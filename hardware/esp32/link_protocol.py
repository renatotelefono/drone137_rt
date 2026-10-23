"""Device-side Drone137 wire state machine, shared with the network emulator.

No physics or model is implemented here. Time is the aircraft monotonic clock.
The ground service is the authenticated command producer; models never send
these low-level setpoints directly. See link-protocol.md for the wire contract.
"""
from dataclasses import dataclass
import hashlib
import json
import math
import re
import secrets
import time

VERSION = 1
MAX_DEADLINE_US = 250_000
CONTROL_TIMEOUT_US = 250_000
LEASE_US = 2_000_000
MAX_TILT_RAD = .26
MAX_YAW_RATE = 1.
MAX_THRUST = .8


class ProtocolError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def integer(value, name, minimum=0, maximum=2**63-1):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ProtocolError('Invalid '+name)
    return value


def number(value, name, minimum, maximum):
    if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ProtocolError('Invalid '+name)
    return float(value)


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', value):
        raise ProtocolError('Invalid client identity')
    return value


@dataclass
class Setpoint:
    roll_rad: float = 0.
    pitch_rad: float = 0.
    yaw_rate_rad_s: float = 0.
    thrust: float = 0.

    @classmethod
    def parse(cls, value):
        if not isinstance(value, dict) or set(value) != set(cls.__dataclass_fields__):
            raise ProtocolError('Expected roll, pitch, yaw rate and thrust')
        return cls(number(value['roll_rad'], 'roll', -MAX_TILT_RAD, MAX_TILT_RAD),
                   number(value['pitch_rad'], 'pitch', -MAX_TILT_RAD, MAX_TILT_RAD),
                   number(value['yaw_rate_rad_s'], 'yaw rate', -MAX_YAW_RATE, MAX_YAW_RATE),
                   number(value['thrust'], 'thrust', 0, MAX_THRUST))


class AircraftProtocol:
    def __init__(self, device_id, clock=None, *, flight_enabled=False):
        self.device_id = identifier(device_id)
        self.clock = clock or (lambda: time.monotonic_ns()//1000)
        self.boot_id = secrets.token_hex(16)
        self.flight_enabled = flight_enabled
        self.session_id = self.owner = None
        self.lease_until = self.control_until = 0
        self.last_sequence = -1
        self.last_digest = self.last_reply = None
        self.state = 'disarmed'
        self.reason = None
        self.setpoint = Setpoint()
        self.calibrated = False
        self.voltage_v = 0.
        self.imu_time_us = -1
        self.landing_started = None
        self.landing_thrust = 0.

    def sensor_health(self, *, calibrated, voltage_v, imu_time_us):
        self.calibrated = calibrated is True
        self.voltage_v = number(voltage_v, 'battery voltage', 0, 5)
        self.imu_time_us = integer(imu_time_us, 'IMU timestamp')

    def hello(self):
        self.tick()
        return {'protocol': VERSION, 'device_id': self.device_id, 'boot_id': self.boot_id,
                'clock_us': self.clock(), 'state': self.state, 'owner': self.owner,
                'flight_enabled': self.flight_enabled, 'calibrated': self.calibrated,
                'voltage_v': self.voltage_v, 'reason': self.reason,
                'setpoint': vars(self.setpoint),
                'limits': {'tilt_rad': MAX_TILT_RAD, 'yaw_rate_rad_s': MAX_YAW_RATE,
                           'thrust': MAX_THRUST, 'control_timeout_us': CONTROL_TIMEOUT_US}}

    def claim(self, client_id):
        client_id = identifier(client_id)
        self.tick()
        if self.state != 'disarmed':
            raise ProtocolError('Disarm before acquiring a new control session', 409)
        if self.owner is not None:
            raise ProtocolError('Control session already owned', 423)
        self.owner = client_id
        self.session_id = secrets.token_hex(16)
        self.lease_until = self.clock()+LEASE_US
        self.last_sequence = -1
        self.last_digest = self.last_reply = None
        return {'boot_id': self.boot_id, 'session_id': self.session_id,
                'clock_us': self.clock(), 'lease_until_us': self.lease_until}

    def _revoke(self):
        self.owner = self.session_id = None
        self.lease_until = 0

    def _land(self, reason):
        if self.state == 'armed':
            self.state = 'landing'
            self.reason = reason
            self.landing_started = self.clock()
            self.landing_thrust = self.setpoint.thrust
        self._revoke()

    def tick(self):
        now = self.clock()
        if self.state in ('armed', 'landing'):
            if self.imu_time_us > now or now-self.imu_time_us > 20_000:
                self.state = 'disarmed'
                self.reason = 'IMU unavailable'
                self.setpoint = Setpoint()
                self._revoke()
            elif self.state == 'armed' and now >= self.control_until:
                self._land('Setpoint expired')
            elif self.voltage_v < 3.2:
                self._land('Critical battery')
        if self.owner is not None and now >= self.lease_until:
            self._land('Control lease expired')
        if self.state == 'landing':
            # This is a bounded failsafe ramp, not a claim of altitude-aware
            # landing on a physical drone without a qualified height source.
            fraction = max(0., 1-(now-self.landing_started)/1_500_000)
            self.setpoint = Setpoint(thrust=self.landing_thrust*fraction)
            if fraction == 0:
                self.state = 'disarmed'

    def command(self, body):
        self.tick()
        if not isinstance(body, dict) or set(body) - {'boot_id','session_id','sequence','deadline_us','operation','setpoint'}:
            raise ProtocolError('Invalid command envelope')
        if body.get('boot_id') != self.boot_id:
            raise ProtocolError('Boot identity mismatch', 409)
        sequence = integer(body.get('sequence'), 'sequence', maximum=2**32-1)
        deadline = integer(body.get('deadline_us'), 'deadline')
        try:
            digest = hashlib.sha256(json.dumps(body, sort_keys=True, allow_nan=False).encode()).hexdigest()
        except (TypeError, ValueError) as exc:
            raise ProtocolError('Non-finite or invalid command') from exc
        if sequence == self.last_sequence:
            if digest != self.last_digest:
                raise ProtocolError('Sequence reused with different content', 409)
            # An exact retry returns its acknowledgement without renewing the
            # lease, extending the setpoint lifetime or repeating an action.
            return dict(self.last_reply, duplicate=True, state=self.state)
        if sequence < self.last_sequence:
            raise ProtocolError('Out-of-order command', 409)
        if not self.session_id or body.get('session_id') != self.session_id:
            raise ProtocolError('Control session mismatch', 409)
        now = self.clock()
        if not 0 < deadline-now <= MAX_DEADLINE_US:
            raise ProtocolError('Expired or excessive command deadline', 409)
        operation = body.get('operation')
        required={'boot_id','session_id','sequence','deadline_us','operation'}
        if operation == 'attitude':required.add('setpoint')
        if set(body) != required:
            raise ProtocolError('Command fields do not match operation')
        if operation == 'arm':
            if (self.state != 'disarmed' or not self.flight_enabled or not self.calibrated
                    or not 0 <= now-self.imu_time_us <= 20_000 or not 3.8 <= self.voltage_v <= 4.25):
                raise ProtocolError('Aircraft does not meet arming checks', 409)
            self.state = 'armed'
            self.reason = None
            self.setpoint = Setpoint()
            self.control_until = min(deadline, now+CONTROL_TIMEOUT_US)
        elif operation == 'attitude':
            if self.state != 'armed':
                raise ProtocolError('Aircraft is not armed', 409)
            self.setpoint = Setpoint.parse(body.get('setpoint'))
            self.control_until = min(deadline, now+CONTROL_TIMEOUT_US)
        elif operation == 'heartbeat':
            pass  # Heartbeats never renew motor setpoints.
        elif operation == 'land':
            self._land('Operator requested landing ramp')
        elif operation == 'disarm':
            self.state = 'disarmed'
            self.reason = 'Operator disarmed'
            self.setpoint = Setpoint()
            self._revoke()
        else:
            raise ProtocolError('Unsupported operation')
        if self.owner is not None:
            self.lease_until = now+LEASE_US
        self.last_sequence, self.last_digest = sequence, digest
        self.last_reply = {'accepted': True, 'sequence': sequence, 'clock_us': now, 'state': self.state}
        return dict(self.last_reply)

    def emergency(self, body):
        """Authenticated stop does not wait for the current owner's lease."""
        if (not isinstance(body, dict) or set(body) != {'boot_id', 'deadline_us', 'operation'}
                or body.get('boot_id') != self.boot_id):
            raise ProtocolError('Boot identity mismatch', 409)
        now = self.clock()
        deadline = integer(body.get('deadline_us'), 'deadline')
        if not 0 < deadline-now <= MAX_DEADLINE_US:
            raise ProtocolError('Expired emergency request', 409)
        if body.get('operation') == 'land':
            self._land('Emergency landing ramp')
        elif body.get('operation') == 'disarm':
            self.state = 'disarmed'
            self.reason = 'Emergency disarm'
            self.setpoint = Setpoint()
            self._revoke()
        else:
            raise ProtocolError('Emergency action must be land or disarm')
        return {'accepted': True, 'state': self.state}
