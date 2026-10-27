# Drone137: how to work in this repository

Drone137 is a private indoor reconnaissance drone system: a small aircraft maps rooms, finds what it is asked
to find, docks itself to charge, and keeps watch from its dock. Everything runs on the ground computer with a
local vision model; nothing leaves the site. The software is complete and gated in simulation; no aircraft has
flown physically.

## Start here

1. `docs/agent-handoff.md`: the running record, newest sections last. Read the last five sections first
   (Windows port, shared airspace, perched watch, pre-flight memory, docking).
2. `README.md` for the product and how to start it; `docs/*.md` for each part's spec, gate and limits.
3. On Windows: `docs/windows.md` is the hand-over. The port was written and tested on macOS and has never run on
   Windows. Work through its numbered list in order and record what you find in that file.

## Environments and tests

- macOS (the developed-on machine): `.local/vision-env/bin/python` (3.12), full suite
  `.local/vision-env/bin/python -m unittest discover -s tests` (about 3 minutes, 434 tests on 27 October 2026).
- Windows: `.venv\Scripts\python.exe` after `scripts\bootstrap-windows.ps1`; suite
  `.venv\Scripts\python.exe -m unittest discover -s tests`. Tests that need Apple's frameworks skip themselves.
- Linux or cloud: `./scripts/bootstrap-cloud.sh --minimal`, then `.venv/bin/python -m unittest discover -s tests`.
- The gates (`scripts/qualify_*.py`) are the acceptance tests: docking, perched watch, swarm airspace, blind
  exploration. Their results live in `docs/*-validation*.json`; a change to a gated part reruns its gate and
  records the numbers in that part's doc.

## Rules that hold everywhere

- Local only: the service binds 127.0.0.1; no telemetry, no cloud calls, no download that is not pinned by hash
  (`config/*.json`, `docs/versions.json`). A download whose digest differs is refused, never trusted.
- Credentials and addresses live in the local database and never reach the model or a listing.
- One model server at a time (port 8081); the perched watches and the mission queue on it.
- Evidence under `.local/validation` is never deleted to make space; archive or compact it.
- Report results as measured. A gate that fails is reported as failing with its numbers.
- Commits: full sentences in the message saying what changed and why, the measured results, and what remains
  unverified. Push to `main`.
