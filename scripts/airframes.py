"""Manage reusable hardware profiles: python -m scripts.airframes --help."""
import argparse
import json
from pathlib import Path
from app.airframes import Airframes, DEFAULT_DB


def main():
    p=argparse.ArgumentParser();p.add_argument('--db',type=Path,default=DEFAULT_DB)
    sub=p.add_subparsers(dest='op',required=True)
    sub.add_parser('list');s=sub.add_parser('show');s.add_argument('reference')
    s=sub.add_parser('save');s.add_argument('file',type=Path);s.add_argument('--expected-revision',type=int,required=True)
    s=sub.add_parser('assign');s.add_argument('vehicle');s.add_argument('reference')
    a=p.parse_args();db=Airframes(a.db)
    value=db.list() if a.op=='list' else db.resolve(a.reference) if a.op=='show' else db.save(json.loads(a.file.read_text()),a.expected_revision) if a.op=='save' else db.assign(a.vehicle,a.reference)
    print(json.dumps(value,indent=2))

if __name__=='__main__':main()
