"""Pre-flight memory check: estimate from configuration, then a measured preflight.

  python -m scripts.preflight_memory --profile mission-simulation --seconds 10
  python -m scripts.preflight_memory --profile mapping-flight --estimate-only

Exit 0 when the profile fits this machine; 1 otherwise. --vio-config points at a folder with
an estimator.yaml from an earlier flight so the estimator is measured too.
"""
import argparse
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import memory_budget


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', default='mission-simulation')
    parser.add_argument('--seconds', type=float, default=10.)
    parser.add_argument('--estimate-only', action='store_true')
    parser.add_argument('--no-verifier', action='store_true', help='do not start the Florence worker for the measurement')
    parser.add_argument('--vio-config', type=Path, default=None)
    parser.add_argument('--full', action='store_true', help='print the full report, not the summary')
    args = parser.parse_args()
    if args.estimate_only:
        report = memory_budget.assess(args.profile)
    else:
        report = asyncio.run(memory_budget.measure(args.profile, args.seconds, verifier=not args.no_verifier, vio_config=args.vio_config))
    print(json.dumps(report if args.full else memory_budget.summary(report), indent=1, default=float))
    return 0 if report['verdict']['fits_machine'] else 1


if __name__ == '__main__':
    sys.exit(main())
