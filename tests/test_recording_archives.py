import json
from pathlib import Path
import tempfile
import unittest
from scripts.archive_recording_logs import archive,restore


class RecordingArchiveTests(unittest.TestCase):
    def test_roundtrip_preserves_failed_score_bytes_paths_mode_and_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'score.json').write_text('{"accepted":false}')
            (root/'plant').mkdir();p=root/'plant/public-responses.jsonl'
            content=b'{"image":"evidence","time":12.345}\n'*1000;p.write_bytes(content);p.chmod(0o600)
            stamp=p.stat().st_mtime_ns
            (root/'plant/onboard.webm').write_bytes(b'video evidence')
            self.assertEqual(archive(root)['archived_files'],1)
            self.assertFalse(p.exists());self.assertTrue(p.with_suffix('.jsonl.gz').exists())
            self.assertEqual(json.loads((root/'score.json').read_text()),{'accepted':False})
            self.assertEqual((root/'plant/onboard.webm').read_bytes(),b'video evidence')
            self.assertEqual(restore(root)['restored_files'],1)
            self.assertEqual(p.read_bytes(),content);self.assertEqual(p.stat().st_mtime_ns,stamp)
            self.assertEqual(p.stat().st_mode&0o777,0o600)
            self.assertEqual(restore(root)['restored_files'],0)
            self.assertEqual(archive(root)['archived_files'],1)

    def test_active_recordings_and_path_escape_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'score.json').write_text('{}');(root/'.recording-active').touch()
            with self.assertRaisesRegex(ValueError,'active'):archive(root)
            (root/'.recording-active').unlink()
            (root/'recording-archives.json').write_text(json.dumps({'version':1,'files':{'../outside':{}}}))
            with self.assertRaisesRegex(ValueError,'path'):restore(root)

    def test_corrupt_archive_never_replaces_raw_or_restored_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'score.json').write_text('{}');(root/'plant').mkdir()
            p=root/'plant/public-responses.jsonl';p.write_bytes(b'original\n'*100)
            archive(root);packed=p.with_suffix('.jsonl.gz');packed.write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError,'checksum'):restore(root)
            self.assertFalse(p.exists())
            p.write_bytes(b'new data')
            with self.assertRaises(Exception):archive(root)
            self.assertEqual(p.read_bytes(),b'new data')
