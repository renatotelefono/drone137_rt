"""Build the pinned, optional sensor-only native estimator. No model downloads."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def run(*args, cwd=ROOT):
    subprocess.run(args,cwd=cwd,check=True)


def build(args):
    manifest=json.loads((ROOT/'config/openvins-runtime.json').read_text())
    vendor=ROOT/'.local/vendor/open_vins';build=ROOT/'.local/build/openvins'
    if not vendor.exists():
        if not args.fetch:raise SystemExit('Missing upstream source. Re-run with --fetch when network access is available.')
        vendor.parent.mkdir(parents=True,exist_ok=True)
        run('git','clone',manifest['upstream'],str(vendor))
        run('git','checkout','--detach',manifest['revision'],cwd=vendor)
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=vendor,text=True).strip()
    if revision!=manifest['revision']:raise SystemExit('Unexpected upstream revision; refusing to overwrite local work.')
    patch=ROOT/manifest['patch']
    applied=subprocess.run(['git','apply','--reverse','--check',str(patch)],cwd=vendor,capture_output=True).returncode==0
    if not applied:
        run('git','apply','--check',str(patch),cwd=vendor)
        run('git','apply',str(patch),cwd=vendor)
    command=['cmake','-S',str(vendor/'ov_msckf'),'-B',str(build),'-DENABLE_ROS=OFF',
             '-DENABLE_ARUCO_TAGS=OFF','-DDISABLE_MATPLOTLIB=ON','-DCMAKE_BUILD_TYPE=Release',
             '-DDRONE137_BRIDGE_SOURCE='+str(ROOT/'native/openvins_bridge.cpp')]
    if args.prefix:command.append('-DCMAKE_PREFIX_PATH='+args.prefix)
    if args.opencv:command.append('-DOpenCV_DIR='+args.opencv)
    run(*command)
    run('cmake','--build',str(build),'--target','drone137_openvins','--parallel',str(args.jobs))
    shutil.copyfile(vendor/'LICENSE',build/'OPENVINS-LICENSE')
    (build/'build-manifest.json').write_text(json.dumps({**manifest,
        'patch_sha256':hashlib.sha256(patch.read_bytes()).hexdigest(),
        'bridge_sha256':hashlib.sha256((ROOT/'native/openvins_bridge.cpp').read_bytes()).hexdigest()},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--fetch',action='store_true');p.add_argument('--prefix');p.add_argument('--opencv');p.add_argument('--jobs',type=int,default=2)
    build(p.parse_args())
