"""Pinned optional vision comparison model; does not change the app's 2B default."""
from pathlib import Path
import hashlib
import json
import shutil
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = 'Qwen/Qwen3-VL-4B-Instruct-GGUF'
REVISION = '1cd86afb9a95c410a6038ab3b40d8b578c892266'
FILES = [
    {'name': 'Qwen3VL-4B-Instruct-Q4_K_M.gguf', 'size': 2497281664,
     'sha256': '66358cb18bb6b3b1b6675aa412c7a88ef01d228f481184d13668e5201c730a0a'},
    {'name': 'mmproj-Qwen3VL-4B-Instruct-Q8_0.gguf', 'size': 453974304,
     'sha256': '30ba2c7dd3127a4561b6cba9d13d0f711c91bdb38742e2f56d73c8cb596bd06d'},
]


def verify(path, item):
    with path.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    if path.stat().st_size != item['size'] or digest != item['sha256']:
        raise ValueError('Checkpoint size/checksum mismatch: '+path.name)


def main():
    folder = ROOT/'.local/data/qwen4b'
    folder.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(folder).free < 13*1024**3:
        raise RuntimeError('Preserve 10 GiB free plus download allowance')
    url = f'https://huggingface.co/api/models/{REPOSITORY}/revision/{REVISION}?blobs=true'
    with urllib.request.urlopen(url, timeout=30) as response:
        metadata = json.load(response)
    if metadata['sha'] != REVISION or metadata['cardData']['license'] != 'apache-2.0':
        raise ValueError('Unexpected model revision/licence')
    lookup = {s['rfilename']: s for s in metadata['siblings']}
    for item in FILES:
        official = lookup[item['name']]['lfs']
        if official['sha256'] != item['sha256'] or official['size'] != item['size']:
            raise ValueError('Official file metadata changed')
        destination = folder/item['name']
        partial = folder/(item['name']+'.part')
        if not destination.exists():
            offset = partial.stat().st_size if partial.exists() else 0
            if offset > item['size']:
                raise ValueError('Oversized partial; preserve it for inspection')
            if offset < item['size']:
                request = urllib.request.Request(
                    f'https://huggingface.co/{REPOSITORY}/resolve/{REVISION}/{item["name"]}',
                    headers={'Range': f'bytes={offset}-'} if offset else {})
                with urllib.request.urlopen(request, timeout=60) as response:
                    if offset and (response.status != 206 or response.headers.get('Content-Range') != f'bytes {offset}-{item["size"]-1}/{item["size"]}'):
                        raise RuntimeError('Inconsistent resume response; partial preserved')
                    with partial.open('ab' if offset else 'wb') as output:
                        mark = offset
                        while chunk := response.read(1024**2):
                            if offset+len(chunk) > item['size']:
                                raise ValueError('Oversized model response')
                            output.write(chunk); offset += len(chunk)
                            if offset-mark >= 128*1024**2:
                                print(item['name'], round(offset/item['size']*100), '%', flush=True)
                                mark = offset
            verify(partial, item)
            partial.replace(destination)
        verify(destination, item)
        print('Verified', destination.name, flush=True)
    manifest = {'repository': REPOSITORY, 'revision': REVISION, 'files': FILES,
                'license': 'apache-2.0', 'metadata_source': url}
    (folder/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    shutil.copyfile(ROOT/'LICENSE', folder/'LICENSE')


if __name__ == '__main__':
    main()
