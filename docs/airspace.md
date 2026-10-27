# Shared airspace: several aircraft in the air

Status: implemented in simulation on 27 October 2026. Three aircraft fly through one room at the
same time on a shared airspace that keeps them apart; gated on both simulated plants within the
8 GB machine's memory budget. Nothing here has flown physically.

## Rules (`app/airspace.py`)

Every flight reports where it is in the place frame, several times a second, as an estimate.
The airspace decides, in this order:

1. **A lost link holds everyone.** A flight whose reports stop for more than 1 s is lost;
   every other flight holds where it is until the reports return or the flight is declared
   landed. The aircraft itself lands on its own command watchdog when its setpoints stop; this
   is the ground side of the same event.
2. **Separation.** Two flights at similar heights (within 0.8 m) keep 1.5 m apart, centre to
   centre, on the positions they report, plus 0.3 m because a reported position is an estimate.
3. **Right of way by number.** The lower aircraft number proceeds. The other holds while the
   proceeding flight is within 2.5 m of its next leg, and holds at once when it is already
   within separation of a flight that has right of way. Every leg is planned round the other
   flights as keep-out boxes (`app/mission_navigation.flight_path` with the boxes added to the
   operator map), so the proceeding flight never has to pass through a holding one.
4. **Corridors.** A flight given a corridor is only sent to goals inside it.
5. **Give way.** When the proceeding flight cannot plan past a holding aircraft, in a doorway or
   a dead end, the holding one is told to back off 1.5 m from it; the request lapses after 5 s
   unless renewed. Without this rule two aircraft meeting in a doorway wait for each other for
   ever, which the first simulation showed.

The airspace commands nothing. A flight asks before each leg and five times a second while
flying it, stops where it is on `hold`, backs off on `give_way`, and replans the leg from the
new position when it may go on. The rules and every flight's state are read at `GET
/api/airspace`; the mission runtime's own flight reports into it at 5 Hz
(`app/airspace_api.py`), so a single mission shows there too.

## Simulation (`sim/swarm_world.py`)

The benchmark room is two halls joined by one doorway at about (6.0, 4.0). Three aircraft start
in three places, fly out through the doorway to a far point in the other hall and back home, so
all three want the one gap at about the same time, and at 1.5 m separation only one fits through
at a time. Take-off is staggered by up to 3 s, each position estimate carries a drawn offset of a
few centimetres and a slow drift, and at a drawn moment between 8 and 20 s one aircraft's
reports stop for 2 s while it holds, as the ground would see a radio dropout.

Two plants fly the same mission loop: `kinematic`, a first-order model on a simulated clock
(seconds per run), and `rapier`, the service-owned micro-physics plant in real time, one
transport and physics process pair per aircraft (about a minute per run).

## Gate (`scripts/qualify_swarm.py`)

Per run: truth separation in the air never under 1.2 m; every goal reached; every aircraft
back home within 0.3 m and landed; the others stopped within 2.5 s of the lost link; no
collision envelope violation against the room and no contact; done within 180 s. Every check
passes on at least 90 % of the runs and at least 90 % of the runs pass every check. Over the
gate: the peak resident memory of the gate and its plant processes stays within the small
host's 3.5 GiB budget, and the deployment estimate for three real flights fits it too.

First-order plants, 27 October 2026 (`docs/swarm-validation-kinematic.json`): 30 of 30 runs passed every check. Never closer than 2.22 m between two aircraft in the air, every goal reached and every aircraft home and landed in every run, the others stopped within 1.7 s of the lost link at worst, no envelope violation, 114 s per run on average with 14.5 holds; the give-way rule was never needed in these runs. Peak memory of the gate 0.05 GiB; the deployment estimate for three real flights 3.41 GiB, within the 3.5 GiB budget.

Rapier plants in real time, 27 October 2026 (`docs/swarm-validation-rapier.json`): 10 of 10 runs passed every check. Never closer than 2.24 m, every goal reached and every aircraft home and landed in every run, the others stopped within 1.9 s of the lost link at worst, no envelope violation or contact, 130 s per run on average with 9.5 holds and 0 give-way moves. Peak resident memory of the gate with its six plant processes 1.18 GiB, within the 3.5 GiB budget, and no model or renderer running.

## Memory on an 8 GB machine

The small host's budget for our processes is 3.5 GiB. Three real flights: the model server
1.68 GiB, the console with the watch 0.20 GiB, and 0.50 GiB per aircraft (flight process 0.35,
position estimation 0.15), in all 3.38 GiB. The Florence verifier (1.47 GiB) must stay off. A
fourth aircraft does not fit. The 0.15 GiB per aircraft for position estimation is an allowance
from an idle measurement, not a figure from a real flight.

## What is not done

The plant does not model one aircraft hitting another; separation on the truth is the measure.
Three aircraft ask one model: a decision waits up to about 9 s when all three ask together, and
the swarm gate flies without the model. The right of way is by number, not by urgency or
battery. No physical aircraft has flown, alone or together.
