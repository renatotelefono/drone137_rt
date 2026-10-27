"""What kind of object change a still region is, read from the pictures: added, taken away or moved.

Two tests on the before picture (the detector's reference) and the now picture at its working size.
The surround test: how far a box's pixels are, on average, from the nearest colour in the band around
the box. A thing standing in front of its surroundings scores several levels; the background it hid
scores near zero. One side standing out and the other not settles added or removed.
The move test: a thing that stands out on one side is searched for in the other picture inside the
event's boxes; a strong normalised match at a different place, where it stands out as well, means it
moved. A look-alike elsewhere in unchanged surroundings does not count.
Two boxes in one frame, one losing the thing that stood out in it and one gaining one, are a move too.
Neither test names the thing; the model does that. When nothing settles it, the answer is None.
"""
import cv2
import numpy as np

SURROUND_PX = 12        # band around a box, at working size
STANDS_OUT = 3.         # mean levels from the surround that mean a thing is there
EVIDENCE = 2.           # enough to search for a move from or to this box
DISTINCT_LEVELS = 20    # a pixel with no surround colour this close stands out (for the thing's outline)
MIN_THING_PX = 24
MATCH_SCORE = .55       # normalised cross-correlation that settles a move
SAMPLE = 400


def clip_box(box, shape):
    h, w = shape[:2]; x, y, bw, bh = (int(round(v)) for v in box)
    x0, y0, x1, y1 = max(0, x), max(0, y), min(w, x + bw), min(h, y + bh)
    return (x0, y0, max(0, x1 - x0), max(0, y1 - y0))


def union_box(boxes):
    x0 = min(b[0] for b in boxes); y0 = min(b[1] for b in boxes)
    x1 = max(b[0] + b[2] for b in boxes); y1 = max(b[1] + b[3] for b in boxes)
    return (x0, y0, x1 - x0, y1 - y0)


def dilated(box, shape, factor=1.):
    x, y, w, h = box
    return clip_box((x - w*factor, y - h*factor, w*(1 + 2*factor), h*(1 + 2*factor)), shape)


def surround_colours(image, box, width=SURROUND_PX):
    h, w = image.shape[:2]; x, y, bw, bh = box
    mask = np.zeros((h, w), bool)
    mask[max(0, y - width):min(h, y + bh + width), max(0, x - width):min(w, x + bw + width)] = True
    mask[y:y + bh, x:x + bw] = False
    colours = image[mask].astype(np.float32)
    if len(colours) > SAMPLE:
        colours = colours[np.linspace(0, len(colours) - 1, SAMPLE).astype(int)]
    return colours


def nearest_distance(image, box, colours):
    """Per pixel of the box: distance (levels, max over channels) to the nearest of the colours."""
    x, y, w, h = box
    patch = image[y:y + h, x:x + w].reshape(-1, 3).astype(np.float32)
    if len(patch) == 0 or len(colours) == 0:
        return np.zeros((h, w), np.float32)
    nearest = np.empty(len(patch), np.float32)
    for start in range(0, len(patch), 2048):
        chunk = patch[start:start + 2048]
        nearest[start:start + 2048] = np.abs(chunk[:, None, :] - colours[None, :, :]).max(axis=2).min(axis=1)
    return nearest.reshape(h, w)


def stands_out(image, box):
    """(mean distance from the surround, outline box of the standing-out thing or None)."""
    if box[2] == 0 or box[3] == 0:
        return 0., None
    distance = nearest_distance(image, box, surround_colours(image, box))
    mask = cv2.morphologyEx((distance > DISTINCT_LEVELS).astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    thing = None
    if count > 1:
        i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        if stats[i, cv2.CC_STAT_AREA] >= MIN_THING_PX:
            x, y, w, h = (int(v) for v in stats[i, :4]); thing = (box[0] + x, box[1] + y, w, h)
    return float(distance.mean()), thing


def find_elsewhere(source, target, box, windows, min_shift):
    """The box's content in `source`, looked for in `target` inside the windows but not at its own place: (score, box) or None."""
    x, y, w, h = box; patch = source[y:y + h, x:x + w]
    if w < 6 or h < 6 or float(patch.std()) < 4:
        return None
    best = None
    for wx, wy, ww, wh in windows:
        if ww < w or wh < h:
            continue
        result = cv2.matchTemplate(target[wy:wy + wh, wx:wx + ww], patch, cv2.TM_CCOEFF_NORMED)
        ox, oy = x - wx, y - wy
        result[max(0, oy - min_shift + 1):oy + min_shift, max(0, ox - min_shift + 1):ox + min_shift] = -1.
        _, score, _, loc = cv2.minMaxLoc(result)
        if best is None or score > best[0]:
            best = (float(score), (wx + loc[0], wy + loc[1], w, h))
    return best


def overlap_fraction(box, boxes):
    """How much of the box lies inside the union of the boxes."""
    x, y, w, h = box
    if w == 0 or h == 0:
        return 0.
    inside = np.zeros((h, w), bool)
    for bx, by, bw, bh in boxes:
        x0, y0, x1, y1 = max(x, bx), max(y, by), min(x + w, bx + bw), min(y + h, by + bh)
        if x1 > x0 and y1 > y0:
            inside[y0 - y:y1 - y, x0 - x:x1 - x] = True
    return float(inside.mean())


def classify_change(before, now, boxes):
    """{'category': 'object_added' | 'object_removed' | 'object_moved' | None, 'bbox', 'boxes', 'measures', 'match', 'reason'}
    for the change boxes of one frame; before and now are BGR images of the same size."""
    boxes = [b for b in (clip_box(b, now.shape) for b in boxes) if b[2] > 0 and b[3] > 0]
    if not boxes:
        return {'category': None, 'bbox': None, 'boxes': [], 'measures': [], 'match': None, 'reason': 'no box'}
    measures = []
    for box in boxes:
        sb, tb = stands_out(before, box); sn, tn = stands_out(now, box)
        measures.append({'box': box, 'before': sb, 'now': sn, 'thing_before': tb, 'thing_now': tn})
    windows = [dilated(b, now.shape) for b in boxes]
    # The move test: a thing with evidence on one side, found on the other side at another changed place where it stands out too.
    for m in measures:
        for side, source, target in (('before', before, now), ('now', now, before)):
            if m[side] < EVIDENCE:
                continue
            template = m['thing_' + side] or m['box']
            found = find_elsewhere(source, target, template, windows, min_shift=max(4, min(template[2], template[3])//2))
            if (found and found[0] >= MATCH_SCORE and overlap_fraction(found[1], boxes) >= .5
                    and stands_out(target, found[1])[0] >= EVIDENCE):
                return {'category': 'object_moved', 'bbox': union_box([template, found[1]]), 'boxes': boxes, 'measures': measures, 'match': found[0],
                        'reason': f'the thing standing out {side} is found {"now" if side == "before" else "before"} at another changed place, standing out there too (match {found[0]:.2f})'}
    lost = [m for m in measures if m['before'] >= STANDS_OUT and m['now'] <= m['before']/2]
    gained = [m for m in measures if m['now'] >= STANDS_OUT and m['before'] <= m['now']/2]
    if lost and gained:
        return {'category': 'object_moved', 'bbox': union_box([m['box'] for m in lost + gained]), 'boxes': boxes, 'measures': measures, 'match': None,
                'reason': 'in the same frame one box lost the thing that stood out in it and another gained one'}
    sb = max(m['before'] for m in measures); sn = max(m['now'] for m in measures); bbox = union_box(boxes)
    if sb >= STANDS_OUT and sn >= STANDS_OUT:
        return {'category': None, 'bbox': bbox, 'boxes': boxes, 'measures': measures, 'match': None,
                'reason': f'something stands out before ({sb:.1f} levels) and now ({sn:.1f}) and no move was found'}
    if sb >= STANDS_OUT and sn <= sb/2:
        return {'category': 'object_removed', 'bbox': bbox, 'boxes': boxes, 'measures': measures, 'match': None,
                'reason': f'the box stood out from its surroundings before ({sb:.1f} levels) and does not now ({sn:.1f})'}
    if sn >= STANDS_OUT and sb <= sn/2:
        return {'category': 'object_added', 'bbox': bbox, 'boxes': boxes, 'measures': measures, 'match': None,
                'reason': f'the box stands out from its surroundings now ({sn:.1f} levels) and did not before ({sb:.1f})'}
    return {'category': None, 'bbox': bbox, 'boxes': boxes, 'measures': measures, 'match': None,
            'reason': f'the box stands out {sb:.1f} levels before and {sn:.1f} now, which settles nothing'}
