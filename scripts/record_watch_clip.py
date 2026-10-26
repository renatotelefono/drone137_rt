"""Record a real event clip for the perched-watch gate.

  python -m scripts.record_watch_clip --source 0 --category person --seconds 30 --output .local/validation/watch-clips/person-01
  python -m scripts.record_watch_clip --source http://127.0.0.1:8137/api/aircraft/<id>/frame --category object_removed ...

Frames are saved at 2.5 Hz as JPEG with a truth.json beside them. Press Enter the moment the
event happens (a person walks in, an object is taken); that marks the event frame. Nothing is
uploaded anywhere; the folder is the evidence. Categories: person, object_added, object_removed,
object_moved, lighting.
"""
import argparse
import json
from pathlib import Path
import sys
import threading
import time

import cv2
import numpy as np

RATE = 2.5
CATEGORIES = ('person', 'object_added', 'object_removed', 'object_moved', 'lighting')
KINDS = {'person': 'motion', 'lighting': 'lighting'}


def frame_source(source):
    if source.startswith('http://') or source.startswith('https://'):
        import urllib.request
        def grab():
            with urllib.request.urlopen(source, timeout=3) as response:
                data = response.read()
            return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        return grab, lambda: None
    capture = cv2.VideoCapture(int(source) if source.isdigit() else source)
    if not capture.isOpened():
        raise SystemExit(f'Cannot open camera {source}')
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640); capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    def grab():
        ok, frame = capture.read()
        return frame if ok else None
    return grab, capture.release


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', default='0', help='camera index, video file, or an http frame URL')
    parser.add_argument('--category', required=True, choices=CATEGORIES)
    parser.add_argument('--seconds', type=float, default=30.)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--note', default='')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    grab, release = frame_source(args.source)
    marks = []
    def listen():
        for line in sys.stdin:
            marks.append(time.monotonic())
    threading.Thread(target=listen, daemon=True).start()
    print(f'Recording {args.seconds:.0f} s at {RATE} Hz into {args.output}. Press Enter when the event happens.', flush=True)
    started = time.monotonic(); index = 0; times = []
    try:
        while time.monotonic() - started < args.seconds:
            due = started + index/RATE
            while time.monotonic() < due:
                time.sleep(.005)
            frame = grab()
            if frame is None:
                print('no frame', flush=True); time.sleep(.2); index += 1; continue   # keep the clock; the gap shows as a missing frame
            if frame.shape[1] != 640:
                frame = cv2.resize(frame, (640, int(frame.shape[0]*640/frame.shape[1])))
            cv2.imwrite(str(args.output/f'{index:05}.jpg'), frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            times.append(time.monotonic() - started); index += 1
            if index % 25 == 0:
                print(f'{index/RATE:.0f} s', flush=True)
    finally:
        release()
    at = (marks[0] - started) if marks else None
    truth = {'category': args.category, 'kind': KINDS.get(args.category, 'change'), 'at': at, 'at_index': None if at is None else int(round(at*RATE)),
             'fps': RATE, 'frames': index, 'source': args.source, 'recorded_at': time.strftime('%Y-%m-%d %H:%M'), 'note': args.note}
    (args.output/'truth.json').write_text(json.dumps(truth, indent=2))
    print(json.dumps(truth), flush=True)
    if at is None:
        print('No event mark was pressed; edit truth.json and set "at" in seconds before using this clip.', flush=True)


if __name__ == '__main__':
    main()
