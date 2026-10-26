"""Manual stick control through the console: bounded setpoints over the same pinned link.

The operator's keyboard or gamepad becomes attitude setpoints at 20 Hz inside a reduced
manual envelope. Releasing the sticks levels the aircraft at the current thrust trim; no
input at all for 1.5 s lands it; the aircraft's own 250 ms setpoint expiry and lease stay
in force underneath. Manual control is refused while a mission is active and while another
manual session owns the aircraft. Nothing here runs a model.
"""
import asyncio
import math
import time

from aiohttp import ClientError

from hardware.esp32.link_client import AircraftLink
from hardware.esp32.link_protocol import MAX_THRUST, MAX_TILT_RAD, MAX_YAW_RATE, ProtocolError

MANUAL_LIMITS = {'tilt_rad': .13, 'yaw_rate_rad_s': .5, 'thrust': .6}
RATE_HZ = 20.
STICK_RELEASE_S = .3     # no fresh input: level, hold trim
INPUT_LOST_S = 1.5       # no input at all: land
FIELDS = ('roll_rad', 'pitch_rad', 'yaw_rate_rad_s', 'thrust')


def clamp(value, limit, name):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f'{name} must be a finite number')
    return float(max(-limit, min(limit, value)))


class ManualSession:
    def __init__(self, connection, *, mission_busy=lambda: False, limits=None, rate_hz=RATE_HZ, clock=time.monotonic):
        self.connection, self.mission_busy, self.clock = connection, mission_busy, clock
        self.limits = dict(MANUAL_LIMITS, **(limits or {}))
        if not (0 < self.limits['tilt_rad'] <= MAX_TILT_RAD and 0 < self.limits['yaw_rate_rad_s'] <= MAX_YAW_RATE
                and 0 < self.limits['thrust'] <= MAX_THRUST):
            raise ValueError('Manual limits exceed the aircraft envelope')
        self.period = 1./rate_hz
        self.state = 'idle'
        self.error = None
        self.setpoint = {k: 0. for k in FIELDS}
        self.trim = 0.
        self.last_input = None
        self.started = None
        self.inputs = self.commands = 0
        self.aircraft_state = None
        self.task = None
        self.failures = self.consecutive_failures = 0
        self.lock = asyncio.Lock()
        # Manual control owns its own pinned link, like the stop channel does: a sensor-monitor
        # fault must not revoke the sticks, and the 20 Hz stream must not starve the IMU polls.
        self.link = None
        self.last_sync = 0.

    @property
    def active(self):
        return self.state in ('armed',)

    async def start(self):
        async with self.lock:
            if self.active:
                raise ProtocolError('Manual control is already active', 409)
            if self.mission_busy():
                raise ProtocolError('A mission is active; manual control is refused', 409)
            if self.connection.state != 'connected':
                raise ProtocolError('Connect the aircraft first', 409)
            self.error = None
            source = self.connection.link
            link = AircraftLink(source.url, source.fingerprint.fingerprint.hex(), source.credential, 'drone137-manual')
            try:
                hello = await link.start()
                self.connection.check_identity(hello)
                await link.claim()
                result = await link.command('arm')
            except Exception:
                self.state = 'fault'
                await link.close()
                raise
            self.link = link
            self.last_sync = self.clock()
            self.aircraft_state = result.get('state')
            self.setpoint = {k: 0. for k in FIELDS}
            self.trim = 0.
            self.last_input = None
            self.started = self.clock()
            self.inputs = self.commands = 0
            self.state = 'armed'
            self.task = asyncio.create_task(self.pump())
            return self.snapshot()

    def input(self, value):
        """One stick sample from the console; clamped to the manual envelope."""
        if self.state != 'armed':
            raise ProtocolError('Manual control is not active', 409)
        if not isinstance(value, dict) or set(value) != set(FIELDS):
            raise ValueError('Expected roll_rad, pitch_rad, yaw_rate_rad_s and thrust')
        l = self.limits
        thrust = clamp(value['thrust'], l['thrust'], 'thrust')
        self.setpoint = {'roll_rad': clamp(value['roll_rad'], l['tilt_rad'], 'roll'),
                         'pitch_rad': clamp(value['pitch_rad'], l['tilt_rad'], 'pitch'),
                         'yaw_rate_rad_s': clamp(value['yaw_rate_rad_s'], l['yaw_rate_rad_s'], 'yaw rate'),
                         'thrust': max(0., thrust)}
        self.trim = self.setpoint['thrust']
        self.last_input = self.clock()
        self.inputs += 1
        return self.snapshot()

    def current(self):
        """What the pump sends now: the sticks, levelled after a short silence."""
        age = None if self.last_input is None else self.clock() - self.last_input
        if age is None or age > STICK_RELEASE_S:
            return {'roll_rad': 0., 'pitch_rad': 0., 'yaw_rate_rad_s': 0., 'thrust': self.trim}, age
        return dict(self.setpoint), age

    async def pump(self):
        try:
            while self.state == 'armed':
                setpoint, age = self.current()
                lost = (self.started is not None and self.last_input is None and self.clock() - self.started > INPUT_LOST_S) \
                    or (age is not None and age > INPUT_LOST_S)
                if lost:
                    await self.finish('land', 'No operator input for 1.5 s')
                    return
                try:
                    if self.clock() - self.last_sync > 3.:
                        self.connection.check_identity(await self.link.synchronize())
                        self.last_sync = self.clock()
                    result = await self.link.command('attitude', setpoint=setpoint)
                except (TimeoutError, OSError, ClientError, ProtocolError) as exc:
                    # One late or lost setpoint is survivable: the aircraft keeps the previous one until
                    # its 250 ms expiry and the next arrives in 50 ms. A lost session or a run of
                    # failures is not, and ends in the landing ramp.
                    transient = (not isinstance(exc, ProtocolError)) or exc.status == 409 and str(exc).startswith(('Expired', 'Mismatched', 'Aircraft clock'))
                    self.failures += 1; self.consecutive_failures += 1
                    if not transient or self.consecutive_failures >= 4:
                        raise
                    self.error = f'setpoint retry after {type(exc).__name__}: {exc}'[:160]
                    await asyncio.sleep(self.period)
                    continue
                self.consecutive_failures = 0
                self.aircraft_state = result.get('state')
                self.commands += 1
                if self.aircraft_state != 'armed':
                    self.state, self.error = 'ended', 'Aircraft left the armed state: ' + str(self.aircraft_state)
                    return
                await asyncio.sleep(self.period)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.state = 'fault'
            self.error = (str(exc)[:160] if isinstance(exc, ProtocolError) else 'Aircraft link failed during manual control')
            # The aircraft's own expiry lands it; ask for the ramp explicitly through the stop channel too.
            try:
                await self.connection.stop('land')
            except Exception:
                pass
            if self.link:
                await self.link.close()
                self.link = None

    async def finish(self, operation, reason):
        self.state = 'landing'
        self.error = reason
        try:
            result = await self.link.command(operation)
            self.aircraft_state = result.get('state')
        except Exception as exc:
            self.error = reason + '; ' + (str(exc)[:120] if isinstance(exc, ProtocolError) else 'link failed')
            try:
                await self.connection.stop('land')
            except Exception:
                pass
        finally:
            self.state = 'ended'

    async def land(self):
        """Operator lands: the aircraft's bounded ramp, then the session ends."""
        async with self.lock:
            if self.state != 'armed':
                raise ProtocolError('Manual control is not active', 409)
            if self.task and self.task is not asyncio.current_task():
                self.task.cancel()
                await asyncio.gather(self.task, return_exceptions=True)
            await self.finish('land', 'Operator landed')
            return self.snapshot()

    async def close(self):
        if self.task and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        if self.state == 'armed':
            await self.finish('land', 'Manual control closed')
        if self.link:
            await self.link.close()
            self.link = None

    def snapshot(self):
        setpoint, age = self.current()
        return {'state': self.state, 'error': self.error, 'aircraft_state': self.aircraft_state,
                'setpoint': setpoint, 'trim': self.trim, 'input_age_s': age, 'inputs': self.inputs, 'commands': self.commands, 'failures': self.failures,
                'limits': dict(self.limits), 'rate_hz': 1./self.period,
                'stick_release_s': STICK_RELEASE_S, 'input_lost_s': INPUT_LOST_S}
