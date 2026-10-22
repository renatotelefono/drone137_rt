"""Download one pinned MLX conversion; verify hashes before any inference."""
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = 'aac6fef/laya-mlx'
REVISION = '20aed815fc6acde75733882e7ec0e3f28aeb9717'
DIRECTORY = ROOT/'.local/data/laya-mlx'


def verify():
    manifest = json.loads((DIRECTORY/'manifest.json').read_text())
    for name, record in manifest['files'].items():
        path = DIRECTORY/name
        if not path.resolve().is_relative_to(DIRECTORY.resolve()):
            raise ValueError('Manifest path outside checkpoint')
        with path.open('rb') as source:
            digest = hashlib.file_digest(source, 'sha256').hexdigest()
        if path.stat().st_size != record['bytes'] or digest != record['sha256']:
            raise ValueError('Laya checkpoint hash/size mismatch: '+name)
    record = {'repository': REPOSITORY, 'revision': REVISION,
              'verified_against_pinned_manifest': True, 'files': manifest['files'],
              'source_checkpoint': manifest['source'], 'source_revision': manifest['source_revision']}
    (DIRECTORY/'download-provenance.json').write_text(json.dumps(record, indent=2)+'\n')
    return record


if __name__ == '__main__':
    os.environ.setdefault('HF_HOME', str(ROOT/'.local/huggingface'))
    os.environ.setdefault('HF_HUB_DISABLE_XET', '1')
    os.environ.setdefault('HF_HUB_DOWNLOAD_TIMEOUT', '60')
    from huggingface_hub import snapshot_download
    snapshot_download(REPOSITORY, revision=REVISION, local_dir=DIRECTORY, max_workers=1)
    verify()
    print('Verified pinned Laya MLX checkpoint:', DIRECTORY)
