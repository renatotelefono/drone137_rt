import unittest

from hardware.esp32.link_protocol import AircraftProtocol, ProtocolError


class AircraftProtocolTests(unittest.TestCase):
    def setUp(self):
        self.now = 1_000_000
        self.device = AircraftProtocol('test-aircraft', lambda: self.now, flight_enabled=True)
        self.refresh()
        self.session = self.device.claim('ground-pc')['session_id']
        self.sequence = 0

    def refresh(self):
        self.device.sensor_health(calibrated=True, voltage_v=4., imu_time_us=self.now)

    def command(self, operation, **extra):
        self.sequence += 1
        body = dict(boot_id=self.device.boot_id, session_id=self.session,
                    sequence=self.sequence, deadline_us=self.now+200_000,
                    operation=operation, **extra)
        return body, self.device.command(body)

    def test_exclusive_ownership_and_no_replay_across_reboot(self):
        with self.assertRaises(ProtocolError):self.device.claim('other-pc')
        body, _ = self.command('arm')
        reboot = AircraftProtocol('test-aircraft', lambda: self.now, flight_enabled=True)
        with self.assertRaises(ProtocolError):reboot.command(body)

    def test_duplicate_is_idempotent_without_extending_motor_lifetime(self):
        body, reply = self.command('arm')
        expiry = self.device.control_until
        self.now += 50_000
        self.refresh()
        self.assertTrue(self.device.command(body)['duplicate'])
        self.assertEqual(self.device.control_until, expiry)
        with self.assertRaises(ProtocolError):self.device.command(dict(body,operation='disarm'))
        body, _ = self.command('disarm')
        self.assertTrue(self.device.command(body)['duplicate'])

    def test_heartbeat_does_not_keep_expired_thrust_alive(self):
        self.command('arm')
        self.command('attitude', setpoint=dict(roll_rad=.1,pitch_rad=0,yaw_rate_rad_s=0,thrust=.5))
        self.now += 150_000
        self.refresh()
        self.command('heartbeat')
        self.now += 60_000
        self.refresh()
        self.device.tick()
        self.assertEqual(self.device.state,'landing')
        self.assertIsNone(self.device.owner)
        self.assertEqual(self.device.setpoint.roll_rad,0)
        self.now += 1_600_000
        self.refresh()
        self.device.tick()
        self.assertEqual(self.device.state,'disarmed')
        self.assertEqual(self.device.setpoint.thrust,0)

    def test_unavailable_imu_disarms_even_during_failsafe_ramp(self):
        self.command('arm')
        self.device.emergency(dict(boot_id=self.device.boot_id,deadline_us=self.now+100_000,operation='land'))
        self.now += 21_000
        self.device.tick()
        self.assertEqual(self.device.state,'disarmed')
        self.assertEqual(self.device.reason,'IMU unavailable')

    def test_deadline_and_input_bounds_cannot_be_bypassed(self):
        body, _ = self.command('arm')
        for invalid in (dict(body, sequence=2, deadline_us=self.now),
                        dict(body, sequence=2, deadline_us=self.now+999_999),
                        dict(body, sequence=True)):
            with self.assertRaises(ProtocolError):self.device.command(invalid)
        for key,value in [('roll_rad',1.),('thrust',float('nan')),('thrust',True)]:
            point=dict(roll_rad=0,pitch_rad=0,yaw_rate_rad_s=0,thrust=.5)
            point[key]=value
            with self.assertRaises(ProtocolError):self.command('attitude',setpoint=point)

    def test_emergency_revokes_control_and_blocks_old_setpoints(self):
        self.command('arm')
        old, _ = self.command('attitude',setpoint=dict(roll_rad=0,pitch_rad=0,yaw_rate_rad_s=0,thrust=.5))
        self.device.emergency(dict(boot_id=self.device.boot_id,deadline_us=self.now+100_000,operation='disarm'))
        with self.assertRaises(ProtocolError):self.device.command(dict(old,sequence=old['sequence']+1))
        self.assertEqual(self.device.setpoint.thrust,0)

    def test_uncommissioned_aircraft_refuses_arming(self):
        self.device.flight_enabled=False
        with self.assertRaises(ProtocolError):self.command('arm')
        self.assertEqual(self.device.state,'disarmed')

    def test_overvoltage_and_extra_emergency_fields_are_rejected(self):
        self.device.voltage_v = 4.6
        with self.assertRaises(ProtocolError):self.command('arm')
        with self.assertRaises(ProtocolError):
            self.device.emergency(dict(boot_id=self.device.boot_id, deadline_us=self.now+100_000,
                                       operation='disarm', thrust=.5))

    def test_expired_owner_cannot_resume_without_new_session(self):
        self.now += 2_100_000
        self.device.tick()
        new = self.device.claim('second-pc')['session_id']
        self.assertNotEqual(self.session,new)
        with self.assertRaises(ProtocolError):self.command('heartbeat')


if __name__ == '__main__':unittest.main()
