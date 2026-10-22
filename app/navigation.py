"""Geometry-free mapping and local route planning shared by vehicle backends.

Coordinates are metres, x east / y north / z up. Yaw and scan angles are radians
counterclockwise from east. Only timestamped sensor returns enter this map.
"""
from collections import deque
from dataclasses import dataclass
import math

CELL = .5
RADIUS, MARGIN, SPEED, BRAKE = .18, .12, .6, 1.0


@dataclass(frozen=True)
class VelocityCommand:
    east_m_s: float
    north_m_s: float
    yaw_rad: float


class ObservedMap:
    def __init__(self, width=12., depth=10., home=(1.25, 1.25)):
        self.width, self.depth, self.home = width, depth, home
        self.nx, self.ny = int(width/CELL), int(depth/CELL)
        self.grid = [0]*(self.nx*self.ny)
        self.evidence = [0]*(self.nx*self.ny)
        self.blocked = set()

    def cell(self, x, y):
        return int(y/CELL)*self.nx+int(x/CELL)

    def center(self, cell):
        return ((cell % self.nx+.5)*CELL, (cell//self.nx+.5)*CELL)

    def integrate(self, pose, ranges, now):
        x, y = pose[:2]
        if not (0 <= x < self.width and 0 <= y < self.depth):
            raise RuntimeError('Position outside permitted area')
        updates = {}
        for ray in ranges:
            if not ray['valid'] or not 0 <= now-ray['time'] <= .35:
                continue
            distance = ray['distance']
            if not math.isfinite(distance) or not 0 < distance <= ray['max_range']:
                continue
            free, endpoint = set(), None
            for step in range(1, math.ceil(distance/.04)+1):
                along = min(step*.04, distance)
                px = x+math.cos(ray['angle'])*along
                py = y+math.sin(ray['angle'])*along
                if not (0 <= px < self.width and 0 <= py < self.depth):
                    break
                index = self.cell(px, py)
                if ray['hit'] and along >= distance-1e-8:
                    endpoint = index
                elif not ray['hit'] or along < distance-.04:
                    free.add(index)
            if endpoint is not None:
                free.discard(endpoint)
                updates[endpoint] = updates.get(endpoint, 0)+3
            for index in free:
                updates[index] = updates.get(index, 0)-1
        # Repeated free-space evidence can correct an isolated quantized corner
        # hit. Sticky occupied cells otherwise accumulate until a used doorway
        # vanishes from the map. Count each cell once per beam, not per sample.
        for index, delta in updates.items():
            self.evidence[index] = max(-6, min(6, self.evidence[index]+max(-3,min(3,delta))))
            self.grid[index] = 2 if self.evidence[index] >= 2 else 1 if self.evidence[index] <= -1 else 0
        current = self.cell(x,y)
        self.grid[current], self.evidence[current] = 1, -6

    def neighbors(self, cell):
        x, y = cell % self.nx, cell//self.nx
        for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)):
            if 0 <= x+dx < self.nx and 0 <= y+dy < self.ny:
                yield (y+dy)*self.nx+x+dx

    def safe_cell(self, cell):
        x, y = cell % self.nx, cell//self.nx
        if cell in self.blocked or x < 1 or y < 1 or x >= self.nx-1 or y >= self.ny-1 or self.grid[cell] != 1:
            return False
        # Inflate unknown/occupied cells by the vehicle radius, margin and range
        # quantization. A diagonal cell starts sqrt(2)*CELL/2 away from this
        # centre, beyond that disc. Requiring all eight neighbors unnecessarily
        # closes an observed 2 m doorway after a quantized corner return.
        inflation = RADIUS+MARGIN+.04
        return all(self.grid[(y+dy)*self.nx+x+dx] == 1
                   for dx in (-1,0,1) for dy in (-1,0,1)
                   if math.hypot(max(0,abs(dx)*CELL-CELL/2),
                                 max(0,abs(dy)*CELL-CELL/2)) <= inflation)

    def plan(self, pose, visited, returning=False, goal=None):
        start = self.cell(*pose[:2])
        target = self.cell(*(self.home if returning else goal)) if returning or goal else None
        if target == start:
            # Entering the goal cell is not the same as reaching its centre.
            # Replanning inside the home cell must finish the approach.
            return [target] if self.safe_cell(target) and math.dist(pose[:2], self.center(target)) > .001 else []
        queue, parent, candidates = deque([start]), {start: None}, []
        while queue:
            current = queue.popleft()
            if target is not None and current == target:
                break
            if target is None and current not in visited and current != start:
                unknown = sum(self.grid[n] == 0 for n in self.neighbors(current))
                candidates.append((unknown, current))
            for neighbor in self.neighbors(current):
                if neighbor not in parent and self.safe_cell(neighbor):
                    parent[neighbor] = current
                    queue.append(neighbor)
        if target is None:
            frontiers = [c for unknown, c in candidates if unknown]
            target = (frontiers or [c for _, c in candidates] or [None])[0]
        if target is None or target not in parent:
            return []
        path = []
        while target != start:
            path.append(target)
            target = parent[target]
        return list(reversed(path))


def supervised_velocity(pose, speed, target, ranges, dt, now):
    """Return a bounded velocity, or None when a fresh range blocks this step."""
    dx, dy = target[0]-pose[0], target[1]-pose[1]
    distance, angle = math.hypot(dx, dy), math.atan2(dy, dx)
    needed = RADIUS+MARGIN+speed*.2+speed*speed/(2*BRAKE)
    forward = [r for r in ranges if abs(math.atan2(math.sin(r['angle']-angle),
                                                   math.cos(r['angle']-angle))) < .3]
    if not forward or any(not r['valid'] or not 0 <= now-r['time'] <= .35
                          or not math.isfinite(r['distance']) for r in forward):
        raise RuntimeError('Forward range unavailable: motion stopped')
    if min(r['distance'] for r in forward) <= needed:
        return None
    # A narrow forward cone misses obstacles beside a turning vehicle. Check
    # the whole swept disc, allowing for range quantization and angular spacing.
    for ray in ranges:
        if not ray['valid'] or not ray['hit']:
            continue
        relative = ray['angle']-angle
        along, across = ray['distance']*math.cos(relative), abs(ray['distance']*math.sin(relative))
        radius = RADIUS+MARGIN+.04+ray['distance']*math.sin(math.pi/72)
        if along > 0 and across < radius:
            remaining = along-math.sqrt(max(0, radius*radius-across*across))
            if remaining <= speed*.2+speed*speed/(2*BRAKE):
                return None
    velocity = min(SPEED, speed+BRAKE*dt, math.sqrt(max(0, 2*BRAKE*distance)), distance/dt)
    return VelocityCommand(math.cos(angle)*velocity, math.sin(angle)*velocity, angle)
