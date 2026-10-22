"""Ideal virtual vehicle. Hidden geometry stays on this side of the adapter."""
import math

from app.navigation import RADIUS, MARGIN, SPEED, VelocityCommand
from sim.recon_world import clearance, ray_distance


class KinematicVehicle:
    identity = 'ideal-kinematic'
    physical_transport = False
    real_flight_dynamics = False

    def __init__(self, scene):
        self.reset(scene)

    def reset(self, scene):
        self.scene = scene
        self.pose = [1.25, 1.25, 1.4, 0.]
        self.speed = 0.
        self.minimum_clearance = 100.

    def ranges(self, now):
        x, y = self.pose[:2]
        rays = []
        for i in range(72):
            angle = i*2*math.pi/72
            distance, hit = ray_distance(self.scene, x, y, angle)
            rays.append({'angle': angle, 'distance': distance, 'hit': hit,
                         'valid': True, 'time': now, 'max_range': 3.})
        return rays

    def advance(self, command: VelocityCommand, dt):
        values = (command.east_m_s, command.north_m_s, command.yaw_rad, dt)
        speed = math.hypot(command.east_m_s, command.north_m_s)
        if not all(math.isfinite(v) for v in values) or not 0 < dt <= .15 or speed > SPEED+1e-8:
            raise ValueError('Invalid virtual velocity command')
        x = self.pose[0]+command.east_m_s*dt
        y = self.pose[1]+command.north_m_s*dt
        gap = clearance(self.scene, x, y)-RADIUS
        self.minimum_clearance = min(self.minimum_clearance, gap)
        if gap < MARGIN:
            self.hold()
            raise RuntimeError('Simulator collision guard intervened; mission failed')
        self.pose[:2], self.pose[3], self.speed = [x, y], command.yaw_rad, speed

    def hold(self):
        self.speed = 0.

    def look(self, yaw):
        if not math.isfinite(yaw):
            raise ValueError('Invalid observation yaw')
        self.hold()
        self.pose[3] = yaw
