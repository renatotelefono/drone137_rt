"""A person in a picture, from a detector made for that and nothing else.

On macOS this is Apple's Vision framework (human rectangles, upper body or whole body), on the
machine, no weights of our own, about 20 ms a frame. A 2B vision-language model is the wrong tool
for the question that matters most to security: it has called a rolling cart a person. Where the
framework is not available the detector reports no backend and the watch falls back to the model's
word. Nothing here identifies anyone: a box and a confidence, never a face or a name.

Elsewhere, and on a Mac without the framework, OpenCV's DNN runs MobileNet-SSD (Caffe, VOC classes, MIT licence)
from two files fetched and verified by scripts/fetch_person_model.py as pinned in config/person-detector.json;
the same code path on every platform OpenCV runs on. With neither, the detector reports no backend and the
watch falls back to the model's word.

Limits: Apple's framework sees real people; a drawn silhouette is not a person to it, so the synthetic walking
figure of the gate goes through the model's path. A person smaller than about 150 px tall in the frame is missed;
the fallback remains. MobileNet-SSD has not been measured on this project's frames yet.
"""
import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT/'config/person-detector.json'
MODELS = ROOT/'.local/data/models/person-detector'
MIN_CONFIDENCE = .5
MIN_OVERLAP = .3      # of the smaller box, between a detection and the event's box


def ssd_files():
    config = json.loads(CONFIG.read_text())
    return config, [MODELS/f['name'] for f in config['files']]


def available_backend(system=None, ssd_present=None):
    """'apple-vision' where the framework imports, else 'opencv-ssd' where its files are present, else None."""
    import platform
    system = system or platform.system()
    if system == 'Darwin':
        try:
            import Vision  # noqa: F401
            from Foundation import NSData  # noqa: F401
            return 'apple-vision'
        except Exception:
            pass
    if ssd_present is None:
        try:
            ssd_present = all(path.is_file() for path in ssd_files()[1])
        except (OSError, ValueError):
            ssd_present = False
    return 'opencv-ssd' if ssd_present else None


class PersonDetector:
    def __init__(self, backend='auto', min_confidence=MIN_CONFIDENCE):
        self.backend = available_backend() if backend == 'auto' else backend
        self.min_confidence = min_confidence
        self.calls = 0
        self.net = None

    def detect(self, bgr):
        """[{'confidence', 'bbox': (x, y, w, h)}] of people in the picture, best first; [] without a backend."""
        if bgr is None or bgr.size == 0:
            return []
        if self.backend == 'opencv-ssd':
            return self.detect_ssd(bgr)
        if self.backend != 'apple-vision':
            return []
        import Vision
        from Foundation import NSData
        self.calls += 1
        ok, buf = cv2.imencode('.png', bgr)
        data = NSData.dataWithBytes_length_(buf.tobytes(), len(buf))
        handler = Vision.VNImageRequestHandler.alloc().initWithData_options_(data, None)
        request = Vision.VNDetectHumanRectanglesRequest.alloc().init()
        request.setUpperBodyOnly_(True)          # upper bodies, which covers whole bodies as well
        handler.performRequests_error_([request], None)
        h, w = bgr.shape[:2]; found = []
        for r in request.results() or []:
            confidence = float(r.confidence())
            if confidence < self.min_confidence:
                continue
            box = r.boundingBox()   # normalised, origin bottom left
            x, y, bw, bh = box.origin.x, box.origin.y, box.size.width, box.size.height
            found.append({'confidence': round(confidence, 3), 'bbox': (int(x*w), int((1 - y - bh)*h), int(bw*w), int(bh*h))})
        return sorted(found, key=lambda d: -d['confidence'])

    def detect_ssd(self, bgr):
        """MobileNet-SSD through OpenCV's DNN: one forward pass at 300 by 300, the person class kept."""
        config, files = ssd_files()
        if self.net is None:
            self.net = cv2.dnn.readNetFromCaffe(str(files[0]), str(files[1]))
        self.calls += 1
        h, w = bgr.shape[:2]; size = config['input_size']
        blob = cv2.dnn.blobFromImage(cv2.resize(bgr, (size, size)), config['scale'], (size, size), config['mean'])
        self.net.setInput(blob)
        out = self.net.forward().reshape(-1, 7)
        found = []
        for _, label, confidence, x0, y0, x1, y1 in out:
            if int(label) != config['person_class'] or confidence < max(self.min_confidence, config['min_confidence']):
                continue
            x0, y0, x1, y1 = max(0., x0), max(0., y0), min(1., x1), min(1., y1)
            found.append({'confidence': round(float(confidence), 3), 'bbox': (int(x0*w), int(y0*h), int((x1 - x0)*w), int((y1 - y0)*h))})
        return sorted(found, key=lambda d: -d['confidence'])


def overlap(a, b):
    """Intersection over the smaller of two boxes (x, y, w, h)."""
    x0, y0 = max(a[0], b[0]), max(a[1], b[1]); x1, y1 = min(a[0] + a[2], b[0] + b[2]), min(a[1] + a[3], b[1] + b[3])
    inter = max(0, x1 - x0)*max(0, y1 - y0); smaller = min(a[2]*a[3], b[2]*b[3])
    return inter/smaller if smaller > 0 else 0.


def person_in(detections, box, min_overlap=MIN_OVERLAP):
    """The best detection that overlaps the box, or None."""
    for d in detections:
        if overlap(d['bbox'], box) >= min_overlap:
            return d
    return None
