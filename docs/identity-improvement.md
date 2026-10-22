# Improving object-search reliability

The previous native-flight evaluation completed 2/4 jobs for both supervisors.
Both failures were wrong object identities: red canisters were called fire
extinguishers. Intersecting rays localized those wrong objects successfully.
Laya received the resulting description as text, so it did not independently
check the pixels. Position consistency must not be presented as identity proof.

## Revised experiment

`app/identity.py` separates a full-frame candidate proposal from a visible-parts
check on a padded crop. Crops use only the proposal's predicted box, retain their
source resolution, and never use evaluator boxes or object labels. The check
requires a cylindrical body, an attached curved tube and a projecting top bar.
Unknown or contradictory parts fail closed. A `found` action requires supported
parts from both distinct views plus successful geometric triangulation. Empty
observations cannot trigger confirmation. Search continues after an unsupported
candidate; exhaustion reports unresolved, not proof of absence.

These checks are correlated outputs of one vision model. They are not calibrated
confidence scores, independent votes, or a guarantee of identity. Merely adding
a feature prompt is insufficient when that model invents the features too.

The diagnostic uses 16 saved crops from the final two observations in each of the
previous eight missions. Eight show the true target and eight show the falsely
claimed canisters. Labels apply to the candidate, not whether the room contains
a target elsewhere. These are known failure-analysis images; there is no claim
of an unseen test set or mission completion from this replay. All outputs,
source/crop hashes, predicted boxes, latency and memory samples are retained.
Three exploratory prompt variants are retained separately under
`.local/validation/identity-development`; the chosen prompt and parser are
frozen in the diagnostic's source hashes. Prompt development on these scenes
prevents treating their scores as independent qualification evidence.

## Reproduce

Keep the ordinary Recon app idle with its 2B model ready. Install the existing
`requirements-flight.txt` evaluation environment. The optional comparison model
is the official Qwen3-VL-4B-Instruct Q4_K_M with Q8_0 vision projector, pinned by
revision and official SHA256 in `scripts/download_qwen4b.py`.

```bash
.local/laya-env/bin/python -m scripts.download_qwen4b
.local/laya-env/bin/python -m scripts.evaluate_identity --model-size 2b --output .local/validation/my-identity-2b
.local/laya-env/bin/python -m scripts.evaluate_identity --model-size 4b --output .local/validation/my-identity-4b
.local/laya-env/bin/python -m scripts.evaluate_flight --model-size 4b --arms qwen --output .local/validation/my-verified-flight
```

Output directories must be new. The 4B experiment temporarily stops the idle 2B
model, uses one private loopback inference server with 2,048 tokens, one slot and
no idle prompt cache, then restores the normal model on completion/error. Both
models are never intentionally loaded together. The 4B model startup and evaluations
have sampled 5 GiB application guards. This remains a 16 GiB host measurement;
actual 8 GiB hardware and total OS memory pressure require separate validation.
The production dashboard still uses its original 2B model. This is an evaluation
lab, not a silently changed product default.

The native-flight harness now defaults to the visible-parts gate. Pass
`--legacy-baseline` to reproduce the older geometry-only eligibility behavior.
World complexity, flight dynamics and scoring tolerance are unchanged.

## Next qualification steps

1. Freeze the selected model, prompts, camera settings and policy before testing
   new layouts, object placements, lookalikes, occlusions and lighting seeds.
2. Measure false claims and missed targets separately from landing success and
   position error. Require evidence to support a claim; an honest unresolved job
   is preferable to a fabricated location, but still counts as a miss when the
   target is present.
3. Add evidence-directed closer viewpoints and search coverage. The current
   four operator-authored stations do not guarantee complete room visibility.
4. Build a real-camera hard-negative set across workshops/warehouses, perimeters,
   flat fields and hillsides. If the VLM still confuses objects, train a compact
   detector/verifier on representative footage before attempting airframe tests.
5. Calibrate the actual camera and airframe, including indoor positioning. The
   current native simulation uses generic x500 dynamics and simulated GNSS.

## Diagnostic results, 21 October 2026

The first feature prompt (`visible-parts-v1`) was not usable: 2B accepted seven
of eight lookalike crops; 4B rejected every crop, including all eight positives.
Some fields contradicted their own explanations. The revised contract explicitly
defines each JSON field and asks for a neutral visual description first. This
is development on known images, not a hidden test set.

With the same final `visible-parts-v2` prompt and byte-identical crops:

| Vision model | Correct crop decisions | False accepts / 8 | False rejections / 8 | Mean extra check | Peak summed RSS |
| --- | ---: | ---: | ---: | ---: | ---: |
| Qwen 2B Q4_K_M | 14/16 | 0 | 2 | 1.06 s | 2.11 GiB |
| Qwen 4B Q4_K_M | 14/16 | 0 | 2 | 2.29 s | 3.46 GiB |

Records: `.local/validation/identity-2b-v2/results.json` and
`.local/validation/identity-4b-v3/results.json`. These are crop replay costs,
not the memory cost of a complete running simulator. Neither score establishes
that the larger model improves job completion. The lighter model is the first
candidate for the live-flight follow-up.

A 2B live-flight trial then exposed a controller bug: it could choose another
confirmation even after two views satisfied both checks, and lose the valid
result when the extra view was weaker. That trial is preserved under
`.local/validation/identity-flight-2b-v1`, including an explicitly interrupted
second mission. Its cleanup ran and the inference server was restarted after
the cancelled HTTP request. The controller now makes completion terminal and
skips model calls when only one action is eligible.

One extra evidence-directed view is available only when the first two views
triangulate a candidate but disagree on whether its parts are supported. Its
waypoint comes from estimated image rays, not the target coordinates. It moves
at most 0.72 m horizontally, preserves at least 1.4 m estimated standoff, adjusts
height within 0.9–1.8 m, and must clear the known map by more than 0.65 m. The
existing route, speed and telemetry guards still apply. Both supported views
remain mandatory; a third view is not a majority vote.

Memory accounting now guards the larger of summed process RSS and macOS physical
footprints. Mapped GGUF pages can be resident without being charged to physical
footprint; summed RSS can instead double-count shared pages. Both are reported.
The 4B startup is measured separately; the normal 2B server is already running
when its diagnostic begins. None of these measurements replaces a test on an
actual 8 GiB machine.

## Full-flight results and limits

| Configuration | Complete four-case batch | False location claims | Returned and landed | Peak summed RSS |
| --- | ---: | ---: | ---: | ---: |
| Earlier 2B policy | 2/4 | 2 | 4/4 | See original source samples |
| Revised 2B | 3/4 | 0 | 4/4 | 3.51 GiB |
| Revised 4B | 1/4 | 0 | 4/4 | 4.71 GiB |

The revised 2B located the normal and far-room targets within 16–19 cm. It
reported unresolved in the absent case, rather than a false location. It missed
the genuine target in low light. The 4B full batch missed all three positive
cases under these strict multi-view checks. It is not a demonstrated upgrade for
this task, despite matching 2B on the saved-crop diagnostic.

A subsequent 2B low-light repeat passed at 23 cm error. Thus each scenario now
has a passing 2B run, but the complete batch remains **3/4**, and the five completed
flights under the revised terminal-completion policy contain **four successes
and one miss**. The repeat finished on its first two supported views; it did not
exercise the newer sightline planner. Do not attribute that success to the
planner or report 100% reliability from the latest-case selection. In the absent
mission, two crop observations still incorrectly passed the parts check;
geometric rejection prevented a false location claim. Recognition remains
inconsistent.

Camera inspection exposed an additional planning error: the extra viewpoint
could move behind a shelf post. The planner now rejects candidate sightlines
blocked by the known operator map and tries the opposite lateral direction. A
slightly higher viewpoint helps inspect the top, while a field-of-view bound
keeps the estimated candidate center in frame (height now 0.9–1.8 m). Unit tests
cover the observed shelf obstruction and label-independent geometry. The last
flight did not need this branch; its flight-level benefit is not yet measured.
The final 0.7 m of the sightline is excluded to avoid treating the candidate's
own surface as an occluder, so this is a conservative screening heuristic, not
a guarantee of visibility. An unknown real room would first need a sensed map.

Two earlier 4B infrastructure failures are retained: one found the target and
landed but timed out during camera cleanup; another timed out during PX4 startup
before takeoff. Video now finalizes before the landed simulator is torn down,
with bounded finalization and stage-specific logs. Three real-browser recorder
checks passed, including stale telemetry. The exact cause of the original
cleanup timeout was not isolated; the intermittent native startup failure also
remains a limitation. Failed runs are not counted as completed jobs.

Validation: **123 automated tests passed**; nine indexed recordings decoded;
the review's eight videos seek to 20 seconds; all 63 evidence images load;
no JavaScript errors or desktop/mobile horizontal overflow. Review the complete
attempt history at:

http://127.0.0.1:8142/identity-review/report.html

Compact measurements: `docs/identity-validation.json`. Full model outputs,
flight telemetry, videos and source snapshots remain under
`.local/validation/identity-*`. The ordinary app is restored to its 2B model.
No physical transport or real aircraft was used. Next work should freeze this
configuration and evaluate unseen layouts plus representative real-camera
positive and hard-negative footage, then train/calibrate a compact target
verifier if the VLM continues inventing parts. Preserve separate metrics for
false claims, missed targets, coverage, flight completion and memory.
