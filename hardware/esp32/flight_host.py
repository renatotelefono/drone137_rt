"""Desktop runner of the *onboard* C++ controller/parser. Never drives pins."""
import ctypes as C
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def build():
    files = [ROOT/'native/flight_host.cpp', *sorted((ROOT/'hardware/esp32/flight').glob('*.h')),
             ROOT/'native/vendor/cjson/cJSON.c', ROOT/'native/vendor/cjson/cJSON.h']
    digest = hashlib.sha256(b''.join(p.read_bytes() for p in files)).hexdigest()[:16]
    folder = ROOT/'.local/firmware'/digest
    folder.mkdir(parents=True, exist_ok=True)
    target = folder/('libflight.dylib' if sys.platform == 'darwin' else 'libflight.so')
    if not target.exists():
        subprocess.run(['cc', '-O2', '-fPIC', '-c', str(files[-2]), '-o', str(folder/'cJSON.o')], check=True)
        subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-O2', '-fPIC',
                        '-dynamiclib' if sys.platform == 'darwin' else '-shared', str(files[0]),
                        str(folder/'cJSON.o'), '-I'+str(ROOT/'native/vendor/cjson'), '-o', str(target)], check=True)
    return target


class Firmware:
    def __init__(self, *, enabled=False, device='sil-scout'):
        self.lib = C.CDLL(str(build()))
        signatures = {'create': ([C.c_char_p, C.c_char_p, C.c_bool], C.c_void_p),
                      'destroy': ([C.c_void_p], None), 'free': ([C.c_void_p], None),
                      'imu': ([C.c_void_p, C.c_uint64]+[C.c_double]*7, None),
                      'tick': ([C.c_void_p, C.c_uint64], None), 'fault': ([C.c_void_p], None),
                      'bench': ([C.c_void_p,C.c_bool],None),
                      'rig': ([C.c_void_p],None),
                      'request': ([C.c_void_p, C.c_char_p, C.c_char_p, C.c_uint64, C.c_char_p,
                                   C.POINTER(C.c_int)], C.c_void_p)}
        for name, (args, result) in signatures.items():
            fn = getattr(self.lib, 'd137_'+name)
            fn.argtypes, fn.restype = args, result
        self.boot_id = secrets.token_hex(16)
        self.ptr = self.lib.d137_create(device.encode(), self.boot_id.encode(), enabled)

    def close(self):
        if self.ptr:
            self.lib.d137_destroy(self.ptr)
            self.ptr = None

    def imu(self, stamp, gyro=(0, 0, 0), acc=(0, 0, 9.80665), voltage=4.):
        self.lib.d137_imu(self.ptr, stamp, *gyro, *acc, voltage)

    def tick(self, stamp):
        self.lib.d137_tick(self.ptr, stamp)

    def request(self, path, body=None, now=0):
        status = C.c_int()
        raw = body if isinstance(body, str) else json.dumps(body or {}, allow_nan=False)
        value = self.lib.d137_request(self.ptr, path.encode(), raw.encode(), now,
                                     secrets.token_hex(16).encode(), C.byref(status))
        try:
            return status.value, json.loads(C.string_at(value))
        finally:
            self.lib.d137_free(value)

    def hello(self, now):
        return self.request('/v1/hello', now=now)[1]
