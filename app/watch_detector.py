"""Motion and change detection on a fixed camera: deterministic, cheap, runs on every frame.

A reference frame is learned from the first frames and drifts slowly. Each frame is compared
with it; connected regions of difference become candidates. A region that keeps moving is
`motion`; one that stays put for a few frames is `change` (something added, removed or
moved); a difference covering most of the image is `lighting`. The model is never run here.
"""
import cv2
import numpy as np

KINDS = ('motion', 'change', 'lighting')


def iou(a, b):
    ax, ay, aw, ah = a; bx, by, bw, bh = b
    x0, y0 = max(ax, bx), max(ay, by); x1, y1 = min(ax+aw, bx+bw), min(ay+ah, by+bh)
    inter = max(0, x1-x0)*max(0, y1-y0)
    union = aw*ah + bw*bh - inter
    return inter/union if union else 0.


class ChangeDetector:
    def __init__(self, *, width=320, threshold=24, min_area_fraction=.002, learn_frames=5, drift=.01,
                 persist_frames=4, lighting_fraction=.55, shift_fraction=.7, move_px=6, associate_px=40):
        self.width, self.threshold, self.min_area_fraction = width, threshold, min_area_fraction
        self.learn_frames, self.drift, self.persist_frames = learn_frames, drift, persist_frames
        self.lighting_fraction, self.shift_fraction, self.move_px, self.associate_px = lighting_fraction, shift_fraction, move_px, associate_px
        self.reference = None
        self.learning = []
        self.tracks = []       # [{'bbox', 'first', 'frames', 'centres', 'reported'}] in processing coordinates
        self.frames = 0
        self.scale = 1.
        self.last_gray = None

    def prepare(self, frame):
        h, w = frame.shape[:2]
        self.scale = self.width/w
        small = cv2.resize(frame, (self.width, int(round(h*self.scale)))) if w != self.width else frame
        if small.ndim == 2:
            small = cv2.cvtColor(small, cv2.COLOR_GRAY2BGR)
        return cv2.GaussianBlur(small, (5, 5), 0).astype(np.float32)   # colour kept: a grey object on a grey wall still differs in hue

    def absorb(self):
        """Make the current view the reference, after a change has been reported."""
        if self.last_gray is not None:
            self.reference = self.last_gray.copy()
        self.tracks = []

    def update(self, frame):
        """Candidates for this frame: [{'kind', 'bbox' (x, y, w, h in frame pixels), 'area_fraction', 'frames'}]."""
        gray = self.prepare(frame); self.last_gray = gray; self.frames += 1
        if self.reference is None:
            self.learning.append(gray)
            if len(self.learning) >= self.learn_frames:
                self.reference = np.median(np.stack(self.learning), axis=0).astype(np.float32); self.learning = []
            return []
        diff = cv2.absdiff(gray, self.reference).max(axis=2)
        mask = (diff > self.threshold).astype(np.uint8)
        fraction = float(mask.mean())
        # A brightness shift in one direction over most of the picture is a light change even where the
        # dark parts of a dim room move by less than the object threshold.
        shift = gray.mean(axis=2) - self.reference.mean(axis=2)
        shifted = max(float((shift < -self.threshold/3).mean()), float((shift > self.threshold/3).mean()))
        if fraction > self.lighting_fraction or shifted > self.shift_fraction:
            # Whole-image change: light level, not an object. The new light becomes the reference at
            # once; a slow fade would leave partial differences that look like objects for a while.
            self.reference = gray.copy(); self.tracks = []
            return [{'kind': 'lighting', 'bbox': self.full_bbox(frame), 'area_fraction': max(fraction, shifted), 'frames': 1}]
        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.morphologyEx(cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel), cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
        count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
        min_area = self.min_area_fraction*mask.size
        regions = [(tuple(int(v) for v in stats[i, :4]), tuple(float(c) for c in centroids[i])) for i in range(1, count) if stats[i, cv2.CC_STAT_AREA] >= min_area]
        # The reference drifts only where nothing is happening.
        still = mask == 0
        self.reference[still] = self.reference[still]*(1-self.drift) + gray[still]*self.drift
        candidates = []
        next_tracks = []
        for bbox, centre in regions:
            track = next((t for t in self.tracks if iou(t['bbox'], bbox) > .3 or
                          (t['centres'] and abs(t['centres'][-1][0]-centre[0]) + abs(t['centres'][-1][1]-centre[1]) < self.associate_px)), None)
            if track is None:
                track = {'bbox': bbox, 'first': self.frames, 'frames': 0, 'centres': [], 'reported': None}
            track['bbox'] = bbox; track['frames'] += 1; track['centres'] = (track['centres'] + [centre])[-4:]
            next_tracks.append(track)
            moved = len(track['centres']) >= 2 and max(abs(track['centres'][-1][0]-c[0]) + abs(track['centres'][-1][1]-c[1]) for c in track['centres'][:-1]) > self.move_px
            kind = 'motion' if moved else ('change' if track['frames'] >= self.persist_frames else None)
            if kind and track['reported'] != kind:
                track['reported'] = kind
                candidates.append({'kind': kind, 'bbox': self.to_frame(bbox), 'area_fraction': bbox[2]*bbox[3]/mask.size, 'frames': track['frames']})
        self.tracks = next_tracks
        return candidates

    def to_frame(self, bbox):
        x, y, w, h = bbox; s = 1/self.scale
        return (int(x*s), int(y*s), int(w*s), int(h*s))

    def full_bbox(self, frame):
        h, w = frame.shape[:2]
        return (0, 0, w, h)

    def reference_image(self):
        """The reference as a BGR image at processing size, or None while learning."""
        return None if self.reference is None else np.clip(self.reference, 0, 255).astype(np.uint8)
