"""Tests execute the controller compiled for both ESP32 and this host."""
import json
import math
import unittest
from hardware.esp32.flight_host import Firmware


class FirmwareTest(unittest.TestCase):
    def setUp(self):
        self.fw = Firmware(enabled=True)
        self.addCleanup(self.fw.close)
        self.now = 0
        self.seq = 0
        self.session = None

    def advance(self, seconds, **sample):
        for _ in range(round(seconds/.002)):
            self.now += 2000
            self.fw.imu(self.now, **sample)

    def command(self, operation, **extra):
        self.seq += 1
        body = dict(boot_id=self.fw.boot_id, session_id=self.session,
                    deadline_us=self.now+240000, sequence=self.seq, operation=operation, **extra)
        return self.fw.request('/v1/command', body, self.now)

    def arm(self):
        self.advance(9.1)
        status, reply = self.fw.request('/v1/session', {'client_id': 'test'}, self.now)
        self.assertEqual(status, 200)
        self.session = reply['session_id']
        self.assertEqual(self.command('arm')[0], 200)

    def attitude(self, **values):
        return self.command('attitude', setpoint=dict(roll_rad=values.get('roll', 0),
                            pitch_rad=values.get('pitch', 0), yaw_rate_rad_s=values.get('yaw', 0),
                            thrust=values.get('thrust', .5)))

    def test_restrained_rig_is_bounded_and_not_commissioned(self):
        self.fw.lib.d137_rig(self.fw.ptr);self.arm()
        self.assertFalse(self.fw.hello(self.now)['commissioned'])
        self.assertTrue(self.fw.hello(self.now)['restrained_rig'])
        self.assertEqual(self.attitude(thrust=.7)[0],400)
        for _ in range(49):
            self.assertEqual(self.attitude(thrust=.45)[0],200);self.advance(.1)
        self.attitude(thrust=.45);self.advance(.102)
        h=self.fw.hello(self.now)
        self.assertEqual(h['state'],'disarmed');self.assertEqual(h['controller']['motor_duty'],[0]*4)
        self.assertFalse(h['physical_flight_qualified'])

    def test_boot_and_default_build_cannot_arm(self):
        safe = Firmware()
        self.addCleanup(safe.close)
        for t in range(2000, 9200000, 2000): safe.imu(t)
        _, reply = safe.request('/v1/session', {'client_id': 'test'}, 9198000)
        status, _ = safe.request('/v1/command', dict(boot_id=safe.boot_id,
            session_id=reply['session_id'], deadline_us=9300000, sequence=1, operation='arm'), 9198000)
        self.assertEqual(status, 409)
        self.assertEqual(safe.hello(9198000)['controller']['motor_duty'], [0]*4)

    def test_calibration_requires_stationary_samples(self):
        self.advance(10, gyro=(.2, 0, 0))
        self.assertFalse(self.fw.hello(self.now)['calibrated'])
        self.advance(9.1)
        self.assertTrue(self.fw.hello(self.now)['calibrated'])

    def test_motor_order_and_positive_torques(self):
        self.arm()
        for axis, pairs in [('roll', [(3, 0), (2, 1)]), ('pitch', [(1, 0), (2, 3)]),
                            ('yaw', [(0, 1), (2, 3)])]:
            self.attitude(**{axis: .1})
            self.advance(.002)
            motors = self.fw.hello(self.now)['controller']['motor_duty']
            for higher, lower in pairs: self.assertGreater(motors[higher], motors[lower])

    def test_wifi_or_inference_loss_expires_even_with_heartbeat(self):
        self.arm(); self.attitude()
        for _ in range(5):
            self.advance(.1); self.command('heartbeat')
        self.assertEqual(self.fw.hello(self.now)['state'], 'landing')
        self.advance(1.5)
        self.assertEqual(self.fw.hello(self.now)['controller']['motor_duty'], [0]*4)

    def test_imu_loss_disarms_and_latches(self):
        self.arm(); self.attitude(); self.advance(.01)
        self.now += 21000; self.fw.tick(self.now)
        hello = self.fw.hello(self.now)
        self.assertTrue(hello['fault_latched'])
        self.assertEqual(hello['controller']['motor_duty'], [0]*4)
        self.advance(.1)
        self.assertFalse(self.fw.hello(self.now)['flight_enabled'])

    def test_low_battery_ramp_and_invalid_battery_disarm(self):
        self.arm(); self.attitude(); self.advance(.01, voltage=3.1)
        self.assertEqual(self.fw.hello(self.now)['state'], 'landing')
        self.advance(.002, voltage=2.7)
        self.assertEqual(self.fw.hello(self.now)['state'], 'disarmed')

    def test_invalid_sensor_is_latched(self):
        self.arm(); self.attitude(); self.advance(.002, gyro=(math.nan, 0, 0))
        self.assertTrue(self.fw.hello(self.now)['fault_latched'])

    def test_emergency_revokes_session(self):
        self.arm(); self.attitude(); self.advance(.01)
        status, _ = self.fw.request('/v1/emergency', dict(boot_id=self.fw.boot_id,
            operation='disarm', deadline_us=self.now+100000), self.now)
        self.assertEqual(status, 200)
        self.assertEqual(self.attitude()[0], 409)
        self.assertEqual(self.fw.hello(self.now)['controller']['motor_duty'], [0]*4)

    def test_reboot_cannot_accept_old_session(self):
        self.arm()
        self.fw.close(); self.fw = Firmware(enabled=True)
        self.addCleanup(self.fw.close)
        self.assertEqual(self.attitude()[0], 409)
        self.assertEqual(self.fw.hello(self.now)['state'], 'disarmed')

    def test_malformed_parser_and_bounded_messages(self):
        for raw in ('{"client_id":"a","client_id":"b"}', '{"client_id":true}',
                    '{"client_id":"x","extra":1}', '[]', '{', '['*100+']'*100,
                    '{"client_id":"'+'x'*2000+'"}', '{"client_id":"a"} {}'):
            with self.subTest(raw=raw[:40]):
                self.assertEqual(self.fw.request('/v1/session', raw, self.now)[0], 400)

    def test_bench_motor_pulse_is_single_motor_and_time_bounded(self):
        self.fw.lib.d137_bench(self.fw.ptr,True)
        self.advance(9.1)
        _,reply=self.fw.request('/v1/session',{'client_id':'bench'},self.now)
        self.session=reply['session_id']
        status,_=self.command('motor_test',motor=2,duty=.15,duration_ms=100)
        self.assertEqual(status,200)
        self.advance(.04)
        self.assertEqual(self.fw.hello(self.now)['controller']['motor_duty'],[0,0,.15,0])
        self.assertEqual(self.command('arm')[0],409)
        self.advance(.08)
        self.assertEqual(self.fw.hello(self.now)['controller']['motor_duty'],[0]*4)

    def test_bench_pulse_refuses_excess_and_stops_on_sensor_gap(self):
        self.fw.lib.d137_bench(self.fw.ptr,True);self.advance(9.1)
        _,reply=self.fw.request('/v1/session',{'client_id':'bench'},self.now);self.session=reply['session_id']
        for extra in [dict(motor=4,duty=.1,duration_ms=100),dict(motor=0,duty=.3,duration_ms=100),
                      dict(motor=0,duty=.1,duration_ms=500)]:
            self.assertEqual(self.command('motor_test',**extra)[0],400)
        self.assertEqual(self.command('motor_test',motor=0,duty=.1,duration_ms=200)[0],200)
        self.now+=30000;self.fw.imu(self.now)
        self.assertTrue(self.fw.hello(self.now)['fault_latched'])
        self.assertEqual(self.fw.hello(self.now)['controller']['motor_duty'],[0]*4)

    def test_embedded_nul_does_not_truncate_identity(self):
        raw='{"client_id":"a'+chr(92)+'u0000b"}'
        self.assertEqual(self.fw.request('/v1/session',raw,self.now)[0],400)

    def test_retries_do_not_extend_thrust(self):
        self.arm()
        body = dict(boot_id=self.fw.boot_id, session_id=self.session, sequence=2,
                    operation='attitude', deadline_us=self.now+100000,
                    setpoint=dict(roll_rad=0, pitch_rad=0, yaw_rate_rad_s=0, thrust=.5))
        self.assertEqual(self.fw.request('/v1/command', body, self.now)[0], 200)
        self.advance(.09)
        self.assertTrue(self.fw.request('/v1/command', body, self.now)[1]['duplicate'])
        changed = dict(body, deadline_us=self.now+200000)
        self.assertEqual(self.fw.request('/v1/command', changed, self.now)[0], 409)
        self.advance(.02)
        self.assertEqual(self.fw.hello(self.now)['state'], 'landing')

    def test_attitude_closed_loop_with_motor_lag(self):
        # Independent rigid-body attitude plant, not a claim about real gains.
        self.arm()
        angles = [0., 0., 0.]; rates = [0., 0., 0.]; motors = [.5]*4
        goal = [.12, -.09, .2]
        maxima = [0.]*3
        for i in range(2500):
            if i % 25 == 0: self.attitude(roll=goal[0], pitch=goal[1], yaw=goal[2])
            duties = self.fw.hello(self.now)['controller']['motor_duty']
            for j in range(4): motors[j] += .002/.025*(duties[j]-motors[j])
            torque = [(-motors[0]-motors[1]+motors[2]+motors[3])*.0389*.35,
                      (-motors[0]+motors[1]+motors[2]-motors[3])*.0389*.35,
                      (motors[0]-motors[1]+motors[2]-motors[3])*.002]
            for j, inertia in enumerate((.00008, .00008, .00015)):
                rates[j] += .002*(torque[j]/inertia-.8*rates[j])
            r, p, _ = angles
            # Body angular velocity is not Euler-angle velocity.
            euler_rates = [rates[0]+math.sin(r)*math.tan(p)*rates[1]+math.cos(r)*math.tan(p)*rates[2],
                           math.cos(r)*rates[1]-math.sin(r)*rates[2],
                           (math.sin(r)*rates[1]+math.cos(r)*rates[2])/math.cos(p)]
            for j in range(3):
                angles[j] += .002*euler_rates[j]
                maxima[j] = max(maxima[j], abs(angles[j]))
            r, p, _ = angles
            self.now += 2000
            self.fw.imu(self.now, rates, (-9.80665*math.sin(p), 9.80665*math.sin(r)*math.cos(p),
                                         9.80665*math.cos(r)*math.cos(p)))
        self.assertEqual(self.fw.hello(self.now)['state'], 'armed')
        self.assertLess(abs(angles[0]-goal[0]), .015)
        self.assertLess(abs(angles[1]-goal[1]), .015)
        self.assertLess(abs(rates[2]-goal[2]), .04)
        self.assertLess(max(maxima[:2]), .22)


if __name__ == '__main__': unittest.main()
