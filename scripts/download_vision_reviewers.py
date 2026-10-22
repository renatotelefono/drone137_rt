"""Fetch official checkpoints and freeze revisions/hashes for flight comparisons."""
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = {'florence': 'microsoft/Florence-2-base-ft',
          'smolvlm': 'HuggingFaceTB/SmolVLM2-500M-Video-Instruct'}

def main():
    os.environ.setdefault('HF_HOME', str(ROOT/'.local/huggingface'))
    os.environ.setdefault('HF_HUB_DISABLE_XET', '1')
    os.environ.setdefault('HF_HUB_DOWNLOAD_TIMEOUT', '120')
    from huggingface_hub import HfApi, snapshot_download
    for name, repo in MODELS.items():
        folder=ROOT/'.local/data/vision-reviewers'/name
        folder.mkdir(parents=True,exist_ok=True)
        pin=folder/'revision.json'
        if not pin.exists():
            pin.write_text(json.dumps({'repository':repo,'revision':HfApi().model_info(repo).sha},indent=2))
        record=json.loads(pin.read_text());print(json.dumps(record),flush=True)
        snapshot_download(repo,revision=record['revision'],local_dir=folder,max_workers=2,
            allow_patterns=['*.json','*.safetensors','*.txt','*.model','*.py','README.md','LICENSE*'],
            ignore_patterns=['onnx/*','onnx/**','*/**'])
        files={}
        for p in sorted(folder.iterdir()):
            if p.is_file() and p.name not in ('manifest.json','revision.json'):
                with p.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
                files[p.name]={'bytes':p.stat().st_size,'sha256':digest}
        (folder/'manifest.json').write_text(json.dumps({**record,'files':files},indent=2))
        print(name+' verified',flush=True)

if __name__=='__main__':main()
