"""Pre-flight memory: an estimate from configuration, a measured preflight, and the host budget.

Three layers. The estimate sums formulas (model files and context cache, mapping grids, frame
buffers) and measured baselines per component for the profile a flight will start. The measured
preflight starts what can be started without an aircraft, samples it for a few seconds and
compares with the host's free memory. The budget is what the in-flight memory watch enforces.
Baselines learned by preflights are kept locally and never replace the shipped provenance.
"""
import asyncio
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import time

import psutil

ROOT = Path(__file__).resolve().parents[1]
BASELINES = ROOT/'config/memory-baselines.json'
LEARNED = Path(os.environ.get('DRONE137_DATA_DIR', ROOT/'.local/data')).resolve()/'memory-baselines.json'
GIB = 1024**3


def load_baselines():
    data = json.loads(BASELINES.read_text())
    if LEARNED.is_file():
        try:
            learned = json.loads(LEARNED.read_text())
            for name, entry in learned.get('components', {}).items():
                shipped = data['components'].get(name, {})
                if type(entry.get('gib')) in (int, float) and type(shipped.get('gib')) in (int, float) and entry['gib'] > shipped['gib']:
                    data['components'][name] = {**shipped, **entry, 'learned': True}   # a larger local measurement is kept, never a smaller one
        except (ValueError, OSError):
            pass
    return data


def host():
    v = psutil.virtual_memory(); s = psutil.swap_memory()
    return {'total_gib': v.total/GIB, 'available_gib': v.available/GIB, 'swap_used_gib': s.used/GIB, 'sampled_at': time.time()}


def budget_gib(total_gib=None, data=None):
    """The application budget the memory watch enforces on this host."""
    data = data or load_baselines(); total_gib = host()['total_gib'] if total_gib is None else total_gib
    return data['budget_gib']['small'] if total_gib <= data['small_host_max_gib'] else data['budget_gib']['standard']


def gguf_metadata(path):
    """Architecture, layer count and attention shape from a GGUF header; no tensor data is read."""
    with open(path, 'rb') as f:
        if f.read(4) != b'GGUF':
            raise ValueError('Not a GGUF file')
        version, = struct.unpack('<I', f.read(4)); tensors, = struct.unpack('<Q', f.read(8)); count, = struct.unpack('<Q', f.read(8))
        sizes = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}
        formats = {0: '<B', 1: '<b', 2: '<H', 3: '<h', 4: '<I', 5: '<i', 6: '<f', 7: '<?', 10: '<Q', 11: '<q', 12: '<d'}
        def string():
            n, = struct.unpack('<Q', f.read(8)); return f.read(n).decode('utf-8', 'replace')
        def value(kind):
            if kind == 8:
                return string()
            if kind == 9:
                inner, = struct.unpack('<I', f.read(4)); n, = struct.unpack('<Q', f.read(8))
                if inner == 8:
                    for _ in range(n): string()
                else:
                    f.seek(sizes[inner]*n, 1)
                return None
            return struct.unpack(formats[kind], f.read(sizes[kind]))[0]
        fields = {}
        for _ in range(count):
            key = string(); kind, = struct.unpack('<I', f.read(4)); fields[key] = value(kind)
    arch = fields.get('general.architecture', '')
    pick = lambda name, default=None: fields.get(f'{arch}.{name}', default)
    return {'architecture': arch, 'version': version, 'tensors': tensors, 'layers': pick('block_count'), 'embedding': pick('embedding_length'),
            'heads': pick('attention.head_count'), 'kv_heads': pick('attention.head_count_kv', pick('attention.head_count')),
            'key_length': pick('attention.key_length'), 'value_length': pick('attention.value_length'), 'bytes': Path(path).stat().st_size}


def model_estimate(model, metadata=None):
    """Bytes for the model server: both files, the context cache from the header and a measured overhead."""
    weights, mmproj = ROOT/model['weights'], ROOT/model['mmproj']
    if not weights.is_file() or not mmproj.is_file():
        return {'bytes': None, 'basis': 'model files missing', 'detail': {'weights': str(weights), 'mmproj': str(mmproj)}}
    meta = metadata or gguf_metadata(weights)
    head = meta['key_length'] or (meta['embedding']//meta['heads'] if meta['embedding'] and meta['heads'] else 128)
    value_head = meta['value_length'] or head
    kv = 2*meta['layers']*model['context']*meta['kv_heads']*((head+value_head)/2)*model['kv_bytes_per_value']
    total = meta['bytes'] + mmproj.stat().st_size + kv + model['server_overhead_gib']*GIB
    return {'bytes': int(total), 'basis': 'formula',
            'detail': {'weights_gib': meta['bytes']/GIB, 'mmproj_gib': mmproj.stat().st_size/GIB, 'context_cache_gib': kv/GIB,
                       'context': model['context'], 'layers': meta['layers'], 'kv_heads': meta['kv_heads'], 'overhead_gib': model['server_overhead_gib']}}


def flight_structures(width=960, height=540, ring=3, jpeg_bytes=200_000):
    """Allocate what a flight process keeps in memory and report the bytes; used by the estimate and the preflight child."""
    import numpy as np
    from app.voxel_mapping import RaycastMap
    mapping = RaycastMap()
    grids = {k: v for k, v in vars(mapping).items() if isinstance(v, np.ndarray)}
    frames = [np.zeros((height, width, 3), np.uint8) for _ in range(ring)]
    jpegs = [bytearray(jpeg_bytes) for _ in range(2)]
    return mapping, frames, jpegs, {'grids_bytes': int(sum(g.nbytes for g in grids.values())), 'grid_shapes': {k: list(v.shape) for k, v in grids.items()},
                                   'frames_bytes': int(sum(f.nbytes for f in frames)) + jpeg_bytes*2}


def flight_estimate(data):
    base = data['components']['flight']
    try:
        _, _, _, sizes = flight_structures()
    except Exception as exc:
        return {'bytes': int(base['gib']*GIB), 'basis': base['basis'] + f'; structures not allocated ({type(exc).__name__})', 'detail': {}}
    return {'bytes': int(base['gib']*GIB + sizes['grids_bytes'] + sizes['frames_bytes']), 'basis': base['basis'] + ' + allocated grids and frame ring',
            'detail': {'baseline_gib': base['gib'], 'grids_gib': sizes['grids_bytes']/GIB, 'frames_gib': sizes['frames_bytes']/GIB, 'grid_shapes': sizes['grid_shapes']}}


def estimate(profile, data=None):
    """Per-component bytes for a profile, before anything starts."""
    data = data or load_baselines()
    if profile not in data['profiles']:
        raise ValueError('Unknown memory profile; one of ' + ', '.join(data['profiles']))
    components = {}
    for name in data['profiles'][profile]:
        if name == 'model-server':
            components[name] = model_estimate(data['model'])
        elif name == 'flight':
            components[name] = flight_estimate(data)
        else:
            entry = data['components'][name]
            components[name] = {'bytes': int(entry['gib']*GIB), 'basis': entry['basis'] + (' (learned locally)' if entry.get('learned') else ''), 'detail': {}}
    known = [c['bytes'] for c in components.values() if c['bytes'] is not None]
    return {'profile': profile, 'components': components, 'total_gib': sum(known)/GIB,
            'unknown': [n for n, c in components.items() if c['bytes'] is None], 'baselines': data['version'], 'measured_on': data['measured_on']}


def verdict(total_gib, machine=None, data=None):
    """fits_machine: static, against the host's total memory. fits_now: dynamic, against what is free this moment."""
    data = data or load_baselines(); machine = machine or host()
    need_machine = total_gib + data['os_reserve_gib'] + data['margin_gib']
    budget = budget_gib(machine['total_gib'], data)
    return {'total_gib': total_gib, 'host_total_gib': machine['total_gib'], 'host_available_gib': machine['available_gib'],
            'host_swap_used_gib': machine['swap_used_gib'], 'os_reserve_gib': data['os_reserve_gib'], 'margin_gib': data['margin_gib'],
            'fits_machine': need_machine <= machine['total_gib'], 'fits_now': total_gib + data['margin_gib'] <= machine['available_gib'],
            'budget_gib': budget, 'within_budget': total_gib <= budget,
            'note': 'The total sums component peaks that do not coincide, so it is an upper bound. Available memory on macOS is a lower bound: file cache and compressed pages are reclaimed on demand. The budget is enforced on the measured sum in flight.'}


def assess(profile, data=None):
    e = estimate(profile, data)
    return {**e, 'verdict': verdict(e['total_gib'], data=data)}


def model_server_pid(data=None):
    match = (data or load_baselines())['model']['command_match']
    for p in psutil.process_iter(['pid', 'cmdline']):
        try:
            if any(match in part for part in (p.info['cmdline'] or [])):
                return p.info['pid']
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


def footprint(pid):
    """Memory of a process tree: the larger of summed physical footprints and summed RSS.

    File-backed model pages are resident without being charged to the macOS footprint, and RSS can
    double-count shared pages; the larger figure is the conservative one, as in the memory watch."""
    try:
        procs = [psutil.Process(pid)]
        procs += procs[0].children(recursive=True)
    except psutil.NoSuchProcess:
        return 0
    physical = rss = 0
    for p in procs:
        try:
            rss += p.memory_info().rss
            if sys.platform == 'darwin':
                import ctypes
                lib = ctypes.CDLL('/usr/lib/libproc.dylib'); data = ctypes.create_string_buffer(1024)
                if lib.proc_pid_rusage(p.pid, 0, ctypes.byref(data)) == 0:
                    physical += struct.unpack_from('Q', data.raw, 72)[0]
        except psutil.NoSuchProcess:
            continue
    return max(physical, rss)


ALLOCATOR = ("import sys, time; sys.path.insert(0, %r)\n"
             "from app.memory_budget import flight_structures\n"
             "keep = flight_structures(); print('ready', flush=True); time.sleep(float(sys.argv[1]))\n")


async def measure(profile, seconds=10., *, data=None, verifier=True, vio_config=None):
    """Start what can be started without an aircraft, sample it, compare with the host.

    Measured: the running model server, a child holding the flight structures, the verifier
    worker when the profile needs it, the VIO estimator when a configuration folder is given.
    Everything else keeps its baseline and is marked so."""
    data = data or load_baselines()
    seconds = float(max(1., min(60., seconds)))
    components = estimate(profile, data)['components']
    before = host()
    procs, closers, measured = {}, [], {}
    try:
        pid = model_server_pid(data) if 'model-server' in components else None
        if pid:
            procs['model-server'] = pid
        child = await asyncio.create_subprocess_exec(sys.executable, '-c', ALLOCATOR % str(ROOT), str(seconds + 5), cwd=ROOT,
                                                     stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        line = await asyncio.wait_for(child.stdout.readline(), 60)
        if line.strip() != b'ready':
            raise RuntimeError('Flight structures could not be allocated')
        procs['flight'] = child.pid; closers.append(lambda: child.kill())
        if 'vio' in components and vio_config and (ROOT/'.local/build/openvins/drone137_openvins').is_file():
            vio = subprocess.Popen([str(ROOT/'.local/build/openvins/drone137_openvins'), str(vio_config)], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            ready = vio.stdout.readline()
            if b'"ready":true' in ready:
                procs['vio'] = vio.pid
            closers.append(lambda: (vio.stdin.close(), vio.kill()))
        if 'verifier' in components and verifier:
            from adapters.vision_reviewer import VisionReviewer
            import tempfile
            folder = Path(tempfile.mkdtemp(prefix='preflight-'))
            reviewer = VisionReviewer('florence', folder)
            try:
                await reviewer.start()
                procs['verifier'] = reviewer.process.pid
                closers.append(lambda: asyncio.ensure_future(reviewer.close()))
            except Exception as exc:
                measured['verifier'] = {'error': f'{type(exc).__name__}: {exc}'[:160]}
        peaks = {name: 0 for name in procs}
        samples = 0
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            for name, pid in procs.items():
                peaks[name] = max(peaks[name], footprint(pid))
            samples += 1
            await asyncio.sleep(.2)
        for name, bytes_ in peaks.items():
            measured[name] = {'bytes': bytes_, 'gib': bytes_/GIB, 'basis': 'measured preflight'}
    finally:
        for close in closers:
            try:
                close()
            except Exception:
                pass
    after = host()
    report = {'profile': profile, 'seconds': seconds, 'samples': samples, 'host_before': before, 'host_after': after, 'components': {}}
    for name, est in components.items():
        m = measured.get(name)
        if m and m.get('bytes') is not None:
            # A preflight measures an idle component (no flight, no inference), so it is a floor; the
            # estimate stays in the total when it is larger, and the measured figure is kept beside it.
            # The flight child holds only the grids and frames, never the whole flight process.
            bytes_ = max(m['bytes'], est['bytes'] or 0) if name != 'flight' else (est['bytes'] or m['bytes'])
            report['components'][name] = {'bytes': bytes_, 'gib': bytes_/GIB, 'basis': 'measured preflight' if bytes_ == m['bytes'] else 'estimate; measured idle below it',
                                          'measured_gib': m['gib'], 'estimate_gib': (est['bytes'] or 0)/GIB}
        else:
            report['components'][name] = {'bytes': est['bytes'], 'gib': (est['bytes'] or 0)/GIB, 'basis': 'not measured; ' + est['basis'],
                                          **({'error': m['error']} if m and 'error' in m else {})}
    known = [c['bytes'] for c in report['components'].values() if c['bytes'] is not None]
    report['total_gib'] = sum(known)/GIB
    report['unknown'] = [n for n, c in report['components'].items() if c['bytes'] is None]
    report['measured'] = sorted(n for n in measured if 'bytes' in measured[n])
    report['measured_gib'] = {n: round(measured[n]['gib'], 3) for n in report['measured']}
    report['verdict'] = verdict(report['total_gib'], after, data)
    learn(report, data)
    return report


def learn(report, data):
    """Keep measured peaks locally so later estimates start from this machine's own numbers."""
    try:
        learned = json.loads(LEARNED.read_text()) if LEARNED.is_file() else {'components': {}}
    except (ValueError, OSError):
        learned = {'components': {}}
    for name, entry in report['components'].items():
        if 'measured_gib' in entry and name in data['components'] and data['components'][name].get('basis') != 'formula' and name != 'flight':
            learned['components'][name] = {'gib': entry['measured_gib'], 'basis': f"measured preflight on {time.strftime('%Y-%m-%d')}"}
    LEARNED.parent.mkdir(parents=True, exist_ok=True)
    LEARNED.write_text(json.dumps(learned, indent=2))


def summary(report):
    v = report['verdict']
    return {'profile': report['profile'], 'total_gib': round(report['total_gib'], 2), 'host_total_gib': round(v['host_total_gib'], 1),
            'host_available_gib': round(v['host_available_gib'], 2), 'fits_machine': v['fits_machine'], 'fits_now': v['fits_now'],
            'budget_gib': v['budget_gib'], 'within_budget': v['within_budget'],
            'components': {n: round((c['bytes'] or 0)/GIB, 3) for n, c in report['components'].items()},
            'measured': report.get('measured', []), 'measured_gib': report.get('measured_gib', {}), 'unknown': report.get('unknown', [])}
