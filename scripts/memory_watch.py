"""Sample task-owned processes; abort work above a conservative application budget."""
import ctypes
import os
import platform
import struct
import threading
import time
import psutil

GIB = 1024**3


class MemoryWatch:
    def __init__(self, extra_pids=(), budget_gib=5):
        self.roots = {os.getpid(), *extra_pids}
        self.budget = budget_gib*GIB
        self.samples = []
        self.error = None
        self.exceeded = False
        self.stop_event = threading.Event()
        self.lib = ctypes.CDLL('/usr/lib/libproc.dylib') if platform.system() == 'Darwin' else None
        self.thread = threading.Thread(target=self.run, daemon=True)

    def sample(self):
        pids = set(self.roots)
        for pid in list(pids):
            try:
                pids.update(p.pid for p in psutil.Process(pid).children(recursive=True))
            except psutil.NoSuchProcess:
                pass
        processes = []
        for pid in sorted(pids):
            try:
                p = psutil.Process(pid)
                memory = p.memory_info()
                footprint = None
                if self.lib:
                    # sys/resource.h rusage_info_v0: UUID, seven uint64 fields, phys_footprint.
                    data = ctypes.create_string_buffer(1024)
                    if self.lib.proc_pid_rusage(pid, 0, ctypes.byref(data)) != 0:
                        raise RuntimeError(f'Cannot measure physical footprint of task process {pid}')
                    footprint = struct.unpack_from('Q', data.raw, 72)[0]
                processes.append({'pid': pid, 'name': p.name(), 'rss_bytes': memory.rss,
                                  'physical_footprint_bytes': footprint})
            except psutil.NoSuchProcess:
                continue
        total = sum(p['physical_footprint_bytes'] if self.lib else p['rss_bytes'] for p in processes)
        rss = sum(p['rss_bytes'] for p in processes)
        # File-backed GGUF pages can be resident without being charged to macOS
        # physical footprint. RSS sums may double-count shared pages; using the
        # larger measure is intentionally conservative for the small-host guard.
        guard = max(total, rss)
        sample = {'time': time.time(), 'total_bytes': total, 'rss_bytes': rss,
                  'guard_bytes': guard, 'processes': processes,
                  'host_swap_used_bytes': psutil.swap_memory().used}
        self.samples.append(sample)
        self.exceeded |= guard > self.budget

    def run(self):
        while not self.stop_event.is_set():
            try:
                self.sample()
            except Exception as exc:
                self.error = f'{type(exc).__name__}: {exc}'
            self.stop_event.wait(.2)

    def start(self):
        self.sample()
        self.thread.start()

    def check(self):
        if self.error:
            raise RuntimeError('Memory measurement failed: '+self.error)
        if self.exceeded:
            raise MemoryError('Application exceeded the 5 GiB experiment budget; run stopped')

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=2)

    def report(self):
        return {'metric': 'sum of macOS process physical footprints' if self.lib else 'sum of process RSS',
                'interval_s': .2, 'budget_gib': self.budget/GIB,
                'sampled_peak_gib': max((s['total_bytes'] for s in self.samples), default=0)/GIB,
                'sampled_peak_rss_gib': max((s['rss_bytes'] for s in self.samples), default=0)/GIB,
                'sampled_peak_guard_gib': max((s['guard_bytes'] for s in self.samples), default=0)/GIB,
                'guard_metric': 'Larger of summed RSS and summed physical footprints; RSS can double-count shared pages.',
                'budget_exceeded': self.exceeded, 'measurement_error': self.error,
                'host_memory_gib': psutil.virtual_memory().total/GIB,
                'actual_8gb_hardware': psutil.virtual_memory().total <= 8*GIB,
                'scope': 'Evaluator and its child processes (optional visual reviewer or Laya, camera browser including GPU/helpers, Node, simulator/PX4/MAVSDK) plus the app/Qwen process tree. Excludes unrelated applications and user browser tabs. Sampling is not an OS-enforced RAM limit.',
                'host_swap_start_bytes': self.samples[0]['host_swap_used_bytes'] if self.samples else None,
                'host_swap_end_bytes': self.samples[-1]['host_swap_used_bytes'] if self.samples else None,
                'samples': self.samples}
