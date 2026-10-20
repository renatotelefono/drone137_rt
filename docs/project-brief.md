# drone137

## Whole-project plan: cloud development → Mac mini validation → drone build → flight testing

**Updated:** 20 October 2026  
**Scope:** Develop with Claude in a cloud workspace, move the program to the Mac mini, prove local-model simulation there, then build and test one drone.  
**Current state:** Planning and source review completed; no software build, Mac benchmark, assembled aircraft or flight test is claimed.  
**Available development machine:** Mac mini with **16 GB RAM** and approximately **200 GB total storage**; available disk space, chip and macOS version are not yet known.  
**Efficiency target:** Design the default program for an **8 GB Mac**, using the available 16 GB Mac for development; 8 GB compatibility remains an acceptance target until measured.  
**Start now:** Claude completes the cloud tasks A01–A04 in section 15 and produces a portable source handoff; lack of Mac access or free Mac disk space must not stop that work.  
**Runtime decision:** Qwen3-VL-2B-Instruct via native llama.cpp / llama-server, using Metal on Apple Silicon; current OnPremo requires additional capabilities for this job.  
**Hardware gate:** Build and physical testing start only after the actual Mac passes the local model and virtual inspection gates.

### Opening instruction for Claude

> Implement drone137 from this document. We are starting in a cloud workspace and will transfer the program to an available Mac mini with 16 GB RAM and about 200 GB total storage, with free space unknown. Design the default workload for an 8 GB machine: use the lean profile and explicit memory/storage budgets in section 8; do not spend extra memory merely because the development Mac has 16 GB. Start with A01–A04: create the portable application, adapters, meaningful tests, compact local assets, setup scripts and a reproducible source handoff. Do not require Mac access, Metal, model downloads, Gazebo installation or hardware to make useful progress in this first session. Test real integrations in the cloud only when the environment supports them, and label fixtures and mocked tests accurately. Prepare a separate native Mac validation path; cloud success cannot pass that gate. Preserve all hardware scope, but do not start construction or physical tests until the model and simulator work together on the Mac. Keep runtime inference local and use the selected open-source components. End each session with what changed, what was actually tested, the next task and the exact handoff commands.

## 1. Goal and project phases

Build an observation product operated with **one drone and one nearby computer**, with all image analysis and inspection decisions running locally. The first job is a short inspection of known gates/access points; agricultural observation can follow once the same workflow works on real footage.

The model uses camera images to choose whether to continue an inspection, revisit a predefined viewpoint or finish. PX4 performs stabilization and executes validated navigation commands. A small onboard video encoder may be part of the drone; the AI model stays on the Mac.

| Phase | What we do | Exit gate |
| --- | --- | --- |
| **0. Develop in the cloud** | Claude builds the portable application, integration contracts, test fixtures, local UI and setup/handoff scripts; runs available cloud checks | Reproducible source package and honest test report, with Mac-only checks explicitly pending. |
| **1. Run a successful simulation** | Simulator, camera, local vision model, inspection app and flight interface run together on the Mac mini | Real images cause meaningful model decisions and simulated movements; offline operation, failures and performance are measured. |
| **2. Build one drone** | Freeze a complete parts list, assemble the aircraft and integrate the camera/control links | Assembly/configuration records and successful propellers-off video, telemetry and command checks. |
| **3. Test it and prepare the pilot** | Establish normal flight, test the scripted route, evaluate real footage, then enable supervised model decisions | Repeatable inspections with recorded evidence, defined operating limits and a second-person installation test. |

**Required order:** cloud software development → local model on the Mac → model and simulator together → virtual acceptance → drone construction and bench commissioning → supervised physical tests → deployment. Hardware documentation may be drafted earlier; physical work remains after virtual acceptance.

The first product uses one supported aircraft configuration, one camera, daylight observations, a known route and an operator present. General autonomous exploration, unrestricted obstacle avoidance, swarms, custom flight-control neural networks and a new structural airframe are later projects. A dock, automatic charging and unattended operation are not prerequisites for this first product.

## 2. Instructions for the implementing AI

Build the software described here, starting with the cloud development milestone in section 10 and A01–A04 in section 15. Work towards an actual camera-to-model-to-flight demonstration on the target Mac. Implement real adapter code alongside deterministic fixtures; fixtures make cloud development possible, but only actual image inference and simulator integration can satisfy the Mac acceptance gate.

Production inference and mission operation must run on the same Mac mini without external APIs. Using Claude in the cloud to write software is part of development; do not make Claude, another hosted model, a remote vision service or an API key a dependency of the drone137 application. Internet access is acceptable for initial dependency/model downloads; subsequent operation must work offline. Use open-source application code, simulator, flight software and inference runtime, plus openly licensed model weights. The user's existing macOS/Metal host platform is outside the software we distribute.

The available development Mac's **16 GB RAM is confirmed by the user**, but **8 GB is the default design target**. Its approximately **200 GB storage is total capacity, not available space**. Detect chip, architecture, macOS version, genuinely available disk space and memory pressure when Mac access becomes available. Apple Silicon is the implementation assumption, not a confirmed fact; if the Mac is Intel, report the compatibility gap and validate a suitable native configuration before claiming support. Do not claim that the complete workload fits or runs in real time until measured; a lean-profile pass on 16 GB is not proof of actual 8 GB compatibility.

Implement Phase 0 and Phase 1 before hardware work. Keep simulation the default and physical transport disabled during both. Phase 2 adds a deliberately selected bench-only physical profile for H4/H5, with propellers removed; enable flight operation only after bench commissioning passes. AI work includes software, configuration, documentation and analysis; a human performs assembly, calibration and flights. No hardware purchase is required for the simulation demo.

Preserve progress in `docs/tasks.md` with task ID, owner, dependencies, status, output path and evidence. Continue useful cloud development while Mac storage or access is unavailable; leave Mac-dependent and hardware-dependent gates visibly incomplete. Every result must name the host, architecture, profile and whether real inference/camera/flight dynamics were exercised. A Linux CPU response does not establish Metal performance, and a mock drone does not establish simulator compatibility.

### Development environments

| Environment | Work to complete there | Evidence it can provide |
| --- | --- | --- |
| **Claude cloud workspace** | Repository, contracts, executor, recorder, local UI, fake/replay adapters, real adapter implementations, small world, tests and install/export scripts | Application logic and any real integrations supported by that host; never Mac resource or flight-readiness claims. |
| **Mac with limited free space** | Read-only environment/storage report, source review and lightweight application checks when space permits | Exact target specifications and a staged download/install plan; full validation remains pending until resources are available. |
| **Mac ready for the complete stack** | Native dependencies, actual local model, camera-enabled simulator, lean-profile combined workload and offline checks | Required Phase 1 evidence on the available 16 GB Mac, with the 8 GB design budget measured separately. |

The cloud environment may have no GPU, display, package-manager privileges or hardware acceleration. Detect capabilities instead of assuming them. Keep the default cloud bootstrap small; full PX4/Gazebo installation and model downloads are optional cloud integration checks. If unavailable, implement the adapters and document the unrun checks while continuing application work. Do not substitute a hosted inference API.

## 3. Runtime decision: OnPremo assessment

**Decision: keep llama.cpp / llama-server with Metal as the initial runtime for Qwen3-VL-2B.** OnPremo has useful memory-admission and structured-text features, but the inspected implementation cannot accept the camera images required by this project.

Assessment performed on 20 October 2026 from the official site, documentation and public source at commit `da82fbd0f9da6c3225b446d171dd695a50165d94`. This was a source review: OnPremo was not installed, compiled or benchmarked on a Mac for this assessment. [21][22]

| Requirement | OnPremo finding | Project decision |
| --- | --- | --- |
| Open-source runtime / commercial reuse | MIT OR Apache-2.0; model weights have separate licences. [22] | Compatible with the project's licensing direction. |
| Local Mac operation | Apple Silicon and Intel binaries are published; real inference is built with `backend-llama`, while the default workspace build uses a mock backend. [22] | Mac availability is documented; a successful mock response cannot count as a model test. |
| Camera-image input | Runtime chat content is a string; HTTP content is `Option<String>`; no image-content array or projector field is exposed. [23][24] | **Blocking for the initial vision pipeline.** An image encoded as text does not provide vision. |
| Multimodal execution | The backend tokenizes text and has no `mmproj`/`mtmd` image path in the inspected implementation. [23][25] | Underlying llama.cpp support does not automatically appear in OnPremo's adapter. |
| Apple GPU acceleration | The backend explicitly sets GPU layers to zero. [25] | Current inference is CPU-only; do not promise Metal acceleration from the Mac installer. |
| Mac memory awareness | Available memory is approximated as total RAM minus this process's RSS high-water mark; swap is unprobed. [26] | It does not reliably measure memory available while Gazebo and other apps run. Measure the complete workload independently. |
| Structured output | The real backend applies a grammar sampler; runtime validation remains the application's responsibility. [25] | Useful for bounded text decisions, but does not replace the flight executor's validation. |

**How to reconsider OnPremo:** require actual image input, vision-projector loading, correct image-dependent answers with identical text prompts, an explicit acceleration configuration, meaningful Mac memory measurements and tested timeout/cancellation behaviour. Verify the real backend and record the exact revision. Implementing those capabilities is a separate runtime-development milestone; it should not delay the first drone137 demonstration.

Keep a small `InferenceBackend` interface so a future OnPremo version can be evaluated without rewriting missions or flight control. Do not add a second text-only model to the MVP merely to use another runtime. The site labels the release 0.1.0 and says hardware certification is still pending; published fit estimates are not benchmarks of our simulator-plus-vision workload. [21][27]

## 4. Drones, hardware and complete-system costs

**Provisional first outdoor aircraft:** a conventional 450–500 mm quad frame, a **MicoAir743-Lite** flight controller with a compatible Bluejay ESC stack, four matched motors/propellers, GPS with compass, battery, telemetry and a manual-control receiver. PX4 lists this exact controller family as manufacturer supported; its guide identifies upstream release support from v1.17. Confirm the actual board revision, firmware target and peripherals before ordering. [1][2]

This meets the requirement to **build the aircraft ourselves using open-source flight software**. Editable manufacturing files and open licences for every purchased circuit board have not been established. Do not describe the entire aircraft as fully open hardware.

| Option | Price or planning allowance, USD | Role in drone137 |
| --- | --- | --- |
| **Self-build with MicoAir743-Lite/PX4** | **$300–450 aircraft allowance**, including one battery, basic telemetry and onboard manual-control receiver; estimate, not a validated shopping cart | Preferred budget direction after the simulator works. The controller/ESC product family is listed at $46.99–88.99 depending on variant. [1] |
| **Holybro S500 V2 development kit** | **$549 listed kit price**; battery, manual controls, charger and camera/video extra | Alternative when reducing assembly/integration effort matters more than the lowest parts cost; includes Pixhawk 6C, GPS and telemetry. [3] |
| **Seeed ESP-FLY DIY kit** | **$59.99 listed kit price**; camera/video extra | Optional inexpensive indoor electronics experiment. Its firmware is GPL-3.0, but the supplied platform has no altitude hold, GPS or autonomous navigation; it needs a different control integration. [4][5] |

Prices were checked on 20 October 2026 and exclude destination-specific shipping and taxes. The self-build allowance includes frame, flight controller/ESC, motors/propellers, GPS/compass, one battery, basic telemetry, onboard receiver and small wiring/mounting items. It excludes the handheld controller, charger, camera/video system, Mac, labour and spares. Selecting a long-range link may increase the allowance; a basic nearby Wi-Fi connection does not establish field coverage.

Use a purchased frame initially: Holybro lists the S500 V2 frame alone at $42. Print camera mounts and housings first; a custom structural frame is a later optimisation. [6]

A flight controller and telemetry radio are not a complete camera-to-Mac system; PX4 documents video through a companion computer/encoder. Keep AI on the Mac even if a small onboard device is needed for encoding. [7]

### Parts to select for the self-build

These are **planning allowances, not supplier quotes or a validated matched kit**. The exact motor/propeller/battery combination, mounting, current draw and firmware target must be checked before ordering.

| Aircraft item | Initial candidate / requirement | USD allowance |
| --- | --- | ---: |
| Frame | Purchased S500 V2 frame; listed price $42 [6] | 42 |
| Flight controller + ESC | MicoAir743-Lite with compatible Bluejay stack; confirm exact variant [1][2] | 75–90 |
| Propulsion | Four matched motors and propellers selected for the frame and intended payload | 60–90 |
| Navigation | GPS plus compass compatible with the exact board | 20–40 |
| Battery | One pack matched to propulsion, power limits and connectors | 35–55 |
| Computer-control link | Basic nearby telemetry link for prototyping; field link selected after range testing | 20–35 |
| Manual-control receiver | Compatible ExpressLRS receiver; handset budgeted separately | 20–30 |
| Electrical/mechanical parts | Wiring, connectors, power accessories and mounts | 20–35 |
| **Component subtotal** | Before camera and shared ground equipment | **292–417** |
| **Rounded aircraft allowance** | Retains a modest margin; substitutions can change it | **300–450** |

Do not assume a processor name such as H743 or F405 establishes PX4 compatibility: record the exact supported board, revision and firmware target. Bluejay is an open-source ESC firmware candidate and ExpressLRS is an open-source radio-control candidate; verify their compatibility with the actual purchased hardware. [34][35]

### Camera and complete-system budget

**First camera candidate to bench-test:** Raspberry Pi Zero 2 W + standard Camera Module 3, with a suitable Zero camera cable, microSD card, regulated power and a printed mount. Manufacturer starting prices are $15 for the board and $25 for the camera; the board documents a camera connector, Wi-Fi and H.264 encoding. These facts establish a plausible component choice, not a proven drone video system. [29][30]

Use `rpicam-apps`/libcamera and a local video stream into GStreamer on the Mac. A local Wi-Fi network can connect the devices without internet; validate a direct access-point configuration so an additional router is not mandatory. Start with modest resolution/frame rate and verify the installed OS/camera stack on the exact board. All AI remains on the Mac. [31][32][33]

| Additional item | Planning allowance, USD | Included work / boundary |
| --- | ---: | --- |
| Camera/encoder package | 70–120 | Camera, board, cable, storage, power conversion, mount and basic local video connection; unvalidated estimate. |
| Handheld controller + charger | 120–180 | Shared development equipment, with transmitter batteries/cables allowed for; select exact models. |
| Spare battery/propellers/small parts | 50–100 | Initial development spares. |
| **DIY prototype equipment total** | **540–850** | Aircraft allowance plus the three rows above; excludes Mac, tax, shipping, labour and any upgraded field radio. |

For the $549 Holybro kit, add its missing flight battery, manual-control equipment, camera/video and spares separately; do not apply the DIY total to that kit. Validate live video and telemetry concurrently before freezing either aircraft BOM. Basic Wi-Fi is a nearby prototype link, not a promise of agricultural-field or whole-building coverage.

Off-the-shelf chips, boot firmware and board manufacturing files are not all verified open. Our code, chosen controllable flight/runtime components and their licences must be documented; do not label the whole physical device fully open hardware. Preserve the user's requirement to assemble and repair it from available components.

## 5. Software to use

| Component | Initial choice | Reason and licence evidence |
| --- | --- | --- |
| Aircraft dynamics and camera | **Gazebo Harmonic**, one PX4 X500 camera model | Integrates with PX4; use a small scene and one rendered sensor. Gazebo core is Apache-2.0. [8][9] |
| Autopilot | **PX4 SITL** | Same flight-software family as the provisional real aircraft; BSD-3-Clause. [10] |
| Flight API | **MAVSDK-Python** with a compatible native `mavsdk_server` | Python application integration; BSD-3-Clause. [11][12] |
| Local model | **Qwen3-VL-2B-Instruct GGUF**, `Q4_K_M` language model and `Q8_0` vision projector | Official Qwen weights, Apache-2.0; the model card documents Apple Silicon/Metal support. [13] |
| Inference | **llama.cpp / llama-server**, native Metal on Apple Silicon | MIT; separate process with a loopback HTTP endpoint; OnPremo decision in section 3. [14] |
| Application | Python, a small local HTTP API and plain HTML/JavaScript UI | Keep dependencies few; choose Apache-2.0 for our original code and retain upstream notices. |
| Persistence | JSONL events, JSON summaries and JPEG evidence files | No separate database service required for the demo. |
| Aircraft setup | **QGroundControl**, commissioning/diagnostics in Phase 2 | Open-source setup and calibration tool; inspect the selected release's Apache/GPL terms and bundled dependencies. [28] |
| Physical camera software | **rpicam-apps / libcamera** | Phase 2 candidate; rpicam-apps is BSD-2-Clause. [31][32] |
| Video reception | **GStreamer** | Local stream decoding; LGPL core, with exact plugins/dependencies recorded. [33] |
| ESC / manual radio | **Bluejay / ExpressLRS**, on compatible parts | Phase 2 candidates with open-source firmware; audit exact versions. [34][35] |

Avoid adding ROS 2, Unreal, Kubernetes, a cloud backend or an agent framework to the initial implementation. Do not make Docker Desktop a prerequisite. Use native processes with explicit startup/shutdown ownership.

### Native Mac compatibility is the first Mac gate

Perform this after the cloud handoff, when the Mac has enough free working space. It must not block the cloud tasks.

Current PX4 `main` documents native Intel and Apple Silicon setup with Gazebo Harmonic, using a locked pixi/conda-forge environment. That documentation belongs to the development branch, not proof that an older stable release has identical Mac support. Pin the exact working PX4 commit and its submodules after testing. [15]

Follow that revision's macOS setup script and record its required tools. Keep the application's Python environment separate from PX4's. If MAVSDK-Python's bundled server does not execute natively, build the matching `mavsdk_server` for the host and connect Python to it; upstream documents external-server operation. [11]

Try the Gazebo GUI for initial inspection, then prefer the simulator server plus our camera viewer. Gazebo documents macOS GUI limitations; removing the GUI does not remove the cost of rendering camera frames. A physics-only demonstration does not satisfy the visual-model milestone. [16]

## 6. First simulation demonstration

Create one small courtyard with two gates, a takeoff/landing pad, and predefined observation positions connected by clear flight corridors. Use simple geometry and locally stored textures.

The operator starts an inspection. The simulated drone takes off, flies to the first observation position, stops and sends an actual camera image to the local model. The model reports `open`, `closed` or `uncertain` and selects a permitted next action. An uncertain image can cause a move to a second predefined viewpoint and another observation; a conclusive image can cause the inspection to continue. The drone then visits the second gate and lands at the pad.

Change gate appearance between episodes, including clear open/closed states and an initially obscured view. Save the image, model output, accepted action and resulting movement together. The demonstration must show that model output can change the next flight segment.

This evaluates **visual inspection and bounded navigation decisions**. PX4 still performs stabilization and flight execution. Low-level neural motor control would be a separate experiment with different data and acceptance criteria.

## 7. Architecture and interfaces

### Process ownership

Use three application responsibilities plus upstream processes:

1. **Launcher/watchdog:** starts owned processes, tracks health using host monotonic time and shuts them down cleanly.
2. **Flight executor:** sole owner of MAVSDK commands; validates proposed actions, tracks mission state and monitors completion. Its execution must not block on inference or UI requests.
3. **Local app:** camera acquisition, model requests, UI and run recording; model inference initially runs in `llama-server`, behind the runtime adapter.

In simulation, PX4, Gazebo and `mavsdk_server` run as separately supervised processes; physical mode runs PX4 on the aircraft and omits Gazebo. Bind local services to loopback. Do not add telemetry uploads or runtime CDN dependencies.

### Adapter boundaries

| Interface | Required behaviour |
| --- | --- |
| `DroneAdapter` | Connect to the explicitly configured simulator initially, or a commissioned physical vehicle later; read telemetry; take off, go to named waypoints, hold, return and land; distinguish accepted/completed/failed status. |
| `FrameSource` | Produce actual camera images with frame ID, episode ID, timestamps, dimensions and camera identity; retain only the newest frame. |
| `InferenceBackend` | Accept a local image plus text, expose capabilities/model identity, and return raw output/timing; start with llama-server and keep future runtime adapters optional. |
| `DecisionPolicy` | Accept an observation and permitted actions; return a typed decision. Implement `ScriptedPolicy` for integration and `QwenPolicy` for evaluation. |
| `RunRecorder` | Associate observations, raw responses, validation outcomes, movement results and timing in an inspectable local run directory. |

MAVSDK does not provide the simulator image stream automatically. Implement a camera adapter using the selected Gazebo image topic, or its documented GStreamer/RTP stream. Prefer a path preserving sensor timestamps; if only receiver timestamps are available, label them accurately and measure the missing capture-to-receipt delay. Gazebo's documented stream uses RTP/H.264 on UDP port 5600, but verify it on the pinned model/revision. [8]

Use a single latest-frame buffer, not a queue of old images. Keep inference concurrency at one and drop superseded work. After a request times out, confirm cancellation or wait for its worker to finish before submitting another inference; never accumulate hidden server work. Flight supervision continues independently. Store sensor simulation time and host monotonic receipt time in separate fields; never subtract timestamps from different clocks. Establish their mapping before reporting capture age, or explicitly report receipt age and the remaining uncertainty. If Gazebo Python transport bindings do not work in the chosen environment, isolate a small native image bridge behind `FrameSource`; do not introduce an entire robotics middleware stack for it.

### Flight commands

Begin with MAVSDK actions/repositioning to named, predefined waypoints, using `goto_location` where supported by the pinned PX4/MAVSDK combination. Test command acknowledgement and actual arrival separately. The API takes absolute altitude, so convert from the mission's local coordinates explicitly and verify the home reference. [17]

Store mission geometry in one documented local frame, with explicit units, origin and yaw convention. Add a meaningful conversion check for Gazebo/world coordinates, local navigation coordinates and global waypoint altitude; do not silently mix ENU, NED, relative height and altitude above mean sea level.

Only one movement may be active. A waypoint name maps to a fixed position and an allowed route segment. The model does not invent coordinates or obtain raw motor control. Restrict movement to the clear corridors in the authored world; generic obstacle avoidance is outside this first demo.

Count arrival only after a configurable position tolerance and settling condition are met: initially within 0.5 m horizontally and 0.3 m vertically, moving below 0.2 m/s for one second. Give each route segment a finite travel timeout sized to its length and speed limit. These are simulation starting values to test; capture images after settling, not immediately after acknowledgement. Derive separate physical-aircraft tolerances from measured positioning and image quality; standard GPS must not be assumed to meet the simulator tolerances.

Use actions/mission execution first. If Offboard mode proves necessary, document why and implement its separate watchdog requirements: MAVSDK can resend setpoints at 20 Hz, so a stopped Python decision loop does not by itself imply loss of the autopilot's command stream. [18]

### Observation and decision contracts

Each observation envelope must include:

- `episode_id`, `request_id`, `frame_id`, capture/receipt timestamps and request deadline.
- Image data, ordinary vehicle pose/health telemetry and current mission state.
- Current inspection target, named allowed viewpoints and allowed next actions.

The model returns a small object such as:

```json
{
  "observation": "uncertain",
  "action": "recheck",
  "target_view": "gate_a_side",
  "reason": "The gate opening is obscured from this view."
}
```

Use enums and reject unknown fields, invalid targets or oversized outputs. The app attaches the trusted request/episode/frame envelope to the returned decision; do not trust a model-generated timestamp or identifier as proof of freshness. A model's self-reported confidence is not a calibrated probability.

Allowed model actions:

| Action | Defined meaning |
| --- | --- |
| `continue` | Record this finding and request the next predefined inspection target; after the final target, return to the pad and land. |
| `recheck` | Move to an allowed alternative view of the same target; permit at most one recheck per target initially. |
| `hold` | Stay at the current observation position while the executor enforces a finite timeout. |
| `finish` | End the inspection and follow the predefined return-to-pad-and-land sequence. |

The operator controls start, pause and land. Start/takeoff requires readiness checks for the active profile: simulator readiness in Phase 1 and commissioned-aircraft readiness in Phase 3; bench-only profiles cannot start a flight. Start/takeoff is not a model tool. Operator `land` requests landing at the current position, immediately cancels pending model decisions and has priority over the inspection sequence. Model `finish` follows the predefined route back to the pad before landing. Author the initial scene with clear ground beneath the allowed flight corridors and test both behaviours.

### Validation and failure behaviour

Reject decisions for a different episode, superseded request, stale observation, expired deadline, invalid target, unavailable position estimate or wrong mission state. Cancel pending decisions after pause, reset or stop. Never execute raw model text as code or shell commands.

Initial configurable settings, to be measured rather than presented as proven limits:

- Lean-profile camera target: 320 × 240, up to 2 frames/s; analyse one fresh frame while holding at a viewpoint. Use the actual model encoder dimensions for memory accounting; a small input JPEG alone does not guarantee a small encoder workload.
- Maximum frame age at request dispatch: 1 second, using the best available timestamp source.
- Inference timeout: 6 seconds; accept a response only while the drone still holds the corresponding observation position and the request remains current.
- At most one recheck and a finite observation/mission timeout.
- Initial scene speed limit: 1 m/s, with a small configured flight volume and fixed inspection heights.

On model timeout or malformed output, retain position and record an unresolved observation; use the configured recovery/landing path after the finite timeout. A stale frame cannot authorize another inspection movement. Loss of telemetry or executor health must trigger the tested simulator recovery behaviour and invalidate the run's autonomous-success result.

Test app/executor death explicitly. A surviving MAVSDK server can continue heartbeats independently of the application. The launcher must manage that lifetime, and the configured PX4 loss behaviour must be verified in the actual simulated flight mode; setting a parameter is not evidence that it works. During this test, keep PX4 and Gazebo alive while stopping/disconnecting the orphaned SDK server, observe the vehicle response, and only then clean up the simulator processes.

## 8. Design for 8 GB RAM and uncertain free disk space

### Default lean profile

Use one default profile named `lean-8gb` on both the available 16 GB Mac and any later 8 GB test machine. The name expresses an engineering target; it is not a passed compatibility claim. Higher-resource profiles must be opt-in and cannot be used to hide a failure of this default.

Use the official files `Qwen3VL-2B-Instruct-Q4_K_M.gguf` and `mmproj-Qwen3VL-2B-Instruct-Q8_0.gguf`. Their listed download sizes are 1.11 GB and 445 MB, approximately 1.6 GB together; these are file sizes, not runtime memory requirements. Save model revision, file hashes, runtime commit and licence locally. Download only this pair when requested, then launch with local file paths. [13][36]

| Resource | Initial default | Implementation requirement |
| --- | --- | --- |
| Model | One Qwen3-VL-2B instance, Q4_K_M plus Q8_0 projector | No second reasoning model, full-precision copy or duplicate model server. |
| Context / output | 2,048-token context target; at most 128 generated tokens per decision | Budget for image tokens and prompt overhead; verify the complete request fits. Keep mission history as compact application state, not an expanding conversation. |
| Image inference | One image and one request in flight | Latest-frame buffer of size one; discard superseded frames/results and release decoded image buffers. |
| Camera | 320 × 240 at up to 2 frames/s initially | Inspect only after settling. Check model-side resize/token settings; raise resolution only if measured accuracy requires it. |
| Simulation | One drone, one small authored scene and one camera | Run the simulator server with sensor rendering; use our small viewer and leave the Gazebo GUI closed for acceptance measurements. |
| Application | Small Python services and plain HTML/JavaScript | No Electron shell, ROS stack, database server, vector database, containers or background agent framework required. |
| Evidence | Selected inspection JPEGs and compact events | Continuous video off; default project run-data limit 1 GB. If full, pause recording/new runs and request explicit project-data cleanup or another data path. |

The executor/watchdog must remain responsive during inference. Use asynchronous I/O and bounded queues; do not create an unbounded worker pool. Measure structured-output support on the pinned llama.cpp revision and validate every decision in the application.

### Memory budget and honest verification

**Initial engineering goal:** keep the combined incremental physical-memory footprint of simulator, PX4, SDK, model, app and viewer at or below approximately **5 GiB**, leaving roughly 3 GiB of an 8 GiB machine for macOS and working headroom. This is a proposed budget, not a measured requirement or guarantee; actual OS usage and shared GPU memory vary. Do not infer memory fit from the 1.6 GB weight download.

| Component group | Provisional budget | If exceeded |
| --- | ---: | --- |
| llama-server, vision encoder and inference buffers | 2.5 GiB | Inspect image-token limits, context, allocations and duplicate loads before changing models. |
| Gazebo, PX4, image bridge and MAVSDK server | 1.75 GiB | Simplify the scene, reduce camera rendering and remove unused processes/assets. |
| Application and minimal viewer | 0.5 GiB | Inspect retained frames, queued work, logging and UI growth. |
| Shared working margin | 0.25 GiB | Record transient peaks; do not hide them with averages. |
| **Combined design budget** | **5 GiB** | Keep 8 GB support pending if it cannot be met. |

Record a baseline before launch, process physical footprints where available, system memory pressure, compression, swap growth and peak usage during image encoding, model loading and complete missions. Explain the accounting method: summing RSS can count shared pages more than once, and Apple GPU allocations share system memory. Sustained swap growth, memory pressure, OOMs or growing resident memory fail the efficiency target even if one route eventually finishes.

Run at least a 30-minute repeated-mission resource check after the functional smoke suite passes, to detect retained frames, histories and logs. This is a proposed endurance check for resource use, not a flight certification. A low-memory configuration or Linux memory-limit test on a 16 GB host does not reproduce an 8 GB Mac's Metal, OS or simulator behaviour. Mark actual 8 GB compatibility `unverified` until the complete workload is demonstrated on appropriate hardware; do not launch artificial memory-pressure processes to simulate it.

If the default is too slow or inaccurate, change one setting at a time and record both resource and accuracy effects. A smaller vision model can be evaluated as a documented fallback with its licence and actual image support checked; do not silently replace visual inference with scripted labels. The first physical prototype may proceed after the actual available Mac passes the complete virtual gate and the reported efficiency checks, while actual 8 GB validation remains a separately visible open item. A budget miss keeps `lean_memory_budget` failed; document optimizations or a revised target separately instead of relabelling a failed result as passed.

### Storage-aware installation

Treat the reported 200 GB as total disk capacity. Before each large installation, download or build, measure free space on both the system volume and the configured data/build volume, estimate the operation's peak additional space, and preserve OS headroom. Detect existing usable dependencies/assets to avoid duplicate installs.

| Disk item | Initial planning allowance | Policy |
| --- | --- | --- |
| Source, small assets and application environment | 0.5–2 GB; estimate | Keep the cloud handoff compact; do not bundle environments or downloaded dependencies. |
| Selected model/projector | Approximately 1.6 GB of weights [36] | One verified copy; allow temporary download space, resume interrupted downloads, verify hashes and rename atomically. |
| PX4/Gazebo/native dependencies and builds | 10–25 GB provisional allowance, potentially higher | Measure exact selected packages/builds; install only when space is available and reuse the tested build. |
| Run evidence | 1 GB default cap | No unlimited video or silent retention growth. |
| System headroom | 10 GB provisional reserve | Configurable project policy, not an Apple-published minimum; report if current free space is below it. |

Until the installer has a measured manifest, use roughly **30–40 GB free space** as a planning allowance for the complete development setup including headroom, not as a verified minimum. Existing tools may reduce additional space; build intermediates may increase it. Insufficient space blocks only the affected install/run, not cloud development or a lightweight handoff.

Expose `DRONE137_DATA_DIR` for models/runs and `DRONE137_BUILD_DIR` for rebuildable native work, with documented project-owned defaults; allow an already available external SSD when the user chooses that location. Some package managers still use the system volume, so an external path does not waive the system-space check. No automatic deletion of unrelated files, global caches, existing user recordings or other projects. Cleanup commands must preview exact project-owned targets and require an explicit cleanup invocation. Do not download all quantizations or full-precision weights just to obtain the selected model.

## 9. Repository and operator commands

| Path | Contents |
| --- | --- |
| `README.md` | Setup, start, stop, expected first demonstration and measured host requirements. |
| `pyproject.toml` and lock file | Small application dependency set and reproducible environment. |
| `app/` | API, UI, mission state machine, executor, watchdog and recorder. |
| `adapters/` | MAVSDK, camera and local-model integrations. |
| `schemas/` | Observation, decision, mission and event contracts. |
| `sim/` | Small courtyard world, camera configuration and scenario generator. |
| `config/` | Mission waypoints, limits, process endpoints and local paths. |
| `scripts/` | Separate cloud/Mac bootstrap, diagnostics, staged dependency/model download, start/stop, evaluation and handoff export. |
| `tests/` | Contract/failure tests and simulator integration checks. |
| `hardware/` | BOM, wiring diagram, component revisions, weight/power budget, assembly photos and commissioning records. |
| `docs/` | Architecture, runtime decision, pinned versions, environment/storage reports, benchmarks, task ledger, cloud-to-Mac handoff, pilot and deployment records. |
| `runs/` | Ignored by Git; captured images, events, model replies, flight logs and summaries. |
| `THIRD_PARTY_NOTICES.md` | Component/model licences, source references and redistribution notices. |

Provide these entry points; they are implementation requirements, not commands already supplied by this document:

```bash
# First Claude cloud session: small dependencies, no automatic model/simulator download.
./scripts/bootstrap-cloud.sh --minimal
./scripts/doctor.sh --profile cloud-dev
./scripts/test-portable.sh
./scripts/export-handoff.sh

# Later, on the Mac: inspect first; perform large installs only when space permits.
./scripts/doctor.sh --profile lean-8gb --preflight-only
./scripts/bootstrap-macos.sh --minimal
./scripts/install-runtime.sh --profile lean-8gb
./scripts/download-model.sh --profile lean-8gb
./scripts/check-vision.sh --profile lean-8gb
./scripts/install-sim.sh --profile lean-8gb
./scripts/doctor.sh --profile lean-8gb
./scripts/run-local.sh --profile lean-8gb --mode sim --scenario courtyard --policy scripted
./scripts/run-local.sh --profile lean-8gb --mode sim --scenario courtyard --policy qwen
./scripts/evaluate.sh --suite smoke
./scripts/evaluate.sh --suite resources --duration-minutes 30
./scripts/stop-local.sh
```

Implement preflight with the tools already available on the host; it must not install Python, compilers or a package manager merely to report free disk space. `doctor` must identify chip/RAM/OS, free space per relevant volume, current memory pressure, native binary architecture, model/projector presence, dependency versions, ports and camera/control availability. `--preflight-only` performs read-only checks and reports pending components without installing them. Bootstrap must reuse installed dependencies and explain required host changes. Installers must check estimated peak disk needs and the configured reserve before downloading. Record exact successful commits/versions in `docs/versions.json`; do not leave production launch scripts fetching a moving `main` branch.

`install-runtime` obtains or builds the pinned native `llama-server` with the supported Mac acceleration backend. `check-vision` runs actual inference on two visually distinct local test images with identical text prompts and saves the results. `install-sim` installs/builds the selected PX4/Gazebo stack and a compatible native MAVSDK server when the Python package's bundled binary is unsuitable. Each staged installer applies the same disk-space check and records its native architecture and installed size.

### Transfer from cloud to Mac

Deliver a Git checkout or a source archive, with `docs/handoff.md` listing the exact source revision/archive checksum, tested cloud commands, unresolved checks, required Mac commands and selected resource profile. The source package contains application code, small scene assets, tests, licence notices, lockfiles, configuration templates and dependency/model manifests. Use relative paths and per-host configuration. Do not embed credentials, cloud absolute paths or the cloud workspace's virtual environment.

Exclude `.venv`, dependency caches, compiled Linux binaries, native build directories, downloaded model files and bulk run evidence from the default source handoff. Models may be transferred separately as an optional verified asset package if already available; never make re-downloading an existing verified copy mandatory. Recreate native environments and binaries for the Mac, retaining separate host-specific lock/build information where needed. Target a source-only handoff under 250 MB and report the actual size; this is a project size goal, not a reason to omit necessary source or licences.

The cloud fixture mode must be explicit (`cloud-dev`/fake adapters), visibly labelled and unavailable as a silent fallback in acceptance runs. Start/end reports must record whether the selected model, rendered camera and flight dynamics were real. A green portable test suite completes the cloud milestone, not Phase 1.

The UI needs only live camera, vehicle/mission status, current observation and accepted action, start/pause/land controls, plus a local report link. Use a simple local top-down mission view if useful; no internet map dependency.

Add a `--mode sim` default and separate named physical profiles in later phases. A physical profile records the intended vehicle identity, link endpoints, camera calibration and tested limits; the application must not silently connect to the first available aircraft. Keep firmware configuration and calibration backups per unit.

## 10. Cloud development and local simulation milestones

| Milestone | Build | Evidence required before proceeding |
| --- | --- | --- |
| **C0. Cloud implementation** | Contracts, executor/watchdog, recorder, small UI/world, real adapter code and deterministic fake/replay adapters | Meaningful checks for stale/invalid decisions, operator priority, command lifecycle, bounded frames and owned-process cleanup; report the actual host. |
| **C1. Portable handoff** | Staged Mac scripts, version/asset manifests, resource profile and source export | Compact handoff with exact next steps; any unsupported cloud integrations and all Mac-only acceptance checks remain pending. |
| **M0. Mac preflight** | Identify native architecture and available resources; install only required components when disk permits | Actual host/storage report and verified native binaries/model pair; use the lean profile. |
| **M1. Local vision and native simulation** | First prove real Qwen image responses, then PX4/Gazebo camera and MAVSDK control with the model loaded concurrently | Image-dependent answers, rendered sensor frame and scripted takeoff/land; record model/host versions and combined resource measurements. |
| **M2. Scripted inspection** | Small world, two gates, named viewpoints, camera adapter, executor and recorder | One complete route with actual image capture, bounded movements, return and landing; no fake camera frames. |
| **M3. Model-directed inspection** | Qwen policy, typed decisions and alternative observation path | A changed/obscured gate leads to an appropriate changed observation and a real alternative flight segment. |
| **M4. Virtual acceptance** | Failure handling, held-out scenarios, resource limits, offline run and repeatable install | Stale camera, invalid JSON, timeouts, telemetry loss and executor death handled; complete suite and resource report, with no silent mock fallback. |

Cloud implementation and Mac validation are separate deliverables. Build enough UI to inspect the integration; spend the initial session on the contracts, executable code and handoff. Run a real cloud model/simulator check if practical, but do not install a large stack just to pass a mock demonstration.

If M0 or M1 is blocked by Mac access or disk space, finish the cloud work and leave a concrete handoff instead of pretending the Mac test passed. If the native stack fails after installation, produce the smallest reproducible failure and resolve it before advancing Mac acceptance. A Gazebo rendering failure may justify evaluating another simulator, but document added camera/control integration work and preserve the interfaces; a physics-only substitute cannot satisfy the visual milestone.

**Phase 1 exit:** M1–M4 and the lean-profile memory-budget check pass on the actual Mac, the local model changes real simulated movements, and the report includes measured efficiency results. Record actual 8 GB validation separately if the available test machine has 16 GB. Only now may Phase 2 construction/commissioning start.

## 11. Phase 2: build and commission one drone

Complete the actual Mac simulator gate before starting aircraft construction, commissioning or physical tests. Draft the BOM and camera shortlist as documentation during software development, then freeze the configuration and build one unit after Phase 1 passes.

| Step | Work | Required deliverable / gate |
| --- | --- | --- |
| **H1. Freeze one configuration** | Select exact controller/ESC, frame, propulsion, GPS/compass, battery, manual radio, telemetry and camera components | `hardware/bom.csv` with quantities, exact variants, source URLs, price dates and substitutes; no unnamed essential parts. |
| **H2. Check integration** | Verify mounting, connectors, voltages, current/power provision, mass/payload and firmware targets | Wiring diagram and weight/power budget, with unresolved assumptions clearly marked. |
| **H3. Assemble** | Human assembles the standard airframe and camera mount | Build record and photographs; serial/revision list; mounting and connector inspection. |
| **H4. Configure** | Use QGroundControl and the board's documented setup procedure; retain parameter/firmware backups | Sensor orientation, power sensing, navigation and manual-control setup recorded for this aircraft. |
| **H5. Bench-check** | With propellers removed, verify correct vehicle identity, telemetry, camera freshness and command routing concurrently | Actual Mac logs and frames; loss/reconnect behaviour observed; physical profile ready for controlled flight testing. |

Keep stabilization and navigation on PX4. The Pi camera board, if used, encodes/transmits images; it does not need to run the local model. Manual control is a separately verified recovery path, not a replacement for validating the computer link. Radio, camera or battery substitutions require the relevant commissioning checks again.

**Phase 2 complete:** one assembled, documented aircraft passes bench commissioning; this does not yet establish flight reliability or model performance outdoors.

## 12. Phase 3: physical testing and inspection pilot

Use a suitable test area and a human operator responsible for the physical flights. Set the site's operating conditions before testing; use simulation/bench tests for induced failures that cannot be exercised appropriately in flight.

| Step | What runs | What must be recorded |
| --- | --- | --- |
| **T1. Normal aircraft flight** | Human flies without model control, then checks supported position/hold/return/landing behaviour | Flight logs, positioning, payload effects, usable camera views and manual takeover. |
| **T2. Scripted route** | The application executes the same bounded route concept used in simulation | Arrival/settling behaviour, real link coverage, frame age, command failures and usable flight duration. |
| **T3. Real-image evaluation** | Local model analyses independently labelled footage without commanding the aircraft | Open/closed/uncertain findings, misses, false alerts and latency across the intended lighting/views. |
| **T4. Advisory operation** | Model recommends rechecks/continuations; operator reviews while the aircraft follows the validated control procedure | Proposed actions and whether an operator accepts them; no hidden substitution of operator judgement in reported model scores. |
| **T5. Supervised model decisions** | Executor accepts only permitted model actions, with immediate operator priority | Complete image → decision → validation → command → movement evidence, including interventions and unsuccessful runs. |
| **T6. Repeated pilot** | One site, one inspection job, fixed hardware/software configuration | Reproducible inspections, actual delivered cost and a deployment trial by a second person. |

Begin with at least 20 supervised complete inspections and at least 100 separately labelled real observations held out from prompt tuning. These are proposed pilot evidence targets, not a claim of statistical certification. Set acceptable misses/false alerts and operator workload with the pilot owner before reviewing results. Record unclear observations rather than forcing a binary answer.

For every configuration, verify behaviour for camera loss, telemetry loss, application/executor exit, low battery, stale decisions and operator pause/land. Define which checks happen in simulation, on the bench and in controlled flights. Do not copy simulator failure settings or sub-metre arrival tolerances into a physical profile without measured evidence.

**Phase 3 complete:** the supported inspection works repeatedly within documented conditions, failures have explicit outcomes, and someone other than the developer can install and run it using the delivered instructions. Larger fields, changing routes and unattended operation require further validation.

## 13. Evaluation and acceptance

These are **proposed acceptance checks, not achieved results**.

Keep scenario truth in the evaluation harness only. The model and mission policy receive rendered images and ordinary telemetry; they must not receive the simulator's gate-state variable, object labels, hidden scenario seed or an answer encoded in filenames. Separate prompt-tuning scenarios from the evaluation set.

Start with at least 20 complete episodes spanning clear open/closed gates and initially obscured observations. Treat this as a smoke evaluation, not statistical proof of real-world reliability. Report counts and failure examples, not only a percentage.

Record:

- Route completion, correct/incorrect/uncertain observations, rechecks and operator interventions.
- Collisions, flight-volume violations and any rejected actions.
- Frame age, model latency, action acceptance and actual movement completion times.
- Simulator real-time factor and peak memory with simulator and inference running together.
- Any fallback or timeout, clearly distinguished from model success.

Initial performance goals: sustained simulator real-time factor at least 0.9, useful visible camera updates and model decision p95 at or below 5 seconds on the recorded host. Apply the `lean-8gb` profile and section 8's memory/retention checks; include transient loading/encoding peaks and the repeated-run trend. Revise a setting only with measured results and an explanation of resource and accuracy effects. Failing a latency or memory goal must remain visible in the report.

Report statuses separately: `cloud_implementation`, `mac_virtual_acceptance`, `lean_memory_budget`, `actual_8gb_validation`, and `hardware_gate`. A cloud or 16 GB result cannot populate `actual_8gb_validation` as passed. Until real 8 GB hardware is available, record the existing host's footprint evidence and leave that final compatibility status unverified.

Compare the scripted route with the model policy on the same scenario suite. For paired scenes differing only in gate visibility/state, save the resulting observations/actions so the team can inspect whether the model contributes to the inspection. A successful synthetic scene is evidence for integration; it does not establish real-field accuracy or flight readiness.

## 14. Deployment, commercial reuse and support

The eventual offer is the assembled observation kit, open-source application, installation and support. A release supports one tested combination first.

| Deliverable | Required contents |
| --- | --- |
| Local deployment bundle | Small source/application package plus separately managed model/native assets, pinned versions, lean profile, disk preflight and offline start/stop after setup. |
| Release manifest | Hardware revisions, PX4/ESC/radio firmware, runtime/model versions and hashes, tested Mac specifications and known limits. |
| Per-unit records | BOM, wiring/assembly guide, calibration backups, camera orientation and commissioning results. |
| Operator workflow | Select route, check readiness, start/pause/land, review findings and export local evidence. |
| Updates/support | Configuration backup, tested rollback, bounded logs, local diagnostic export and spare-part instructions. |
| Licence/source bundle | Our Apache-2.0 code; required upstream notices; applicable corresponding source/build instructions for distributed copyleft components. |

PX4/MAVSDK, llama.cpp, Qwen weights, Gazebo and the optional components retain their own licences. Our licence does not relicense dependencies. Inspect exact video plugins, firmware, Qt/native libraries and model files in the shipped bundle; the runtime's licence alone does not establish rights for model weights. [10][12][13][14][28][33][34][35]

No cloud service, remote API key, external map download or automatic data upload may be needed during an inspection. Provide an explicit local export when the user wants to move records. Retain only useful evidence and use bounded storage/retention settings.

Publish a production date and performance claims only after the complete chosen configuration passes its gates. The current dollar amounts are development equipment estimates, not a customer selling price; labour, assembly, warranty, support and deployment remain to be costed.

## 15. First tasks for the implementing AI

Execute A01–A04 in the first cloud session. A05 onward runs when the Mac is available with enough free working space. Independent documentation/BOM research may run in parallel; construction and physical tests remain gated. Avoid rebuilding capabilities already provided by the selected open-source components.

| ID | Priority / owner | Task | Completion evidence |
| --- | --- | --- | --- |
| A01 | Now, cloud / AI | Inspect existing repo and accessible cloud host; create minimal project, task ledger and environment record | `docs/environment.md`, confirmed target vs assumptions, small dependency set and reproducible cloud bootstrap. |
| A02 | Now, cloud / AI | Implement contracts, executor/watchdog, bounded buffers, recorder, small UI, fake/replay adapters and real adapter interfaces | Executable portable tests for state, stale outputs, operator priority and process ownership; fixtures labelled explicitly. |
| A03 | Now, cloud / AI | Implement real llama-server/MAVSDK/camera adapters, small world, lean profile and staged Mac scripts; run supported real cloud integrations | Adapter code, schema-valid flow, source/asset manifests and evidence classified by actual backend; unrun integrations listed. |
| A04 | First handoff / AI | Export portable source with pinned dependencies, model manifest, runtime decision, disk guards and next-session instructions | `docs/handoff.md`, source revision/archive checksum, compact export, test results and exact Mac commands; no mandatory large downloads. |
| A05 | Mac available / AI + operator | Run read-only host/storage preflight; stage native dependencies and the single selected model/projector pair | Chip/macOS/free-space report, measured installed sizes, checksums and working native binaries; stop only affected installs if space is insufficient. |
| A06 | Mac / AI + operator | Prove actual local image inference; then run camera-enabled PX4/Gazebo and MAVSDK with the model loaded concurrently | Actual frames/model answers and scripted takeoff/land; host-specific memory/latency evidence. |
| A07 | Mac / AI | Complete scripted route and genuine model-directed recheck, then the virtual failure/offline/resource suite | M2–M4 reports, held-out results, bounded memory/storage and explicit 8 GB validation status. |
| A08 | Parallel documentation / AI + hardware lead | Draft exact aircraft BOM and later camera/link bench plan | Cost sheet, wiring/weight/power plan and unresolved compatibility questions; no physical work yet. |
| A09 | After Mac virtual acceptance / human + AI support | Complete H1–H5 in order to assemble and commission one aircraft | Human build/configuration records and propellers-off bench evidence. |
| A10 | After commissioning / human + AI support | Progress through T1–T6 | Ordinary flight, scripted missions, real-image evaluation and supervised model-control evidence. |
| A11 | After repeated runs / AI + operator | Freeze, package and reproduce the installation on the supported host | Offline deployment, measured resource requirements and second-person reproduction report. |

**First Claude cloud session objective:** complete the accessible A01–A04 work and provide runnable source, meaningful test evidence and a compact Mac handoff. Do not stop after a plan or a UI mockup. If native integrations are unavailable in the cloud, complete the code and isolated tests, then mark only those integration checks blocked. Keep every task marked `not_started`, `in_progress`, `blocked` or `verified`, with a link to evidence and the host/profile for every verified result. The next Mac session starts with A05.

## 16. Optional research: DeepMind fly work

Keep **Flybody** out of the initial dependency graph. It is an Apache-2.0 MuJoCo fruit-fly body model and locomotion research framework developed by Google DeepMind and HHMI Janelia. Adapting an insect policy to a quadrotor's sensors and actuators would require a separate control/training experiment. [19]

If explored later, isolate it in `experiments/flybody/`, state whether the goal is insect simulation or a newly trained quadrotor policy, and benchmark a small policy against the existing controller. It must not delay the camera/model/navigation demo. Google's separate MaleCNS connectome release is a wiring dataset, not an executable quadrotor pilot. [20]

## 17. Decision log and completion reporting

| Decision / uncertainty | Current position | How it is resolved |
| --- | --- | --- |
| Development host / transfer | Start in Claude's cloud workspace, then move source to the Mac | A01–A04 complete portable work and document the host-specific tests still pending. |
| Available Mac mini | User reports 16 GB RAM and approximately 200 GB total storage; chip, macOS and free disk unknown | A05 reads the actual host without assuming that total capacity is free. |
| Efficiency target | Default `lean-8gb` profile; approximately 5 GiB combined incremental memory design budget | A06/A07 measure all processes and system memory pressure; actual 8 GB compatibility requires separate hardware evidence. |
| Storage constraints | Free space may initially be insufficient | Staged installs, one model pair, configurable data/build directories and bounded evidence; cloud tasks continue. |
| Initial runtime | llama.cpp with Metal; OnPremo not selected for current vision path | A03 prepares the adapter; A06 demonstrates actual local image inference and concurrent load on the Mac. |
| Aircraft | Self-build S500/MicoAir743-Lite preferred; $549 kit alternative | H1 freezes variants and total cost after compatibility checks. |
| Camera/link | Pi Zero 2 W + Camera Module 3/local Wi-Fi is the first bench candidate | H2/H5 prove power, images, telemetry and Mac reception together. |
| Flight range/endurance | Unquoted for the assembled payload | T1/T2 measure the actual rig and test site. |
| Model reliability | Unmeasured on real site footage | T3 and the held-out pilot evaluation. |
| Production readiness | Not established | Repeated tests, fixed configuration and second-person deployment. |

At handoff, record five separate states: cloud implementation complete, Mac virtual acceptance passed, lean-profile memory budget passed, actual 8 GB support verified, and physical hardware work permitted to begin. Do not collapse them into a single green status. Set `hardware_gate` to passed only when `mac_virtual_acceptance` and `lean_memory_budget` pass. Actual 8 GB validation may remain pending while prototyping with the available Mac, but the product must not claim verified 8 GB support until that test is complete.

At each milestone, report what was implemented, commands to reproduce it, exact versions/host, measured outcomes, failures and next task. Keep source review, mocked tests, simulator evidence, bench results and real flights explicitly distinguished. Include evidence images or a short recording when available.

An implementing AI should complete accessible work and document a concrete blocked gate when it needs the Mac, parts or human flight execution. Do not invent a passed test, hardware compatibility, sensor reading, benchmark, flight log or production-readiness claim.

## Sources

Primary documentation and supplier listings reviewed on 20 October 2026. Pin and archive the exact versions used; prices and development-branch instructions can change.

1. [MicoAir743-Lite store: controller/ESC variants and PX4 option](https://store.micoair.com/product/micoair743-lite/)
2. [PX4: MicoAir743-Lite board support](https://docs.px4.io/main/en/flight_controller/micoair743-lite)
3. [Holybro S500 V2 development kit: price and contents](https://holybro.com/collections/multicopter-kit/products/s500-v2-development-kit)
4. [Seeed ESP-FLY: current kit listing](https://www.seeedstudio.com/ESP-FLY-co-create-p-6744.html)
5. [Seeed ESP-FLY repository: GPL-3.0, contents and autonomous-flight limitations](https://github.com/Seeed-Projects/Co-Create_ESP-FLY)
6. [Holybro S500 V2: frame and ARF variants](https://holybro.com/products/s500-v2-kit)
7. [PX4: companion-computer video streaming](https://docs.px4.io/main/en/companion_computer/video_streaming)
8. [PX4: Gazebo simulation and camera streaming](https://docs.px4.io/main/en/sim_gazebo_gz/)
9. [Gazebo simulator source and licence](https://github.com/gazebosim/gz-sim)
10. [PX4 BSD-3-Clause licence](https://github.com/PX4/PX4-Autopilot/blob/main/LICENSE)
11. [MAVSDK-Python: installation and external-server operation](https://github.com/mavlink/MAVSDK-Python)
12. [MAVSDK licence](https://github.com/mavlink/MAVSDK/blob/main/LICENSE.md)
13. [Official Qwen3-VL-2B-Instruct GGUF weights, licence and usage](https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct-GGUF)
14. [llama.cpp: native inference and licence](https://github.com/ggml-org/llama.cpp)
15. [PX4 development branch: native macOS setup](https://docs.px4.io/main/en/dev_setup/dev_env_mac)
16. [Gazebo Harmonic: getting started and macOS limitations](https://gazebosim.org/docs/harmonic/getstarted/)
17. [MAVSDK Action API: goto_location and altitude semantics](https://mavsdk.mavlink.io/main/en/cpp/api_reference/classmavsdk_1_1_action.html)
18. [MAVSDK Offboard guide: automatic setpoint resend](https://mavsdk.mavlink.io/main/en/cpp/guide/offboard.html)
19. [Flybody: MuJoCo fruit-fly model and locomotion research](https://github.com/TuragaLab/flybody)
20. [Google Research: MaleCNS connectome release](https://research.google/blog/a-connectomics-milestone-mapping-the-complete-male-fruit-fly-brain/)
21. [OnPremo official site: features, published targets and release status](https://onpremo.org/)
22. [OnPremo repository: licensing, installation and real/mock backend distinction](https://github.com/bitfent/onpremo)
23. [OnPremo inspected runtime types, pinned source](https://github.com/bitfent/onpremo/blob/da82fbd0f9da6c3225b446d171dd695a50165d94/crates/onpremo-runtime/src/lib.rs)
24. [OnPremo inspected HTTP request types, pinned source](https://github.com/bitfent/onpremo/blob/da82fbd0f9da6c3225b446d171dd695a50165d94/crates/onpremo-server/src/lib.rs)
25. [OnPremo inspected llama.cpp adapter: CPU setting and text/grammar path](https://github.com/bitfent/onpremo/blob/da82fbd0f9da6c3225b446d171dd695a50165d94/crates/onpremo-runtime/src/llama.rs)
26. [OnPremo inspected Mac memory probe, pinned source](https://github.com/bitfent/onpremo/blob/da82fbd0f9da6c3225b446d171dd695a50165d94/crates/onpremo-memory/src/lib.rs)
27. [OnPremo architecture and MVP boundaries](https://github.com/bitfent/onpremo/blob/main/docs/architecture.md)
28. [QGroundControl: setup capabilities, source and licences](https://github.com/mavlink/qgroundcontrol)
29. [Raspberry Pi Zero 2 W: price and hardware specifications](https://www.raspberrypi.com/products/raspberry-pi-zero-2-w/)
30. [Raspberry Pi Camera Module 3: price and camera capabilities](https://www.raspberrypi.com/products/camera-module-3/)
31. [Raspberry Pi camera software documentation](https://www.raspberrypi.com/documentation/computers/camera_software.html)
32. [rpicam-apps: source and BSD-2-Clause licence](https://github.com/raspberrypi/rpicam-apps)
33. [GStreamer: application/plugin licensing](https://gstreamer.freedesktop.org/documentation/frequently-asked-questions/licensing.html)
34. [Bluejay: open-source ESC firmware](https://github.com/mathiasvr/bluejay)
35. [ExpressLRS: open-source radio-control link](https://github.com/ExpressLRS/ExpressLRS)
36. [Official Qwen3-VL-2B GGUF file list: exact model/projector names and download sizes](https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct-GGUF/tree/main)
