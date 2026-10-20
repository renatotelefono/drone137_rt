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
