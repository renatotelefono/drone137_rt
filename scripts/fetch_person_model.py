"""Fetch and verify the cross-platform person detector's files (MobileNet-SSD, MIT) as pinned in config/person-detector.json.

  python -m scripts.fetch_person_model

Each file is checked against its size and the git blob SHA-1 that GitHub publishes for it; a mismatch is refused and
removed. The SHA-256 of a verified file is printed and, with --record, written into the config beside the pin.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.person_detector import CONFIG, MODELS


def git_blob_sha1(path):
    size = path.stat().st_size
    h = hashlib.sha1(f'blob {size}\0'.encode())
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def sha256(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def verify(path, pin):
    """True when the file matches its pinned size and git blob SHA-1, and its SHA-256 when one is recorded."""
    if not path.is_file() or path.stat().st_size != pin['size'] or git_blob_sha1(path) != pin['git_blob_sha1']:
        return False
    return pin.get('sha256') is None or sha256(path) == pin['sha256']


def fetch(pin, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + '.partial')
    with urllib.request.urlopen(urllib.request.Request(pin['url'], headers={'User-Agent': 'drone137'}), timeout=60) as response, partial.open('wb') as out:
        shutil.copyfileobj(response, out, 1024*1024)
    if partial.stat().st_size != pin['size'] or git_blob_sha1(partial) != pin['git_blob_sha1'] or (pin.get('sha256') and sha256(partial) != pin['sha256']):
        partial.unlink(missing_ok=True)
        raise RuntimeError(f"{pin['name']}: the download does not match its pin; refused and removed")
    partial.replace(destination)
    return destination


def main(args):
    config = json.loads(CONFIG.read_text()); changed = False
    for pin in config['files']:
        path = MODELS/pin['name']
        if verify(path, pin):
            print(f"{pin['name']}: present and verified")
        else:
            fetch(pin, path); print(f"{pin['name']}: fetched and verified ({pin['size']} bytes)")
        digest = sha256(path); print(f"  sha256 {digest}")
        if args.record and pin.get('sha256') != digest:
            pin['sha256'] = digest; changed = True
    if changed:
        CONFIG.write_text(json.dumps(config, indent=2) + '\n'); print('config/person-detector.json: sha256 pins recorded')
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--record', action='store_true', help='write the SHA-256 of each verified file into the config')
    sys.exit(main(parser.parse_args()))
