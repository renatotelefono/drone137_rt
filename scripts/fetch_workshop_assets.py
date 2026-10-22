"""Restore pinned CC0 assets from their exact URLs; no live catalog at runtime."""
import argparse
import hashlib
import json
import urllib.request
from sim.asset_world import ASSET_ROOT, MANIFEST, verify_assets


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--verify', action='store_true', help='Verify local files without network access')
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text())
    if not args.verify:
        for relative, record in manifest['files'].items():
            path = ASSET_ROOT/relative
            if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == record['sha256']:
                continue
            request = urllib.request.Request(record['url'], headers={'User-Agent':'drone137-local-simulation-research'})
            with urllib.request.urlopen(request, timeout=90) as response:
                data = response.read(record['bytes']+1)
            if len(data) != record['bytes'] or hashlib.sha256(data).hexdigest() != record['sha256']:
                raise ValueError(f'Asset download checksum mismatch: {relative}')
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(path.suffix+'.part')
            temporary.write_bytes(data); temporary.replace(path)
    verify_assets()
    print(f"Verified {len(manifest['files'])} CC0 asset files. Source: https://polyhaven.com")


if __name__ == '__main__':
    main()
