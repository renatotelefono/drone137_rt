# Online assets in the native flight simulation

The `polyhaven` scene variant replaces selected procedural props with locally
bundled CC0 models and adds photographed workshop HDR illumination. It remains
an assembled digital room: it is not a reconstruction of one real building.

## Observed result — October 21, 2026

The first complete Qwen 2B + Laya run with these assets scored **6/8 (75%)**,
compared with **5/8 (62.5%)** in the preceding procedural hard-suite run.
Target-present missions passed **2/4**; all **4/4** target-absent searches
completed without a location claim. There was one missed target and one
wrong-object claim. The eight-mission acceptance target is **not met**.

| Condition | Imported assets: target present | Imported assets: target absent | Previous target-present result |
| --- | --- | --- | --- |
| Dim light | Missed | No location claim | Missed |
| Glare | Found, 0.051 m error | No location claim | Missed |
| Partial occlusion | Found, 0.124 m error | No location claim | Found |
| Blur, delay and JPEG degradation | Wrong object, 6.056 m error | No location claim | Wrong object |

All eight flights landed; there were zero conservative horizontal envelope
violations and no runtime or integrity errors. Total flight distance was
209.60 m. Simulation advanced at 0.989–0.991 times wall-clock speed. Peak
guard memory was **3.54 GiB**, below the 5 GiB application budget on this
16 GiB host. The prior run measured 3.48 GiB. This is one run of each variant,
not a statistically established improvement or an 8 GiB hardware qualification.

The run made 51 full-frame vision requests, 40 candidate-crop requests and
22 Laya decisions. Mean full-frame inference latency was 2.20 s. Captured frame
ages ranged from 121–270 ms. The integrity audit verified all 138 frozen source
and asset files, all 51 camera images, all 40 crops and the frozen protocol.

[Watch both complete runs](http://127.0.0.1:8142/online-assets-review/report.html).
The review includes every mission and loads one indexed video at a time.
Compact metrics are in `online-assets-validation.json`; regression output is
in `online-assets-tests.txt`. Full records remain in
`.local/validation/online-assets-flight-v1` and `.local/validation/laya-hard-v1`.

The dim-light failure is particularly informative: the full-frame model
correctly proposed the imported extinguisher, but its crop check called the
visible operating handle a flat round lid in both views. In the motion case,
two crop checks instead accepted a red shelf container and nearby black
structure as an extinguisher. These are correlated verifier errors. Raising
visual detail did not solve them. Better candidate framing and an independent
target verifier, tested against held-out real footage and lookalikes, are the
next priorities; loosening the current parts gate would risk more false claims.

## Asset selection and scale

| Asset | Source | Use |
| --- | --- | --- |
| Korean Fire Extinguisher 01 | [UM JOORIN / Poly Haven](https://polyhaven.com/a/korean_fire_extinguisher_01) | Target; original physical height 0.659 m |
| Industrial Storage Cart | [Jule Bielitz / Poly Haven](https://polyhaven.com/a/industrial_storage_cart) | Replaces the procedural lab bench |
| Steel Frame Shelves 01 | [James Ray Cock / Poly Haven](https://polyhaven.com/a/steel_frame_shelves_01) | Two shelves replace the stock rack |
| Wooden Crate 01 | [James Ray Cock / Poly Haven](https://polyhaven.com/a/wooden_crate_01) | Shared mesh/material instances replace small storage cartons |
| Industrial Workshop Foundry | [Dimitrios Savva and Jarod Guest / Poly Haven](https://polyhaven.com/a/industrial_workshop_foundry) | Photographed HDR illumination and reflections |

All five assets are [CC0](https://polyhaven.com/license). The exact source URLs,
authors, upstream MD5 checksums, local SHA-256 hashes, byte sizes and published
dimensions are in `app/ui/real-assets/manifest.json`. The 27 downloaded files
total 9,831,674 bytes (9.38 MiB). Each texture is the publisher's 1K version.
The existing scanned concrete floor is retained. No API or external CDN is
contacted by the renderer at runtime. Powered by Poly Haven.

The glTF shelving geometry was exported at ten times its published metre
dimensions. A recorded uniform unit conversion restores its 2.14 m height.
The other models retain their physical scale, apart from the repeated small
crates, which are uniformly fitted into existing storage slots. All models are
grounded and centred by measured mesh bounds; their proportions are preserved.
The imported target is substantially smaller than the old procedural target.
No target is enlarged to make detection easier.

`sim/asset_world.py` derives each conservative axis-aligned collision box from
the same scale and yaw used by Three.js. The browser checks every imported
instance against those bounds. Boxes include empty spaces inside shelves and
cart frames; they are conservative collision approximations, not exact meshes.
Present/absent twins share collision bounds. The absent twin keeps a plain red
canister instead of the imported extinguisher.

Models share geometry, materials and textures across clones. A single camera
and renderer are active per mission. The 1K HDR image is converted to a small
prefiltered environment map, then its temporary resources are released. The
HDR panorama supplies lighting/reflections; it is never displayed as a fake
collidable room or used to hide targets in background imagery.

## Frozen comparison

The eight cases from `config/native-hard-v1.json` retain their seeds, placements,
camera impairments, drafts, search stations and scoring rules. Qwen3-VL 2B Q4
and Laya retain their previous prompts and decision policy. The imported asset
variant changes geometry, target scale and lighting together; its score is a
scene-change experiment, not a causal estimate of one asset's effect.

The evaluator snapshots code, renderer dependencies, asset files and manifests
before inference, records hashes, and checks integrity at the end. It preserves
all planned cases in the denominator and records full camera video, model
frames, candidate crops, responses, native flight telemetry, actual Laya calls,
frame ages, drops and sampled process memory.

The 5 GiB application guard covers the evaluator, models, Chrome camera,
Gazebo, PX4 and associated workers. The host has 16 GiB. Passing this sampled
guard does not establish operation on an actual 8 GiB computer.

## Reproduction

With the pinned native simulator environment and the normal local Qwen 2B
server ready on port 8081:

```sh
.local/laya-env/bin/python -m scripts.fetch_workshop_assets --verify
.local/laya-env/bin/python -m scripts.check_asset_camera --output .local/validation/asset-camera-new
.local/laya-env/bin/python -m scripts.evaluate_flight --suite hard --assets polyhaven --model-size 2b --arms qwen+laya --output .local/validation/asset-flight-new
```

Omit `--verify` to restore missing asset files from their pinned URLs and verify
their hashes. Output directories must be new. The native evaluation owns the
shared simulation ports and must run serially. `--assets procedural` retains
the earlier scene variant.

Preflight validation: 130 software tests passed, including route feasibility,
source-unit normalization and matched collision bounds. The static browser
audit rendered all eight scenes at four fixed viewpoints, checked 25/26
imported instances per absent/present room, and closed every recorder cleanly.

## Interpretation limits

The room topology and much of its clutter remain procedural. The model gets
pixels; navigation gets a known operator map and simulated GNSS. This does not
test unknown-building SLAM, real indoor localization, rolling shutter, calibrated
camera response or a specific aircraft's flight dynamics. Photographic material
detail and metre-scale objects improve the visual challenge without validating
real-world flight. Laya reads text choices and cannot independently verify an
image claim. No 100% real-world accuracy claim follows from this finite suite.
