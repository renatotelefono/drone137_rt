# Validation report — 20 October 2026

Host: `25eaecfa9f86`, Linux 6.18.55 / x86_64, Python 3.12.14.
Browser: Chromium 154.0.8037.57, headless software WebGL; Playwright 1.58.2.
Actual model inference: **no**. Rendered Three.js camera: **yes**.
Realistic flight dynamics / native Mac / physical transport: **not validated**.

## Current recon lab evidence

- **52 automated tests passed**, zero failures/skips, in 31.438 seconds.
  Full output: `portable-tests.txt`. New coverage includes official-metadata
  contract/resumable HTTP downloads, range mismatch, corrupt hashes, insufficient
  disk, installation locking, stale sensors, browser loss, stale camera tickets,
  independent inference cancellation, observed-map-only planning, four seeded
  controller runs, forward-obstacle stops and video ordering/finalization.
- A real local HTTP exchange with a **stub vision server** sent image data and
  exercised `look_left` followed by `finish`. This verifies the image/action
  integration and bounded turn behavior, not Qwen recognition.
- Complete **scripted browser mission**, seed 137: 12 observations, **36.30 m**
  travelled, return home, **0.704 m** minimum simulator clearance, zero obstacle
  stop interventions, **84.375% map observed**. This percentage is simulated range
  coverage, not camera-view coverage or object-detection accuracy.
- **90 ordered video chunks**, finalized to WebM. Chromium successfully decoded
  the recorded file as **320 × 240**. Selected images and a JSON report persisted.
- A subsequent mission in seed 42, in the same browser session, stopped on injected
  stale range sensors with speed zero and a finalized recording. There were **zero
  JavaScript exceptions** in the passing browser test.
- The GUI's actual model download displayed the cloud proxy's **HTTP 403** failure;
  the model did not become ready and no scripted fallback was started.
- Browser results: `recon-browser-results.json`. GUI capture: `recon-ui.png`.
  Full run artifacts remain in `.local/data/runs/4df9f614a8ec45af93bd73d0e8873940`
  and sensor-failure episode `354e8de92fbc4290ba277bde2a6649d2`; bulk artifacts are
  excluded from the source archive.
- Python compilation, JavaScript syntax, shell syntax and Python dependency
  consistency checks passed. Vendored Three.js 0.180.0 was extracted only after
  verifying the npm tarball's SHA512 integrity.
- Orderly shutdown via the independent parent launcher's control socket succeeded.

During development, an early repeat-browser run lost its camera connection and
another hit the app heartbeat deadline under software rendering. The UI now
rejects stale poll responses across mission starts and limits rendering to 20 fps;
the complete repeated-session browser check passed after these changes. A legacy
happy-route test also exposed an overly tight 250 ms timing assumption; its
success-path budget was increased while dedicated deadline/failure tests retain
their short timeouts. Failures were not counted as successful missions.

## Earlier baseline retained

The original 35-test gate-fixture suite passed before recon work. Two HTTP-driven
fixture inspections completed in 28.23 seconds, with synthetic JPEGs, scripted
policies and kinematic FakeDrone movement (`fixture-smoke.json`). Optional MAVSDK
3.17.4 was installed to inspect/test its external-server API using stubs; no
native flight connection was exercised. Native camera byte-stream and SDF/model
preparation checks remain contract tests, not Gazebo rendering evidence.

## Unverified / blocked

- Hugging Face official metadata and weights: cloud proxy HTTP 403. Download logic
  is tested against a local server; real artifact retrieval, Qwen outputs and its
  paired-image check still need execution on an allowed network.
- Actual Mac/Metal, llama.cpp native compilation, Safari/MP4, local model latency,
  combined memory/swap and actual 8 GiB performance.
- Gazebo/PX4 native simulation, bridge compilation, realistic aircraft dynamics,
  local positioning, noisy/delayed sensors, full 3D navigation and dynamic obstacles.
- Camera-visible coverage, perception accuracy, exact camera/pose clock alignment,
  long-duration/offline operation and held-out model-driven mission acceptance.
- Physical flight, hardware suitability and recovery behavior. Virtual stop tests
  do not establish physical landing or autopilot recovery.

`docs/versions.json` contains candidate native commits, not Mac-validated release
pins. Cloud configuration is saved as a draft; publication and fresh-task
restoration are separate, unverified actions. Git publication does not change
the runtime validation results recorded here.

Reproduce automated checks with `./scripts/test-portable.sh`; browser checks and
Mac acceptance are documented in `README.md` and `handoff.md`.

## Clean source-package check

The source archive was extracted into a separate temporary directory and all
90 source hashes verified. A fresh virtual environment installed the locked
minimal dependencies; **all 52 tests passed again in 28.644 seconds**, with zero
failures/skips (`clean-copy-tests.txt`). The clean copy started recon mode through
the parent launcher, served the GUI and both offline Three.js modules, reported
an explicitly unavailable local model, and shut down with its control socket
removed. Documentation-only evidence additions followed this executable-source
check. The final export was generated twice with an identical SHA256; the exact
hash is in `dist/drone137-source.tar.gz.sha256`.

The updated cloud draft includes the official model metadata/storage domains
`huggingface.co`, `*.huggingface.co`, and `*.hf.co`. This preserves the package
manager preset. Saving did not change this running environment's network policy;
review/save and publish are still required before a new environment can use it.
