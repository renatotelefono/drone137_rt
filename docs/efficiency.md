# Efficiency without changing the decision policy

The accepted change makes route planning cheaper while keeping the same
clearance rules, sample positions and route outputs. The current camera code,
Qwen prompts, visible-parts checks, Laya policy and flight limits are unchanged.

## Measured result

Across 40 routes through the eight imported-asset rooms, median process CPU
time for a batch fell from **5.786 s to 0.702 s**, an **8.25× speedup** (87.9%
less CPU time). Three batches were measured per implementation, alternating
their order. All **40/40 route point lists matched exactly**. The benchmark
compares against the source frozen in `online-assets-flight-v1`.

`sim/flight_world.py` now creates a small geometry snapshot once per route.
It precomputes box half-widths and half-depths, checks whether a box could
violate the requested clearance before calculating its exact distance, and
stops a threshold query at the first violation. A bounded, 4,096-entry cache
reuses repeated directed grid-edge checks within that one plan. It is discarded
after planning; a new map always gets fresh geometry. Sampling direction,
0.06 m segment spacing, A* ordering and path simplification are preserved.
The moving cart's full swept envelope is still included.

The full regression suite passed **133 tests**, including thousands of
threshold comparisons at exact edges, their adjacent floating-point values,
random points, segment samples and a changed-map regression. The original
minimum-distance function remains the reference for telemetry and these tests.

A native PX4/Gazebo smoke test also completed takeoff, an 11.17 m route,
return and landing with zero conservative horizontal envelope violations,
no runtime errors and no source changes during execution. It made no model
requests and is not an additional recognition-accuracy result.

This is a routing microbenchmark, not an 8× faster mission. The previous full
run took about 951 s in total: full-frame inference accounted for 112.1 s,
candidate-crop inference 43.9 s and supervisor decisions 3.6 s. Flight movement,
settling and simulator lifecycle also consume time. Reducing Laya's small
contribution is unlikely to provide the largest overall saving.

## Repeatability check

The final full frame and last adequate crop from each of the eight recorded
missions were selected before inference: **16 image inputs**, including
successful and failed cases. Each was sent to Qwen twice with fresh requests,
without a response cache. All **16/16** pairs returned identical structured
outputs and matched their prior recorded output. All **22** saved supervisor
states with multiple eligible actions were also evaluated twice: **22/22**
choices matched both the repeat and the original recording. The Qwen and Laya
weight manifests were checked against the original experiment.

This establishes agreement on those fixed inputs on this host. It does not
guarantee identical results in every live flight or across different hardware.
Live flight changes camera pose, noise phase, exposure time and frame timing;
the inputs can differ even with temperature zero. A stable mistake is still a
mistake. The latest full mission score remains **6/8** from the prior run;
this optimization is not a new eight-mission accuracy measurement.

## Renderer trial that was not adopted

A trial reused static object transforms and camera-profile allocations.
All **51/51** fixed camera fixtures produced byte-identical PNGs before and
after the trial. Matrix composition calls fell from a median 958 to 21 per
frame, but instrumented CPU frame-submission time was **2.35 ms before versus
2.60 ms after**. That did not demonstrate a speedup, so the renderer changes
were rolled back. Its final source hashes match the previous flight run.

These fixtures reused recorded positions, attitudes, simulation times and cart
positions. Because the older frame metadata omitted angular speed, both sides
used the same explicit 0/0.3/1.2 rad/s angular-speed fixtures. This was a
before/after renderer comparison, not a reconstruction of the original video.
Submission timing does not measure GPU completion or full mission speed.

## Next optimization priorities

1. Keep a fixed-input regression suite alongside the live eight-mission suite.
   Exact replay catches changes in pixels, geometry and decisions; live runs
   check flight, timing, memory and failure handling.
2. Benchmark batching repeated static meshes. The existing scene produces
   roughly 900 draw calls per frame. Accept it only after pixel and recognition
   comparisons; preserve target detail and collision geometry.
3. Test a cheaper independent candidate verifier before reducing expensive
   vision requests. The current 40 crop requests took 43.9 s, and the verifier
   still produced both a false rejection and a false acceptance. This is a
   separate accuracy experiment, not a behavior-preserving refactor.
4. Keep one model instance, bounded queues, per-mission caches and explicit
   resource budgets. Reuse the existing 5 GiB application guard. No new full
   stack RAM reduction or actual 8 GiB hardware qualification is claimed here.

## Commands and evidence

```sh
.local/laya-env/bin/python -m scripts.benchmark_efficiency --baseline .local/validation/online-assets-flight-v1 --output .local/validation/efficiency-new
.local/laya-env/bin/python -m scripts.check_model_repeatability --baseline .local/validation/online-assets-flight-v1 --output .local/validation/repeatability-new
.local/laya-env/bin/python -m unittest discover -s tests
```

The benchmark preserves changed candidate source files on future runs. The
original renderer trial was recorded before that source-preservation feature
was added; its raw pixel/timing evidence is retained in
`.local/validation/efficiency-v1`. Its renderer trial is explicitly rejected,
so it must not be interpreted as the current renderer's performance.
Repeatability responses are in `.local/validation/repeatability-v1`.
Compact measured results are in `efficiency-validation.json`; complete test
output is in `efficiency-tests.txt`. Native smoke evidence is retained under
`.local/validation/efficiency-flight-smoke-v1`.
Output directories must be new; these tools acquire the shared evaluation
lock and must not run concurrently with a native flight.
