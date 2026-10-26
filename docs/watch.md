# Perched watch: events from a docked camera

Status: implemented in simulation on 26 October 2026. A docked aircraft keeps its camera on;
the ground computer detects motion and change on every frame, asks the local model what an
event was, keeps the evidence, and raises an alert in the console. Nothing leaves the site.

## How it works

1. **Detection, deterministic, on every frame** (`app/watch_detector.py`). A reference image is
   learned from the first frames and drifts slowly where nothing happens. Each frame is compared
   with it in colour; connected regions of difference of at least 0.2 % of the frame (a 40 cm
   tin at 2 m is a third of a percent) become candidates. A region that keeps moving is
   `motion`; one that stays put for four frames is `change` (something added, removed or
   moved); a difference over most of the image, or a brightness shift in one direction over
   70 % of it, is `lighting`, which a dim room needs because its dark parts move by less than
   the object threshold. About 10 ms per VGA frame.
2. **One fixed question to the model, only on events** (`app/watch_events.py`). The event's
   before-and-after picture, the two panels labelled BEFORE and NOW with the changed region
   boxed in both, goes to the local model with a fixed schema: a one-sentence summary of what
   differs first, then the category (person, object added, removed, moved, lighting, nothing),
   then whether it matters, and the instruction never to describe who a person is. The prompt
   defines a person as any walking or standing human shape, and the detector adds what it knows
   in words: whether the region moved across the frame or appeared and stayed still, how much of
   the picture it covers, and whether it is taller than wide. Lighting events skip the model. If the model fails, the event is recorded as an unreviewed
   alert; the detector decides that something happened, the model only says what.
3. **The event record** (`.local/data/watch.sqlite3`, evidence under `.local/data/watch/`): time,
   aircraft, kind, category, matters, summary, box, before, after and composite pictures, the
   model's latency, and when it was acknowledged. One event per kind per 30 s cooldown; a
   reported change becomes the new normal so it is reported once.
4. **Alerts in the console.** The Watch panel lists events with their pictures; unacknowledged
   events that matter show a red banner and a tone; one button acknowledges. Delivery beyond
   the console is the site's own channel, not a cloud of ours.

## Gate

`scripts/qualify_watch.py` stages events on a real photo with sensor noise and lamp flicker:
an object removed, added or moved, a figure walking through, a light change, twelve seeds
each, and quiet nights of eight hours at 2.5 Hz with no events. The detector gate: every staged
event raises an event of the right kind within 4 s with its box overlapping the truth, no event
before the staged time, and at most one alert per quiet night. With `--model` the local model's
category and "matters" answers are scored and reported, not gated, because the pictures are
synthetic. Results: `docs/watch-validation.json`.

Run on 26 October 2026, after the labelled panels, the person definition, the detector note
and the detector's smaller minimum region: 60 of 60 staged events detected and passed, worst
latency 1.2 s (a light change at once, a walking figure in 0.4 s, an object change in 1.2 s),
no event before its time, and 0 false alerts over two eight-hour quiet nights of 72,000 frames
each, with no candidate region at all. The local model's "matters" answer was right on 100 %
of the 60 events, which is the answer that raises the alert; its category label was right on
85 %: a removed object 12 of 12, an added object 12 of 12, light changes 12 of 12, the walking
figure 11 of 12, a moved object 4 of 12 (it says added or removed; a 90 px shift on a photo
rarely reads as the same thing in a new place). The same gate before these changes scored the
category at 58 %. Mean model latency 2.2 s per event with the longer answer.

**Rendered set.** `sim/watch_render.py` renders staged events in the CC0 workshop through the
service's own mission camera from a fixed dock pose: a paint tin, canister, bin, case, cone or
chair removed, added or moved 0.6 to 1 m, a full-size wooden crate set down, the stock cart
rolling 2.4 m across open floor, the lights mostly off (lamps and the HDR environment at
30 %). The dock sits at table or shelf height (0.75 or 1.05 m; the camera is pitched 9° down,
so a floor-level dock sees mostly floor),
2 to 3.5 m from the object, in free space, with the object's foot and top inside the camera's
field and nothing standing between; the camera's own noise, blur, vignette and frame drops apply.
Fifteen frames before the event and twenty-five after at 2.5 Hz, twenty scenarios, with the
truth beside each (`.local/validation/watch-rendered/`, `tests/test_watch_render.py` checks the
geometry). `scripts/qualify_watch.py --set <folder>` plays each scenario through the watch and
scores it by kind and timing, no box truth, and the gate requires every one to pass. Nothing
rendered is a person.

**Real clips.** `scripts/record_watch_clip.py --source 0 --category person --output <folder>`
records a webcam, a video file or an aircraft's frame URL at 2.5 Hz with a `truth.json` beside
the frames; Enter marks the moment the event happens. A parent folder of such clips goes to the
gate as another `--set`. A person event can only come from a real clip; none is recorded yet.

Rendered set, same run: 20 of 20 scenarios detected and passed, an object change in 1.2 s,
the cart's motion in 0.4 to 2.4 s, a light change at once, no event before its time. The
model's "matters" answer was right on all 16 events it saw (lighting skips it); its category
label on 7 of 16: an added object 4 of 4 (the crate, the canister), a removed object 2 of 4,
a moved object 1 of 8 (the rolling cart and the moved tin, cones, canister and chair it mostly
calls added or removed). Mean model latency 2.5 s. The two smallest removals, a 40 cm tin at
2.1 m and a 32 cm bin at 2.9 m, are a quarter to a third of a percent of the frame and set
the detector's minimum region; the light change in the dim workshop set its brightness-shift
rule. Both sets' results are in `docs/watch-validation.json`.

`hardware/esp32/link_emulator.py --frames <folder>` plays a folder of JPEG frames at 2.5 Hz
instead of its fixture, so the whole chain from camera to alert runs without a flight
(`tests/test_watch_emulator.py`).

## API

| Endpoint | Does |
| --- | --- |
| `GET /api/watch` | Running watches and unacknowledged alerts |
| `POST /api/watch/{aircraft}/start`, `.../stop` | Watch a connected aircraft's camera |
| `GET /api/watch/events?since=&limit=` | Event records, newest first |
| `POST /api/watch/events/{id}/ack` | Acknowledge |
| `GET /api/watch/events/{id}/composite.jpg` | Evidence: `before.jpg`, `after.jpg`, `composite.jpg` |

## What is not done

The dock's tag stand sits in a perched camera's view; a sentinel dock needs the tag column
moved off the camera's axis. Person detection is a moving figure and the model's word for it,
never an identity, and no real clip of a person has been through the gate yet. The moved-object
label is the model's weak point on both sets: the alert is right, the word is not. Change detection between sorties (the Watch cluster on flown images) is a
separate piece, as is the site page that draws rooms green, amber or red. Retention and who
sees the evidence are product decisions still to be written down.
