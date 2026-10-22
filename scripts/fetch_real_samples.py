"""Fetch six small CC BY 4.0 TUM RGB-D preview frames, with pinned checksums.

Diagnostic real-image baseline, not a representative target-camera holdout.
"""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

SAMPLES = [
    ('freiburg1_desk', '5dbdd530cd1165fc5cdd875613f87666c67df84645a585dd1745cb18e5982533', [['monitor','monitors','screen','screens'], ['keyboard','keyboards']]),
    ('freiburg1_room', '94afe78f6c0efac7e2f268392a8014c7f5da3b763524eb098cd44265dded94c2', [['laptop'], ['monitor','monitors']]),
    ('freiburg2_desk', '19a37c42b247b44d9b63d25ee763ac4e4e589dc666ee065eb96014953ed860ab', [['monitor','screen'], ['keyboard']]),
    ('freiburg2_large_no_loop', 'b868bb3b88d883745839260387467b47702505a30a65fc11910efe906a113bc8', [['tripod'], ['fire extinguisher']]),
    ('freiburg2_pioneer_slam', '1dde58eb29f0e08645f00d3554228bbe9fda69616772ae095e840fce2be4b7e3', [['checkerboard','checker board','chessboard','checkered board'], ['cabinet','drawers','drawer']]),
    ('freiburg3_long_office_household', 'a84f24b35cfa73f3180d63a6f6068cbae637ff5c3612c8ef05882ce3979607cc', [['chair','chairs'], ['bottle','bottles']]),
]


def prepare(folder):
    folder.mkdir(parents=True, exist_ok=False)
    cases = []
    for name, checksum, objects in SAMPLES:
        url = f'https://cvg.cit.tum.de/rgbd/dataset/{name.split("_")[0]}/rgbd_dataset_{name}-rgb.png'
        with urllib.request.urlopen(url, timeout=20) as response:
            data = response.read(2_000_001)
        if len(data)>2_000_000 or hashlib.sha256(data).hexdigest() != checksum:
            raise ValueError(f'Unexpected source content: {name}; preserve and investigate, do not update hashes blindly')
        (folder/f'{name}.png').write_bytes(data)
        cases.append({'id': name, 'input': f'{name}.png', 'source_kind': 'public_real',
                      'domain': 'indoor_proxy', 'site_id': 'tum-location-unverified',
                      'encounter_id': name, 'camera_id': 'TUM Kinect/Asus RGB preview',
                      'perception_profile': 'detail', 'split': 'development',
                      'conditions': ['nominal'] if name!='freiburg2_large_no_loop' else ['motion_blur'],
                      'provenance': url+' ; TUM RGB-D benchmark, Sturm et al. (2012), CC BY 4.0',
                      'annotation': {'reviewer':'Codex visual review before Qwen inference, 2026-10-20',
                                     'reviewer_kind':'agent', 'center':None, 'required_objects':objects,
                                     'notes':'Two salient visible objects only. Center clearance and complete inventory are unlabelled. Not independent human ground truth. Acquisition series are not verified independent sites; conservatively grouped together.'}})
    (folder/'collection.json').write_text(json.dumps({'version':1,'dataset_id':'tum-real-smoke-v1',
        'scope':'Six public real-camera preview frames. New to this project test, model pretraining exposure unknown. Indoor proxy; not target-site/camera or flight evidence.',
        'cases':cases},indent=2)+'\n')
    print(folder/'collection.json')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True,help='New directory')
    prepare(parser.parse_args().output)
