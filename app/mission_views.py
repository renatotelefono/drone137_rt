"""Acquire better images from estimated rays and an identity-free operator map."""
import math
from app.mission_navigation import clearance, flight_path
from app.flight_localization import planned_parallax


def visible_ray(geometry, origin, target):
    # The estimated candidate's own enclosing box must not occlude itself.
    # All other boxes, including objects near the candidate, remain occluders.
    boxes = []
    for box in geometry['obstacles']+geometry.get('fixtures', []):
        inside = (abs(target[0]-box['x']) <= box['sx']/2+.1 and
                  abs(target[1]-box['y']) <= box['sy']/2+.1 and
                  box.get('bottom', 0)-.1 <= target[2] <= box.get('bottom', 0)+box['height']+.1)
        if not inside:
            boxes.append(box)
    length = math.dist(origin, target)
    for i in range(1, math.ceil(length/.05)):
        f = min(i*.05/length, 1)
        p = [a+(b-a)*f for a, b in zip(origin, target)]
        for box in boxes:
            if (abs(p[0]-box['x']) <= box['sx']/2 and abs(p[1]-box['y']) <= box['sy']/2
                    and box.get('bottom', 0) <= p[2] <= box.get('bottom', 0)+box['height']):
                return False
    return True


def next_views(geometry, position, location, reference, previous=(), preserve_view=False):
    """Rank safe stations around a predicted candidate, never scene target labels.

    Keep the existing 0.58 m path margin, 1.4 m standoff, 0.3 m vertical move
    and 3.5 m search radius. Aim the optical axis towards the estimated candidate.
    """
    target = location['xyz_m']
    # Triangulating a visible tip does not establish an unobstructed view of the
    # whole object. Score a small uncertainty volume around the predicted point.
    # Dimensions are acquisition priors, never a target-object lookup.
    volume = [target, [target[0], target[1], max(.05, target[2]-.35)],
              [target[0], target[1], target[2]+.2]]
    volume += [[target[0]+dx, target[1]+dy, max(.05, target[2]-.15)]
               for dx, dy in ((.18, 0), (-.18, 0), (0, .18), (0, -.18))]
    candidates = []
    for distance in (1.6, 2., 2.5, 3., 3.5):
        for i in range(36):
            a = i*math.tau/36
            x, y = target[0]+distance*math.cos(a), target[1]+distance*math.sin(a)
            if math.dist([x, y], position[:2]) > 3.5:
                continue
            centre = target[2]+distance*math.tan(math.radians(10))
            heights = {max(.9, min(1.8, position[2]+.3, max(position[2]-.3, centre))),
                       max(.9, min(1.8, position[2]+.3)), max(.9, min(1.8, position[2]))}
            for height in heights:
                pose = [x, y, height, math.atan2(target[1]-y, target[0]-x)]
                if clearance(geometry, pose) < .61:
                    continue
                if any(math.dist(pose[:3], p[:3]) < .3 for p in previous):
                    continue
                if not planned_parallax(reference, pose, location):
                    continue
                origin = [x+.12*math.cos(pose[3]), y+.12*math.sin(pose[3]), height+.02]
                if not visible_ray(geometry, origin, target):
                    continue
                off_axis = abs(math.atan2(height-target[2], distance)-math.radians(10))
                seen = 0
                for sample in volume:
                    depression = math.degrees(math.atan2(origin[2]-sample[2], math.dist(origin[:2], sample[:2])))
                    if -8.5 <= depression <= 28.5 and visible_ray(geometry, origin, sample):
                        seen += 1
                # Prefer visible object extent and usable pixel size over
                # perfectly centring one visible tip while remaining far away.
                coverage = seen/len(volume)
                # Acquisition prioritizes larger pixels. Confirmation instead
                # prioritizes keeping the object inside the fixed camera FOV;
                # moving closer again can clip it or put clutter in front.
                centering_weight, range_weight = (2., .7) if preserve_view else (.4, 1.5)
                cost = 6*(1-coverage)+centering_weight*off_axis+range_weight*distance+.1*math.dist(position, pose[:3])
                if preserve_view:
                    # Once pixels support identity, obtain parallax near that
                    # successful sightline instead of circling behind clutter.
                    cost += 1.5*math.dist(reference['origin'], origin)+abs(reference['origin'][2]-origin[2])
                candidates.append((cost, pose, coverage))
    result = []
    for cost, pose, coverage in sorted(candidates):
        try:
            path = flight_path(geometry, position, pose)
        except ValueError:
            continue
        result.append({'pose': pose, 'cost': cost, 'path': path, 'predicted_visible_fraction': coverage,
                       'source': 'predicted candidate uncertainty volume and operator geometry'})
        if len(result) == 8:
            break
    return result
