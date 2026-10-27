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
2. **The kind of object change, from the pixels** (`app/watch_classify.py`). The still regions
   of one frame are one event (a moved thing leaves one box and fills another). Two tests on the
   reference and the frame at the detector's working size decide what kind of change it is. The
   surround test: how far a box's pixels are, on average, from the nearest colour in the band
   around the box; a thing standing in front of its surroundings scores several levels, the
   background it hid scores near zero, so one side standing out and the other not settles added
   or removed. The move test: a thing that stands out on one side is searched for in the other
   picture inside the event's boxes, and a strong match at a different changed place where it
   stands out as well means it moved; a look-alike in unchanged surroundings does not count, and
   one box losing a thing while another gains one in the same frame is a move too. When neither
   settles it, the answer is left to the model. A 2B model reads a revealed wall as a new object
   and misses a shift; the pixels do not.
3. **A person is the person detector's call** (`app/person_detector.py`). On every motion or
   change event the frame goes to a detector made for people and nothing else: Apple's Vision
   framework on macOS, on the machine, no weights of ours, about 20 ms and 0.1 GiB. A sighting
   that overlaps the event's box makes the event a person, the alert is raised at once with the
   fixed words "A person is in view", and the model is not asked. Nothing identifies anyone: a
   box and a confidence, never a face or a name. Where the framework is not available the watch
   says so in its status and the model's word decides, as below. The framework sees real people
   and not drawn ones: the gate's walking silhouette goes through the model's path, and a real
   person's photo carried through the room goes through the detector's. A person under about
   150 px tall in the frame is missed by it and left to the model.
4. **One fixed question to the model, only on events** (`app/watch_events.py`). The event's
   before-and-after picture, two panels labelled BEFORE and NOW cropped around the box and
   scaled so a small thing is legible, the box drawn in both, goes to the local model with a
   fixed schema: a one-sentence summary of at most 20 words first, then the category, then
   whether it matters, and the instruction never to describe who a person is. A region that
   moved across the frame can only be a person, a moving object or nothing; a still region can
   be any category. The prompt defines a person as any walking or standing human shape and says
   a cart, trolley, box, machine or piece of furniture is not one, and that a thing gone from
   BEFORE is removed even when the wall or floor it uncovered looks new; the detector adds what
   it knows in words: moved or stayed, how much of the picture, taller than wide, and the pixel
   verdict with its reason. The model's own sentence is read as well: when it names a person,
   the answer is person, since its free text proved more reliable than its category pick. The
   event's category is the model's word when it says person, otherwise the pixel verdict,
   otherwise the model's word. Lighting events skip the model. If the model fails, the event is recorded as an unreviewed
   alert; the detector decides that something happened, the model only says what.
5. **The event record** (`.local/data/watch.sqlite3`, evidence under `.local/data/watch/`): time,
   aircraft, kind, category, matters, summary, box, before, after and composite pictures, the
   model's latency, the pixel verdict with its reason, the person detector's sighting and the
   model's own label, and when it was acknowledged. One event per kind per 30 s cooldown; a
   reported change becomes the new normal so it is reported once.
6. **Alerts in the console.** The Watch panel lists events with their pictures; unacknowledged
   events that matter show a red banner and a tone; one button acknowledges. Delivery beyond
   the console is the site's own channel, not a cloud of ours.

## Gate

`scripts/qualify_watch.py` stages events on a real photo with sensor noise and lamp flicker:
an object removed, added or moved, a drawn figure walking through, a real person's photo
(public domain, `tests/fixtures/person-public-domain.jpg`) carried through, a light change,
twelve seeds each, and quiet nights of eight hours at 2.5 Hz with no events. The detector
gate: every staged event raises an event of the right kind within 4 s with its box
overlapping the truth, no event
before the staged time, and at most one alert per quiet night. With `--model` the event's
category (pixel verdict and model together) is gated at 90 % on the synthetic set and on every
`--set`, and the model's own label and its "matters" answer are reported beside it. Results:
`docs/watch-validation.json`.

Run on 27 October 2026, with the person detector, the pixel verdict, the labelled panels and
the detector's smaller minimum region: 72 of 72 staged events detected and passed (the twelve
real-person photo walks included), worst latency 1.2 s (a light change at once, a walking
figure in 0.4 s, an object change in 1.2 s), no event before its time, and 0 false alerts over
two eight-hour quiet nights of 72,000 frames each, with no candidate region at all. The event's
category was right on 72 of 72 and "matters" on 72 of 72. The twelve photo walks were the
person detector's call every time, raised at 0.4 s without a model call; the twelve drawn
figures went through the model, which called them person every time. The model's own label was
right on 45 of the 48 events it saw (three moved objects it called added; the pixels overruled
it). Mean model latency 2.0 s per event.

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

**Several watches on one model.** Each docked aircraft has its own watch; the local model
answers one question at a time, so the watches queue on one lock and the record keeps the
time each question waited (`model_wait_s`). The person alert never waits: the detector raises
it before any question is asked. `scripts/qualify_watch.py --parallel 2 --only-sets` plays
the rendered set as two watches at once on the one model (`docs/watch-validation-paired.json`):
20 of 20 detected and passed, category 18 of 20 and "matters" 20 of 20, the same as one watch at a time; the model answered one question at a time (never two in flight), no question failed, the second watch's question waited up to 4.3 s, and the sentence arrived 6.0 s after the event on average (8.3 s at worst) against 2.8 s (4.3 s) alone. The detector's alert itself was not delayed: worst event latency 2.4 s in both runs. Before the queue, two watches reaching the model together made the adapter refuse the second question outright; that run is why the queue exists.

**Real clips.** `scripts/record_watch_clip.py --source 0 --category person --output <folder>`
records a webcam, a video file or an aircraft's frame URL at 2.5 Hz with a `truth.json` beside
the frames; Enter marks the moment the event happens. A parent folder of such clips goes to the
gate as another `--set`. A person event can only come from a real clip; none is recorded yet.

Rendered set, same run: 20 of 20 scenarios detected and passed, an object change in 1.2 s,
the cart's motion in 0.4 to 2.4 s, a light change at once, no event before its time. The
event's category was right on 18 of 20 (90 %, the gate's bar) and "matters" on 20 of 20: the
four added objects, the four light changes, the four cart runs, three of the four moved
objects and three of the four removals. The person detector saw no person in any of the
twenty, the cart and the chair included. The pixels settled ten of the twelve still changes,
all correctly; the two they left to the model, an office chair moved 0.9 m within one dark
region and a 32 cm bin taken off a rack 2.9 m away, the model called added (it read the plant
the chair had hidden and the wall behind the bin as new things). The model's own label was
right on 13 of the 20; mean model latency 2.7 s. The two smallest removals, a 40 cm tin at
2.1 m and the bin, are a quarter to a third of a percent of the frame and set the detector's
minimum region; the light change in the dim workshop set its brightness-shift rule. Both
sets' results are in `docs/watch-validation.json`.

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
never an identity. A real person has been through the detector only as a photo carried
through the synthetic room; no clip of a person walking through a real room has been through
the gate yet, and the drawn figure still relies on the model's word. The category
is at the gate's bar, not above it: a thing moved within one region, or a thing that does not
stand out from the rack it sits on, is left to the model, which reads uncovered background as
a new object. The alert is right in those cases; the word is not. Change detection between sorties (the Watch cluster on flown images) is a
separate piece, as is the site page that draws rooms green, amber or red. Retention and who
sees the evidence are product decisions still to be written down.
