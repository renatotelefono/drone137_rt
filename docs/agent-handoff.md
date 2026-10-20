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

## What is implemented and tested

- A seeded single-room Three.js sandbox, onboard/overhead views, observed-grid
  exploration, return routing, obstacle supervision and bounded video recording.
- A GUI for one Qwen3-VL-2B GGUF/projector pair: resumable downloads, immutable
  revision selection, SHA256 verification, native runtime build/start/stop,
  diagnostics and a paired-image vision check.
- 52 automated tests passed on Linux, also from a clean source-package install.
- A complete scripted browser mission returned home with 12 observations and
  playable 320 × 240 video. A second mission stopped on stale simulated sensors.
- Local HTTP stubs exercised downloads and model-directed view changes. Those
  checks are **not actual Qwen inference**.

The sandbox uses ideal pose, ideal planar ranges and fixed 1.4 m altitude.
Map-observed fraction measures simulated range coverage, not visual coverage.
Physical transport is disabled. Native Mac/Metal, actual Qwen, Safari recording,
8 GiB resource use, and Gazebo/PX4 indoor flight are unverified.

## First development session

Inspect the working tree and preserve existing changes. On an extracted Mac copy:

```bash
./scripts/bootstrap-macos.sh --minimal
./scripts/test-portable.sh
./scripts/run-local.sh --mode recon --open-browser
```

On Linux, use `bootstrap-cloud.sh --minimal` instead. Use `.venv/bin/python` for
Python commands. Start with the explicitly selected **Scripted demo**. Stop via
Ctrl-C or `./scripts/stop-local.sh`; do not kill unrelated model processes.

Next priority is **R04/A05: real model acceptance on the target Mac**:

1. Record chip, macOS, available memory and free storage. The automatic native
   runtime installer currently targets Apple Silicon.
2. Install the documented Xcode/CMake/Git prerequisites; build the pinned runtime.
3. Download and verify the actual model/projector through the GUI. This cloud's
   Hugging Face requests returned proxy HTTP 403; no real weights were installed.
   Do not substitute unverified weights or silently fall back to scripted mode.
4. Start the model, run the paired-image check, then run rendered reconnaissance.
   Preserve images, responses, failures, timings and changed viewpoints.
5. Measure combined model/browser/controller RAM and swap on the Mac. A profile
   named `lean-8gb` is not proof of compatibility.
6. Update the validation report and task ledger with observed results. Then
   address camera coverage, noisy sensing and fuller navigation/dynamics.

Inference timeout/cancellation quarantines the local model client and requires
server restart. Keep range supervision independent of inference and preserve
operator overrides. Run evidence shares a 1 GiB cap; native logs are bounded.
Do not automatically delete evidence to make a test pass.

After changes, run relevant tests and `./scripts/export-handoff.sh` to refresh
the transfer artifact and checksum. Documentation-only changes do not require
rerunning the full flight/browser suite.
