# Perched watch: events from a docked camera

Status: implemented in simulation on 26 October 2026. A docked aircraft keeps its camera on;
the ground computer detects motion and change on every frame, asks the local model what an
event was, keeps the evidence, and raises an alert in the console. Nothing leaves the site.

## How it works

1. **Detection, deterministic, on every frame** (`app/watch_detector.py`). A reference image is
   learned from the first frames and drifts slowly where nothing happens. Each frame is compared
   with it in colour; connected regions of difference become candidates. A region that keeps
   moving is `motion`; one that stays put for four frames is `change` (something added, removed
   or moved); a difference over most of the image is `lighting`. About 10 ms per VGA frame.
2. **One fixed question to the model, only on events** (`app/watch_events.py`). The event's
   before-and-after picture, the changed region boxed, goes to the local model with a fixed
   schema: category (person, object added, removed, moved, lighting, nothing), whether it
   matters, a summary under 20 words, and the instruction never to describe who a person is.
   Lighting events skip the model. If the model fails, the event is recorded as an unreviewed
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

Run on 26 October 2026: 60 of 60 staged events detected and passed, worst latency
1.2 s (a walking figure in 0.4 s, an object change in 1.2 s), no event before its time, and
0 false alerts over two eight-hour quiet nights of 72,000 frames each, with no candidate
region at all. The local model's "matters" answer was right on 100 % of the 60 events,
which is the answer that raises the alert; its category label was right on 58 %: light
changes always, a removed object 10 of 12, a moved object 8 of 12, an added object 2 of 12 and the
walking figure 3 of 12, where it writes "a person moved" in the summary but picks object_moved. The
category is a label on a correct alert; the next step for it is the prompt and the before-and-after
framing, measured against this same gate. Mean model latency 0.9 s per event.

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
never an identity. Change detection between sorties (the Watch cluster on flown images) is a
separate piece, as is the site page that draws rooms green, amber or red. Retention and who
sees the evidence are product decisions still to be written down.
