# Third-party components

Original drone137 application code, small authored courtyard and synthetic test
images: Apache License 2.0, copyright 2026 drone137 contributors. The supplied
project brief is preserved as user-provided planning/reference material.

Dependencies are installed separately; their notices/licences must accompany any
later binary distribution. The source-only export does not bundle their binaries,
model weights, virtual environments or native build trees.

| Component | Licence / source |
| --- | --- |
| aiohttp, aiosignal, frozenlist, multidict, propcache, yarl | Apache-2.0; https://github.com/aio-libs |
| aiohappyeyeballs | PSF-2.0; https://github.com/aio-libs/aiohappyeyeballs |
| attrs | MIT; https://github.com/python-attrs/attrs |
| idna | BSD-3-Clause; https://github.com/kjd/idna |
| typing_extensions | Python Software Foundation; https://github.com/python/typing_extensions |
| MAVSDK / MAVSDK-Python | BSD-3-Clause; https://github.com/mavlink/MAVSDK / https://github.com/mavlink/MAVSDK-Python |
| grpcio / protobuf | Apache-2.0 / BSD-3-Clause; https://github.com/grpc/grpc / https://github.com/protocolbuffers/protobuf |
| PX4 | BSD-3-Clause; https://github.com/PX4/PX4-Autopilot |
| Gazebo core | Apache-2.0; https://github.com/gazebosim/gz-sim |
| llama.cpp | MIT; https://github.com/ggml-org/llama.cpp |
| Qwen3-VL-2B-Instruct-GGUF | Apache-2.0 model licence; https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct-GGUF |
| JPEG library used by optional native bridge | Use installed library's IJG / libjpeg-turbo notices; audit selected native package |
| GStreamer optional RTP receiver | LGPL core; individual plugin/dependency licences require release audit |

Exact Python versions and artifact hashes are in the lockfiles. Candidate native
source pins are in `docs/versions.json`. Native model copies retain their upstream
directory contents/notices. Packaging a final native/hardware bundle requires a
licence audit of those exact artifacts, plugins and firmware.

## Bundled browser library

Three.js 0.180.0 JavaScript modules are bundled under `app/ui/vendor/` under the
MIT licence. The full licence is `app/ui/vendor/LICENSE`; npm tarball integrity
and provenance are recorded in `app/ui/vendor/provenance.json`. Installation
verified that tarball's SHA512 before extracting the two browser modules. This
is the only vendored third-party runtime code in the source handoff.

## Bundled scanned surface textures

`app/ui/textures/concrete_floor_02_*_1k.jpg`: Concrete Floor 02 by Rob Tuytel,
Poly Haven, CC0-1.0. Source: https://polyhaven.com/a/concrete_floor_02 ; license:
https://polyhaven.com/license . The diffuse, OpenGL normal and roughness maps are
redistributed locally. URLs, byte sizes and SHA256 hashes are recorded in
`app/ui/textures/provenance.json`. The authored objects use procedural geometry;
this scanned floor does not make the complete scene a real-camera capture.

## Optional real-camera evaluation samples

The optional `scripts/fetch_real_samples.py` downloads six RGB preview frames from
the TUM RGB-D benchmark. They are not included in the source distribution.
Attribution: J. Sturm, N. Engelhard, F. Endres, W. Burgard and D. Cremers,
*A Benchmark for the Evaluation of RGB-D SLAM Systems*, IROS 2012.
Dataset: https://cvg.cit.tum.de/data/datasets/rgbd-dataset
Data license: Creative Commons Attribution 4.0 (CC BY 4.0),
https://creativecommons.org/licenses/by/4.0/ . Input PNGs are converted to JPEG
for the model. Source URLs, original hashes and converted-image hashes are retained.

## Optional local Laya experiment

Laya by ConvAI Innovations: https://huggingface.co/convaiinnovations/laya and
https://github.com/NandhaKishorM/laya, Apache-2.0. The optional experiment uses
the Apple Silicon FP16 conversion https://huggingface.co/aac6fef/laya-mlx at
commit `20aed815fc6acde75733882e7ec0e3f28aeb9717` and the community runtime
https://github.com/mizorewww/laya-mlx (`laya-mlx==0.5.0`), Apache-2.0.
Checkpoint LICENSE, NOTICE, source revision and file hashes remain with the
download under `.local/data/laya-mlx`; neither its weights nor its runtime are
vendored in the source handoff. MLX and the other optional dependencies retain
their installed package licenses. This is not TypeSafe's hosted Jev model.

## Optional 4B vision comparison

Qwen3-VL-4B-Instruct-GGUF by Qwen, Apache-2.0:
https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct-GGUF . The optional experiment
pins revision `1cd86afb9a95c410a6038ab3b40d8b578c892266`, the Q4_K_M language
weights and Q8_0 projector. Official file hashes, model-card licence declaration
and the standard Apache-2.0 text are retained under `.local/data/qwen4b`.
Weights are downloaded separately and are not vendored in the source handoff.

## Imported workshop assets

Powered by [Poly Haven](https://polyhaven.com). The local simulation bundles
CC0-1.0 assets; see https://polyhaven.com/license and
`app/ui/real-assets/manifest.json` for exact URLs, byte counts and SHA-256 hashes.

- Korean Fire Extinguisher 01 — UM JOORIN.
- Industrial Storage Cart — Jule Bielitz.
- Wooden Crate 01 and Steel Frame Shelves 01 — James Ray Cock.
- Industrial Workshop Foundry — photography by Dimitrios Savva, processing by Jarod Guest.

Models and 1K texture files are unchanged. Runtime transforms ground and centre
the models, normalize source units, and uniformly scale repeated small crates.
The photographed HDRI is used for illumination and reflections, not room geometry.
The existing concrete floor texture has its own provenance under `app/ui/textures`.
These assets do not imply endorsement by their creators or Poly Haven.

Three.js GLTFLoader, HDRLoader, RGBELoader and BufferGeometryUtils are vendored
from the same MIT-licensed `three@0.180.0` package as the renderer. Bare module
imports are rewritten locally. The existing vendor LICENSE applies; addon hashes
and the verified package integrity are in `app/ui/vendor/addons/provenance.json`.

## Optional independent visual reviewers

The live flight comparison downloads these checkpoints separately into
`.local/data/vision-reviewers`; weights are not vendored in the source handoff:

- Microsoft Florence-2-base-ft (230M), MIT:
  https://huggingface.co/microsoft/Florence-2-base-ft , revision
  `f6c1a25888ffc1d945ee8a1a77ac833c7303d46e`. Its pinned Python implementation
  and checkpoint files are hashed in the local manifest. The original code is
  used without modification, with generation caching disabled for compatibility
  with the pinned Transformers runtime.
- Hugging Face SmolVLM2-500M-Video-Instruct, Apache-2.0:
  https://huggingface.co/HuggingFaceTB/SmolVLM2-500M-Video-Instruct , revision
  `7b375e1b73b11138ff12fe22c8f2822d8fe03467`. The reviewer uses one 512px tile
  for small camera crops instead of the default 2048px tiling configuration.

Model cards, available license files and SHA-256 manifests remain beside each
checkpoint. `requirements-vision-reviewers.txt` records the isolated inference
environment; PyTorch, Transformers and their dependencies retain their own
installed licenses. The models run locally with network access disabled in the
worker configuration, and receive candidate pixels without simulator labels.
