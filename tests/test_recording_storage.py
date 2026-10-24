import json
import os
from pathlib import Path
import tempfile
import unittest
from scripts.compact_recording import compact


class RecordingStorageTests(unittest.TestCase):
    def test_duplicates_share_storage_but_every_path_and_byte_remains(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'score.json').write_text('{"accepted":false}')
            (root/'a').mkdir();(root/'b').mkdir()
            images={'a/a.jpg':b'jpeg one','b/b.jpg':b'jpeg one','b/c.jpg':b'jpeg two'}
            for name,data in images.items():(root/name).write_bytes(data)
            # An unrelated/pre-existing maintenance artifact must survive.
            (root/'b/b.jpg.sharing').write_bytes(b'keep this artifact')
            result=compact(root)
            self.assertEqual(result['checked_images'],3)
            self.assertEqual(result['shared_images'],1)
            self.assertTrue(os.path.samefile(root/'a/a.jpg',root/'b/b.jpg'))
            for name,data in images.items():self.assertEqual((root/name).read_bytes(),data)
            self.assertEqual((root/'b/b.jpg.sharing').read_bytes(),b'keep this artifact')
            self.assertEqual(json.loads((root/'score.json').read_text()),{'accepted':False})
            self.assertEqual(compact(root),result)

    def test_active_or_unfinalized_recording_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with self.assertRaisesRegex(ValueError,'finalized'):compact(root)
            (root/'score.json').write_text('{}');(root/'.recording-active').touch()
            with self.assertRaisesRegex(ValueError,'active'):compact(root)
            self.assertFalse((root/'recording-storage.jsonl').exists())

    def test_external_symlinks_and_unique_artifacts_are_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'trial';root.mkdir();outside=Path(tmp)/'external.jpg';outside.write_bytes(b'external')
            (root/'termination.json').write_text('{"error":"failed flight"}')
            (root/'frame.jpg').symlink_to(outside);(root/'video.webm').write_bytes(b'video')
            result=compact(root)
            self.assertEqual(result['checked_images'],0)
            self.assertTrue((root/'frame.jpg').is_symlink())
            self.assertEqual(outside.read_bytes(),b'external')
            self.assertEqual((root/'video.webm').read_bytes(),b'video')
