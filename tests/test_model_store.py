import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from app.model_store import FILES, REPOSITORY, ModelStore, validate_manifest


class Downloads(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.contents = {FILES[0]: b'model'*1000, FILES[1]: b'projector'*500, 'LICENSE': b'licence '*100}
        self.ranges = []
        self.bad_range = self.corrupt = False
        self.no_license = False
        self.declared_license = 'apache-2.0'
        test = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                if self.path.startswith('/api/'):
                    data = json.dumps({'sha': 'a'*40, 'cardData': {'license': test.declared_license}, 'siblings': [{'rfilename': n, 'lfs': {
                        'size': len(test.contents[n]), 'sha256': hashlib.sha256(test.contents[n]).hexdigest()}}
                        for n in FILES]}).encode()
                    self.send_response(200)
                else:
                    name = self.path.rsplit('/',1)[-1]
                    if name == 'LICENSE' and test.no_license:
                        self.send_error(404)
                        return
                    data = test.contents[name]
                    if test.corrupt and name in FILES: data = b'X'*len(data)
                    value = self.headers.get('Range')
                    if value:
                        test.ranges.append(value)
                        offset = int(value.split('=')[1].split('-')[0])
                        self.send_response(206)
                        self.send_header('Content-Range', f'bytes {0 if test.bad_range else offset}-{len(data)-1}/{len(data)}')
                        data = data[offset:]
                    else: self.send_response(200)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.store = ModelStore(Path(self.temp.name), base_url=f'http://127.0.0.1:{self.server.server_port}', reserve_bytes=0)

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.temp.cleanup()

    def test_resumes_and_verifies_exact_pair(self):
        (self.store.directory/(FILES[0]+'.part')).write_bytes(self.contents[FILES[0]][:123])
        self.store.download()
        self.assertEqual(self.ranges, ['bytes=123-'])
        self.assertTrue(self.store.verified)
        self.assertEqual(self.store.manifest()['revision'], 'a'*40)
        self.assertEqual(self.store.verify()[1].read_bytes(), self.contents[FILES[1]])

    def test_bad_resume_range_rejected_preserves_partial(self):
        self.bad_range = True
        path = self.store.directory/(FILES[0]+'.part'); path.write_bytes(b'model')
        with self.assertRaisesRegex(RuntimeError, 'inconsistent'): self.store.download()
        self.assertEqual(path.read_bytes(), b'model')

    def test_corrupt_download_never_installed(self):
        self.corrupt = True
        with self.assertRaisesRegex(RuntimeError, 'SHA256'): self.store.download()
        self.assertFalse((self.store.directory/FILES[0]).exists())
        self.store.reset_partials()
        self.assertFalse((self.store.directory/(FILES[0]+'.part')).exists())
        self.assertTrue(self.store.manifest_path.exists())

    def test_missing_hash_and_revision_fail_closed(self):
        manifest = self.store.resolve()
        manifest['revision'] = None
        with self.assertRaises(ValueError): validate_manifest(manifest)
        manifest['revision'] = 'a'*40; manifest['files'][0]['sha256'] = None
        with self.assertRaises(ValueError): validate_manifest(manifest)

    def test_space_and_concurrent_install_blocked(self):
        with patch('app.model_store.shutil.disk_usage') as usage:
            usage.return_value.free = 0
            with self.assertRaisesRegex(RuntimeError, 'free space'): self.store.download()
        with self.store.lock():
            other = ModelStore(self.store.directory)
            with self.assertRaisesRegex(RuntimeError, 'Another model'): other.reset_partials()

    def test_verification_detects_tampering(self):
        self.store.download()
        path = self.store.directory/FILES[0]
        path.write_bytes(b'X'*path.stat().st_size)
        with self.assertRaisesRegex(RuntimeError, 'corrupt'): self.store.verify()
        self.assertFalse(self.store.verified)

    def test_missing_license_uses_pinned_card_declaration(self):
        self.no_license = True
        self.store.download()
        source = json.loads((self.store.directory/'license-source.json').read_text())
        self.assertIn('/revision/'+'a'*40, source['source'])
        self.assertEqual(source['declaration'], 'apache-2.0')
        (self.store.directory/'LICENSE').write_text('tampered')
        with self.assertRaisesRegex(RuntimeError, 'licence provenance'):
            self.store.verify()

    def test_missing_license_cannot_assume_apache(self):
        self.no_license = True
        self.declared_license = 'other'
        with self.assertRaisesRegex(RuntimeError, 'no pinned Apache'):
            self.store.download()
        self.assertFalse((self.store.directory/'LICENSE').exists())
