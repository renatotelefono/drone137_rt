# Development agent handoff

## Start here

Continue the existing drone137 implementation; do not rebuild it from scratch.
The user's current objective is autonomous visual reconnaissance in a confined
space, initially using a local model and virtual testing on a Mac. The user
prefers Python and does not want TypeScript for this project. The current stack
is Python/aiohttp, plain JavaScript/Three.js, and a thin llama.cpp model manager.

Read these files in order:

1. `README.md`: current product, startup and limitations.
2. `docs/handoff.md`: Mac installation and acceptance procedure.
3. `docs/recon-architecture.md`: current recon implementation and contracts.
4. `docs/validation.md`: actual test evidence and unverified claims.
5. `docs/tasks.md`: remaining work.
6. `docs/recon-objective.md`: mission requirements beyond this first sandbox.
7. `docs/vision-flight-comparison.md` and `docs/vision-flight-validation.json`:
   native rotor preflight and live Qwen/Florence/SmolVLM2 comparison, including
   resource failures and subsequent inspection-policy experiments.

The visual companion experiments use an optional isolated `.local/vision-env`;
dependencies are pinned in `requirements-vision-reviewers.txt`. They are invoked
through the native flight evaluator, not the mission-control model selector.
Do not describe a four-case development pass as full realism-suite qualification,
held-out accuracy or validation on actual 8 GB hardware. Source edits during a
flight evaluation invalidate its frozen-source integrity check.

The original uploaded project brief is reference material. Its outdoor gate
mission and aircraft assumptions do not override the user's later confined-space
recon objective. The older gate executor/native integration remains a separate
regression path; consult its architecture only when working on that path.

## Transfer and repository state

The source is versioned on `main` in `bitfent/drone137`. Begin by inspecting
`git status` and `git log -1`; preserve any local changes before checkout/reset
or cleanup operations. The repository originally began empty, but the initial
implementation is now supplied as a source commit.

An agent in this same workspace can use `/workspace/drone137`. An agent elsewhere
can clone `https://github.com/bitfent/drone137.git`. Alternatively, use
`dist/drone137-source.tar.gz` and its `.sha256` sidecar from an exported handoff;
verify the checksum before extraction. Generated archives are not Git-tracked.
Models, native builds, environments and bulk run evidence are excluded; source,
lockfiles, tests and validation summaries are included.

The cloud setup draft has been saved, but saving does not apply/publish it.
Fresh-task restoration has not been verified. Do not assume this conversation,
running processes, untracked files or draft network changes exist in a new task.

## Current implementation and observed results

- Latest interface: `/control` mission dashboard, with selectable rectangle,
  actual-Qwen brief interpretation, reviewable viewpoint assignments and two
  isolated aircraft/camera workers. Shared indoor airspace is leased to one
  aircraft at a time; queued drones are docked outside the site. Both completed
  actual-model flights with six total observations and separate playable 720p
  videos. Local-model intent checks passed 8/8 development prompts after a retained
  doorway-task misclassification. 105 automated tests pass. See
  `mission-control.md` and `mission-control-validation.json`; these are dispatch
  and evidence tests, not concurrent-flight or real-world qualifications.

- Latest feature: `realism` camera bay, local scanned concrete, bottles/chair/cone
  and bench clutter. Camera conditions nominal/dim/glare/motion share processed
  display/video/JPEG pixels. Read the newest section of `docs/validation.md` and
  `realism-validation.json`. Frozen seed-619 tests passed 28/28 cases, 36/36 required
  object names and 8/8 doorway checks; p95 4.910 s. This is one synthetic site.
  Failed prompt/crop iterations and the original return-route failure are retained.
  Production uses an explicit passage task only where declared by the operator's
  checkpoint; the original general center and full-frame object survey remain.
  Do not resurrect the rejected crop pipeline or mistake a seed for a new site.

- The latest user scope is workshops, warehouses, building perimeters, flat fields
  and hillsides. All five remain unqualified. Read `docs/reliability-protocol.md`.
  The new frozen evaluator and image/video importer keep site/encounter identities,
  reject changed/duplicate inputs, track used held-out sites, and separate public
  proxy data from target-camera evidence. Six real TUM preview frames found 11/12
  labelled object names and 5/6 passing images; the missed bottles remain a failure.
  No prompt was tuned on these frames. Do not report this as general recognition,
  physical clearance, continuous video understanding or mission performance.
- Three.js random room, warehouse, connected-room and detailed workshop scenes, including a passage
  obstruction variant; explore and inspection-point patrol modes.
- Geometry-free observed-map navigation in `app/navigation.py`; ideal vehicle in
  `adapters/kinematic.py`; scene/range geometry in `sim/recon_world.py`. Recon still
  instantiates the kinematic backend. It is not yet a generic PX4 indoor controller.
- Saved run history and HTML reports with playable video, selected images,
  approximate video seek positions, route/map and unreached checkpoints.
- Actual Qwen/Metal on the M4: the original closed-gate and changed-passage misses
  are corrected by separate image-evidence and action-selection calls. The shared
  camera profiles pass 32 image cases, including 24 rendered viewpoints and eight regressions.
  The workshop has 720p video, 960 × 540 model frames and a separate object-survey call. The
  browser test now requires actual obstruction detection and a report finding;
  recording/navigation success alone cannot pass it. Broader semantics remain open.
- 105 automated tests pass on Mac; 104 accelerated navigation geometry cases return
  with zero clearance violations. These tests use ideal pose/ranges, not dynamics.
- PX4 SITL, locked Gazebo and the JPEG bridge compiled on M4/macOS 15.6. One
  real-Qwen legacy gate route completed takeoff, correctly classified both gates
  from native frames, returned and landed. Indoor PX4 recon remains unimplemented.

Exact current evidence and episode IDs are in `docs/validation.md` and the compact
`docs/workshop-validation.json` and `docs/perception-validation.json` (with earlier failures in `docs/mac-validation.json`). Older Linux records are retained as historical evidence.
Models/builds/run media live under `.local` in this checkout and are not exported.
`app/perception.py` owns the vision schema and separate bounded text policy.
Compare only aligned camera poses, and preserve uncertainty; identical center
classes do not establish that the whole scene is unchanged. Evaluation scripts:
`render-vision-cases.cjs`, `evaluate_perception.py`, `render-detail-cases.cjs`,
`evaluate_detail.py`, and `check-patrol.cjs`. The detail renderer preserves uniquely
named sets; its evaluator defaults to the newest completed set. Object checks
grade expected names, not every caption detail. Review images for hallucinated details.
The model, browser and simulator run on a 16 GiB M4; actual 8 GiB and sustained
physical memory/offline acceptance remain pending. Physical transport is disabled.

## Next development session

Inspect `git status`, preserve current work, and use the existing environments:

```bash
./scripts/bootstrap-macos.sh --minimal
./scripts/test-portable.sh
./scripts/run-local.sh --mode recon --open-browser
```

On Linux use `bootstrap-cloud.sh --minimal`. Use `.venv/bin/python` for Python.
The bootstrap finds supported Python even when Finder defaults to Apple's 3.9.
The GUI starts/stops the owned local model; no Ollama service is required.

1. Keep the corrected perception failures as regressions and expand held-out tests
   beyond centered static surfaces. Score missed obstructions, false-clear
   classifications, uncertain cases and changes. Improve image detail,
   prompt or local model choice based on measured accuracy. Keep range supervision
   independent of model descriptions; never hide uncertain/incorrect observations.
   Use `scripts/prepare-reliability.cjs` and `scripts/evaluate_reliability.py` for
   new physical-camera recordings. Freeze before inference; use fresh sites for
   holdout, label with an independent human, and keep exposed sites in development.
   Public preview images are grouped conservatively as one unverified location.
2. Connect indoor navigation to a PX4 adapter with local pose/ranges and bounded
   velocity commands, explicit coordinate/yaw conversions and autopilot failsafes.
   The existing native path is a separate global-waypoint gate mission.
3. Test localization drift, sensor delay/loss, inference timeout, camera coverage,
   operator takeover and return/landing in flight dynamics. Establish repeated
   held-out, offline and sustained memory evidence before a real-drone test plan.

Native installation uses `scripts/install-sim.sh`, PX4's pinned Pixi lock and
`scripts/with-sim.sh`. It avoids the broad upstream macOS installer. Native fixes:
explicit local world/model launch, PX4 daemon mode, MAVSDK `set_current_speed`,
and a loopback `GZ_IP` shared by Gazebo and the camera bridge. The bundled SDK's
gRPC server still listens on all interfaces; restrict it before distributed use.
Use Ctrl-C or `./scripts/stop-local.sh`; terminate only this app's owned processes.

Inference timeout/cancellation quarantines the local model client and requires
server restart. Keep range supervision independent of inference and preserve
operator overrides. Run evidence shares a 1 GiB cap; native logs are bounded.
Do not automatically delete evidence to make a test pass.

After changes, run relevant tests and `./scripts/export-handoff.sh` to refresh
the transfer artifact and checksum. Documentation-only changes do not require
rerunning the full flight/browser suite.
