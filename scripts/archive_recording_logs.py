"""Losslessly archive large diagnostic logs from completed flight recordings.

Reports, scores, videos and review images stay directly available. Restore a
recording before using historical scripts that expect its raw JSONL paths.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

LOGS=('explorer/vio/estimates.jsonl','plant/public-responses.jsonl',
      'plant/evaluator-telemetry.jsonl','plant/control-timing.jsonl')


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def checked_path(root,name):
    path=root/name
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError('Recording path escapes its directory or is a symlink')
    return path


def inspect_gzip(path,expected_size):
    size=0;h=hashlib.sha256()
    with gzip.open(path,'rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            size+=len(block)
            if size>expected_size:raise ValueError('Archive expands beyond its recorded size')
            h.update(block)
    if size!=expected_size:raise ValueError('Archive size mismatch')
    return h.hexdigest()


def manifest(root):
    p=checked_path(root,'recording-archives.json')
    data=json.loads(p.read_text()) if p.exists() else {'version':1,'files':{}}
    if data.get('version')!=1 or not isinstance(data.get('files'),dict):
        raise ValueError('Unsupported archive manifest')
    if any(name not in LOGS for name in data['files']):raise ValueError('Unexpected archive path')
    return p,data


def save_manifest(path,data):
    with tempfile.NamedTemporaryFile(dir=path.parent,prefix='.archive-',mode='w',delete=False) as stream:
        temporary=Path(stream.name);json.dump(data,stream,indent=2);stream.write('\n')
    temporary.replace(path)


def finalized(root):
    if (root/'.recording-active').exists():raise ValueError('Recording is active')
    if not any((root/p).is_file() for p in ('score.json','termination.json')):
        raise ValueError('Recording is not finalized')


def archive(folder):
    root=Path(folder).resolve();finalized(root);path,data=manifest(root)
    report={'archived_files':0,'released_allocated_bytes':0,'free_before_bytes':shutil.disk_usage(root).free}
    for name in LOGS:
        source=checked_path(root,name);packed=checked_path(root,name+'.gz')
        if not source.exists():continue
        before=source.stat()
        if before.st_nlink!=1:raise ValueError('Refusing to replace a multiply linked log')
        original_hash=digest(source)
        added_bytes=0
        if packed.exists():
            if inspect_gzip(packed,before.st_size)!=original_hash:
                raise ValueError('Existing archive does not match current log')
        else:
            with tempfile.NamedTemporaryFile(dir=source.parent,prefix='.archive-',delete=False) as stream:
                temporary=Path(stream.name)
            try:
                with source.open('rb') as stream,gzip.open(temporary,'wb',compresslevel=3) as compressed:
                    shutil.copyfileobj(stream,compressed,1024*1024)
                if inspect_gzip(temporary,before.st_size)!=original_hash:
                    raise ValueError('Lossless archive verification failed')
                temporary.replace(packed)
                added_bytes=packed.stat().st_blocks*512
            finally:temporary.unlink(missing_ok=True)
        current=source.stat()
        if (current.st_ino,current.st_size,current.st_mtime_ns)!=(before.st_ino,before.st_size,before.st_mtime_ns):
            raise ValueError('Log changed while archiving')
        entry={'source_bytes':before.st_size,'source_sha256':original_hash,
               'gzip_sha256':digest(packed),'gzip_bytes':packed.stat().st_size,
               'mode':before.st_mode&0o777,'mtime_ns':before.st_mtime_ns}
        data['files'][name]=entry
        # Record how to restore before removing the verified redundant raw copy.
        save_manifest(path,data)
        source.unlink()
        report['archived_files']+=1
        report['released_allocated_bytes']+=before.st_blocks*512-added_bytes
    report['free_after_bytes']=shutil.disk_usage(root).free
    return report


def restore(folder):
    root=Path(folder).resolve();finalized(root);_,data=manifest(root);count=0
    for name,entry in data['files'].items():
        source=checked_path(root,name);packed=checked_path(root,name+'.gz')
        if source.exists():
            if digest(source)!=entry['source_sha256']:raise ValueError('Restored log has been modified')
            continue
        size=entry['source_bytes']
        if type(size) is not int or not 0<=size<=64*1024**3:raise ValueError('Invalid archived size')
        if shutil.disk_usage(root).free<size+256*1024**2:raise ValueError('Insufficient space to restore log')
        if digest(packed)!=entry['gzip_sha256']:raise ValueError('Archive checksum mismatch')
        with tempfile.NamedTemporaryFile(dir=source.parent,prefix='.restore-',delete=False) as stream:
            temporary=Path(stream.name)
            try:
                count_bytes=0;h=hashlib.sha256()
                with gzip.open(packed,'rb') as compressed:
                    for block in iter(lambda:compressed.read(1024*1024),b''):
                        count_bytes+=len(block)
                        if count_bytes>size:raise ValueError('Archive size mismatch')
                        h.update(block);stream.write(block)
                stream.flush()
                if count_bytes!=size or h.hexdigest()!=entry['source_sha256']:
                    raise ValueError('Restored log checksum mismatch')
                os.chmod(temporary,entry['mode']&0o777)
                os.utime(temporary,ns=(entry['mtime_ns'],entry['mtime_ns']))
                temporary.replace(source);count+=1
            finally:temporary.unlink(missing_ok=True)
    return {'restored_files':count,'compressed_copies_retained':True}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['archive','restore']);parser.add_argument('recording')
    args=parser.parse_args()
    print(json.dumps((archive if args.action=='archive' else restore)(args.recording),indent=2))
