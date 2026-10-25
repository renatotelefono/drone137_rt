"""Compress the flight-evidence history into one reference archive.

Keeps every file the project's records read (scores, summaries, planning
audits, map grids, reports, scene definitions, logs), replaces the memory
sample series with its summary, stores small thumbnails of the observation
frames the model saw, and records the SHA-256 of every excluded frame, video
and raw log so the full history can be verified against this archive later.
Nothing under the source root is modified or removed.
"""
import argparse
import hashlib
import io
import json
import os
import re
import sys
import tarfile
import time
from pathlib import Path

TEXT_EXT = {'.json', '.md', '.txt', '.log', '.yaml', '.yml', '.csv', '.html', '.py', '.sha256', '.cjs', '.mjs', '.js'}
TEXT_LIMIT = 8 * 1024 * 1024
NPZ_LIMIT = 5 * 1024 * 1024
PNG_LIMIT = 300 * 1024
THUMB_WIDTH = 256
THUMB_QUALITY = 60
FRAME = re.compile(r'^frame-\d{4}\.jpg$')


def sha256_of(path, cache):
    st = path.stat()
    key = (st.st_dev, st.st_ino)
    if key in cache:
        return cache[key]
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    cache[key] = h.hexdigest()
    return cache[key]


def decide(rel, size):
    name = rel.name
    ext = rel.suffix.lower()
    if name == 'startup-and-flight-memory.json':
        return 'memory-summary'
    if FRAME.match(name) and 'explorer' in rel.parts and 'vio' not in rel.parts:
        return 'thumbnail'
    if ext in TEXT_EXT and size <= TEXT_LIMIT:
        return 'include'
    if ext == '.npz' and size <= NPZ_LIMIT:
        return 'include'
    if ext == '.png' and size <= PNG_LIMIT:
        return 'include'
    return 'exclude'


def memory_summary(path):
    data = json.loads(path.read_text())
    samples = data.pop('samples', None) or []
    data['samples_removed'] = len(samples)
    if samples:
        data['sample_time_span'] = [samples[0].get('time'), samples[-1].get('time')]
        for key in ('total_bytes', 'rss_bytes', 'guard_bytes', 'host_swap_used_bytes'):
            values = [s.get(key) for s in samples if isinstance(s.get(key), (int, float))]
            if values:
                data[f'{key}_peak'] = max(values)
    return json.dumps(data, separators=(',', ':')).encode()


def thumbnail(path):
    from PIL import Image
    im = Image.open(path).convert('RGB')
    w, h = im.size
    if w > THUMB_WIDTH:
        im = im.resize((THUMB_WIDTH, max(1, round(h * THUMB_WIDTH / w))))
    buf = io.BytesIO()
    im.save(buf, format='JPEG', quality=THUMB_QUALITY, optimize=True)
    return buf.getvalue()


def trial_index(root):
    """One row per finished trial from its score, termination or summary."""
    rows = []
    for score in sorted(root.rglob('score.json')):
        trial = score.parent
        try:
            d = json.loads(score.read_text())
        except Exception as exc:
            rows.append({'trial': str(trial.relative_to(root)), 'error': f'unreadable score: {exc}'})
            continue
        row = {'trial': str(trial.relative_to(root)), 'accepted': d.get('accepted'),
               'metrics': d.get('metrics'), 'failed_gates': [k for k, v in (d.get('gates') or {}).items() if not v],
               'error': d.get('error'), 'peak_application_memory_gib': d.get('peak_application_memory_gib')}
        summary = trial / 'explorer' / 'summary.json'
        if summary.exists():
            try:
                s = json.loads(summary.read_text())
                row.update(place=s.get('place'), state=s.get('state'), wall_time_s=s.get('wall_time_s'),
                           stop_reason=s.get('stop_reason'), observations=len(s.get('steps') or []))
            except Exception:
                pass
        scene = trial / 'plant' / 'scene.json'
        if scene.exists():
            try:
                w = json.loads(scene.read_text())
                row['seed'] = w.get('seed')
            except Exception:
                pass
        rows.append(row)
    for results in sorted(root.rglob('results.json')):
        try:
            d = json.loads(results.read_text())
        except Exception:
            continue
        if 'planned_seeds' in d:
            rows.append({'suite': str(results.parent.relative_to(root)), 'planned_seeds': d.get('planned_seeds'),
                         'passed': d.get('passed'), 'planned': d.get('planned'), 'accepted': d.get('accepted'),
                         'error': d.get('error')})
    return rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', default='.local/validation')
    p.add_argument('--output', required=True, help='archive path ending in .tar.xz')
    args = p.parse_args()
    root = Path(args.root).resolve()
    out = Path(args.output).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    cache = {}
    manifest = []
    counts = {'include': 0, 'thumbnail': 0, 'memory-summary': 0, 'exclude': 0}
    bytes_in = {'include': 0, 'thumbnail': 0, 'memory-summary': 0, 'exclude': 0}
    bytes_stored = 0
    files = [q for q in root.rglob('*') if q.is_file() and not q.is_symlink()]
    files.sort()
    print(json.dumps({'files': len(files), 'root': str(root)}), flush=True)
    with tarfile.open(out, 'w:xz') as tar:
        def add_bytes(name, data, mtime):
            nonlocal bytes_stored
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mtime = int(mtime)
            tar.addfile(info, io.BytesIO(data))
            bytes_stored += len(data)
        for i, q in enumerate(files, 1):
            rel = q.relative_to(root)
            st = q.stat()
            action = decide(rel, st.st_size)
            digest = sha256_of(q, cache)
            entry = {'path': str(rel), 'bytes': st.st_size, 'sha256': digest, 'action': action, 'nlink': st.st_nlink}
            counts[action] += 1
            bytes_in[action] += st.st_size
            try:
                if action == 'include':
                    tar.add(q, arcname=f'history/{rel}', recursive=False)
                    bytes_stored += st.st_size
                elif action == 'memory-summary':
                    data = memory_summary(q)
                    entry['stored_as'] = f'history/{rel.with_suffix("")}.summary.json'
                    add_bytes(entry['stored_as'], data, st.st_mtime)
                elif action == 'thumbnail':
                    data = thumbnail(q)
                    entry['stored_as'] = f'history/{rel.with_suffix("")}.thumb.jpg'
                    entry['thumbnail_bytes'] = len(data)
                    add_bytes(entry['stored_as'], data, st.st_mtime)
            except Exception as exc:
                entry['error'] = f'{type(exc).__name__}: {exc}'
            manifest.append(entry)
            if i % 5000 == 0:
                print(json.dumps({'processed': i, 'of': len(files), 'stored_mb': round(bytes_stored / 2**20, 1),
                                  'elapsed_s': round(time.time() - started)}), flush=True)
        index = {'created_at': time.time(), 'root': str(root), 'trials': trial_index(root)}
        readme = (
            "# Drone137 validation history, reference archive\n\n"
            "Built by scripts/archive_validation_history.py. `history/` mirrors the original\n"
            "tree for every file the project's records read: scores, summaries, planning\n"
            "audits, map grids, reports, scene definitions, suite results and logs.\n"
            "`*.summary.json` replaces each memory sample series with its summary fields.\n"
            "`*.thumb.jpg` are 256-pixel thumbnails of the observation frames the model saw;\n"
            "simulator frames, estimator images, videos, collision meshes and raw JSONL logs\n"
            "are not stored, but `manifest.json` records the SHA-256 and size of every one of\n"
            "them, so a copy of the original tree can be verified against this archive.\n"
            "`index.json` lists every finished trial with its seed, result, metrics and failed\n"
            "gates. This archive is a reference; it is not new evidence and it does not\n"
            "replace the frozen records in docs/.\n")
        summary = {'created_at': time.time(), 'root': str(root), 'files': len(files), 'counts': counts,
                   'source_bytes': bytes_in, 'source_total_bytes': sum(bytes_in.values()),
                   'stored_bytes_uncompressed': bytes_stored, 'entries': manifest}
        add_bytes('manifest.json', json.dumps(summary, separators=(',', ':')).encode(), time.time())
        add_bytes('index.json', json.dumps(index, indent=1).encode(), time.time())
        add_bytes('README.md', readme.encode(), time.time())
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    out.with_suffix(out.suffix + '.sha256').write_text(f'{digest}  {out.name}\n')
    out.with_name(out.name.replace('.tar.xz', '') + '.index.json').write_text(json.dumps(index, indent=1))
    result = {'archive': str(out), 'archive_bytes': out.stat().st_size, 'sha256': digest, 'files': len(files),
              'counts': counts, 'source_total_gb': round(sum(bytes_in.values()) / 2**30, 2),
              'stored_uncompressed_mb': round(bytes_stored / 2**20, 1), 'elapsed_s': round(time.time() - started)}
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
