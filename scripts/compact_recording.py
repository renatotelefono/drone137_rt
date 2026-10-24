"""Losslessly share duplicate JPEG bytes within a completed flight recording.

Every path and image byte is retained. Call only after the owned flight processes
have exited; an active-recording marker prevents standalone use during capture.
No model weights, videos, failed results or unique images are removed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import uuid


def compact(folder):
    folder=Path(folder).resolve()
    if (folder/'.recording-active').exists():
        raise ValueError('Recording is active; wait until its processes have exited')
    if not any((folder/name).is_file() for name in ('score.json','termination.json')):
        raise ValueError('Recording has no finalized score or termination record')
    summary=folder/'recording-storage.json'
    if summary.exists():
        return json.loads(summary.read_text())
    result={'method':'Exact SHA-256 and byte equality; atomic hardlinks; all paths retained',
            'checked_images':0,'shared_images':0,'released_allocated_bytes':0,
            'free_before_bytes':shutil.disk_usage(folder).free}
    seen={}
    with (folder/'recording-storage.jsonl').open('a') as audit:
        for path in sorted(folder.rglob('*.jpg')):
            # Never traverse a symlink outside the recording.
            if path.is_symlink() or any(p.is_symlink() for p in path.parents if p!=folder):
                continue
            before=path.stat();data=path.read_bytes()
            digest=hashlib.sha256(data).hexdigest();key=(before.st_size,digest)
            other=seen.get(key)
            if other is None:
                seen[key]=path
            elif not os.path.samefile(other,path) and other.read_bytes()==data:
                current=path.stat()
                if (current.st_ino,current.st_mtime_ns,current.st_size)!=(before.st_ino,before.st_mtime_ns,before.st_size):
                    raise RuntimeError('Recording changed during compaction')
                temporary=path.with_name(path.name+'.sharing-'+uuid.uuid4().hex)
                created=False
                try:
                    os.link(other,temporary)
                    created=True
                    os.replace(temporary,path)
                finally:
                    if created and temporary.exists():temporary.unlink()
                result['shared_images']+=1
                if before.st_nlink==1:result['released_allocated_bytes']+=before.st_blocks*512
                audit.write(json.dumps({'path':str(path.relative_to(folder)),
                                        'shares':str(other.relative_to(folder)),
                                        'sha256':digest,'bytes':before.st_size})+'\n')
            result['checked_images']+=1
    result['free_after_bytes']=shutil.disk_usage(folder).free
    temporary=summary.with_suffix('.tmp')
    temporary.write_text(json.dumps(result,indent=2)+'\n');temporary.replace(summary)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('completed_recording')
    print(json.dumps(compact(parser.parse_args().completed_recording),indent=2))
