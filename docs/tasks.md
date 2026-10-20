# Task ledger

Status vocabulary: `not_started`, `in_progress`, `blocked`, `verified`.
Verified entries refer only to the host/profile/backend evidence named here.

The current first objective is [confined-space reconnaissance](recon-objective.md).
The A-series below records the original prototype/handoff work; its completed
fixture tests do not establish the new exploration or video capabilities.

| ID | Owner | Dependencies | Status | Output and evidence |
| --- | --- | --- | --- | --- |
| R01 | AI / development | Clarified objective | verified | Linux Chromium: seeded single-room Three.js world, onboard/overhead views and playable recording; plain JavaScript |
| R02 | AI / development | R01 | verified | Initial ideal-pose planar-range occupancy/frontier planner; randomized controller checks and rendered browser mission. Full 3D/noisy sensing remains pending |
| R03 | AI / development | R01–R02 | in_progress | Scripted exploration/return, video and receipt/pose events verified on Linux; real-model object response and exact exposure sync remain pending |
| R04 | AI + operator / Mac | R01, A05 | in_progress | Model manager/runtime/downloads and image-action interface implemented; HTTP stub verifies view changes; actual Qwen inference blocked by network and Mac access |
| R05 | AI + operator / Mac | R02–R04, native integration | not_started | Confined-space PX4/Gazebo dynamics, local-position navigation, sensor/failure tests, offline and resource evidence |
| R06 | AI + hardware lead | R05 | blocked | Aircraft/sensor suitability review and subsequent human build/test plan for confined spaces |

| ID | Owner | Dependencies | Status | Output and evidence |
| --- | --- | --- | --- | --- |
| A01 | AI / cloud | Empty repository | verified | `README.md`, `pyproject.toml`, locks, `docs/environment.md`; Python bootstrap on Linux x86_64 / cloud-dev |
| A02 | AI / cloud | A01 | verified | Contracts, executor, recorder, local UI, fake/replay adapters, independent heartbeat and process cleanup; portable tests on Linux x86_64 / cloud-dev with fake inference/camera/dynamics |
| A03 | AI / cloud then Mac | A01–A02 | in_progress | `adapters/`, `sim/`, `config/`, staged scripts; isolated HTTP/MAVSDK/camera contracts tested; native binaries, bridge compilation and end-to-end integration unverified |
| A04 | AI / cloud | A01–A03 accessible work | in_progress | Source export, checksum, locks and clean-copy bootstrap verified (see current validation report); model revision/hash resolution remains blocked by cloud egress and deferred to explicit Mac download |
| A05 | AI + operator / Mac | Source handoff | blocked | Needs access to actual Mac; run read-only preflight first |
| A06 | AI + operator / Mac | A05 | not_started | Real Qwen images, native camera/control and concurrent resource measurements |
| A07 | AI / Mac | A06 | not_started | M2–M4, failure suite, offline verification, held-out scenarios, physical-memory measurements |
| A08 | AI + hardware lead | Independent documentation | not_started | Original hardware scope retained in `docs/project-brief.md` and `hardware/README.md` |
| A09 | Human + AI | Mac virtual acceptance + lean budget | blocked | No construction or commissioning yet |
| A10 | Human + AI | A09 | blocked | No physical testing yet |
| A11 | AI + operator | A07 and pilot | not_started | Reproducible supported release and second-person installation |

The first handoff delivers a runnable portable implementation, not completion of
all A03–A04 integration/acceptance requirements. See `docs/validation.md` for exact
checks and the concrete remaining work.

Next acceptance work is real Qwen on the Mac, perception-directed missions, and
combined resource measurement, followed by noisy sensing/full 3D navigation. Hardware work remains
blocked until the new reconnaissance acceptance and resource gates pass.
