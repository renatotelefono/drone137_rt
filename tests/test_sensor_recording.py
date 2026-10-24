import hashlib,json,tempfile,unittest
from pathlib import Path
from hardware.esp32.sensor_recording import replay_inputs

class ReplayContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.image=b'fixture-jpeg-payload'
        (self.root/'one.jpg').write_bytes(self.image)
        self.samples=[dict(time_us=100000+i*2000,gyro_flu_rad_s=[0,0,0],specific_force_flu_m_s2=[0,0,9.80665]) for i in range(20)]
        self.packet=dict(boot_id='boot',overrun=False,samples=self.samples)
        self.record=dict(device_id='scout',boot_id='boot',kind='protocol-emulator',complete=True,frames=[dict(path='one.jpg',capture_time_us=110000,boot_id='boot',width=640,height=480,sha256=hashlib.sha256(self.image).hexdigest())])
        self.cal=dict(device_id='scout',source_kind='measured',passed=True,camera_to_imu_time_offset_us=1000,launch_imu_height_m=.05,optics=dict(width=640,height=480,fx=300,fy=300,cx=320,cy=240,distortion=[0]*5),mount=dict(pitch_degrees=0,body_offset_flu_m=[.01,0,0]))
        self.save()
    def tearDown(self):self.tmp.cleanup()
    def save(self):
        raw=(json.dumps(self.packet)+'\n').encode();(self.root/'imu.jsonl').write_bytes(raw)
        self.record['imu_sha256']=hashlib.sha256(raw).hexdigest()
        (self.root/'recording.json').write_text(json.dumps(self.record))
        (self.root/'calibration.json').write_text(json.dumps(self.cal))
    def inputs(self):return replay_inputs(self.root,self.root/'calibration.json')
    def test_common_epoch_uses_measured_clock_offset(self):
        _,cal,epoch,samples,frames=self.inputs()
        self.assertEqual(epoch,100000);self.assertEqual(frames[0][0],111000);self.assertEqual(cal['width'],640)
    def test_calibration_identity_and_measurement_required(self):
        for key,value in [('device_id','another'),('source_kind','provisional'),('passed',False)]:
            old=self.cal[key];self.cal[key]=value;self.save()
            with self.assertRaises(ValueError):self.inputs()
            self.cal[key]=old
    def test_changed_image_and_imu_are_rejected(self):
        (self.root/'one.jpg').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'Image evidence changed'):self.inputs()
        (self.root/'one.jpg').write_bytes(self.image);(self.root/'imu.jsonl').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'IMU evidence changed'):self.inputs()
    def test_sensor_gap_and_reboot_rejected(self):
        self.samples[4]['time_us']+=30000;self.save()
        with self.assertRaisesRegex(ValueError,'unordered'):self.inputs()
        self.samples[4]['time_us']-=30000;self.packet['boot_id']='reboot';self.save()
        with self.assertRaisesRegex(ValueError,'Discontinuous'):self.inputs()
    def test_paths_nonfinite_values_and_partial_recordings_rejected(self):
        self.record['frames'][0]['path']='../outside.jpg';self.save()
        with self.assertRaisesRegex(ValueError,'escapes'):self.inputs()
        self.record['frames'][0]['path']='one.jpg';self.samples[2]['gyro_flu_rad_s'][0]=float('nan');self.save()
        with self.assertRaisesRegex(ValueError,'Invalid IMU'):self.inputs()
        self.samples[2]['gyro_flu_rad_s'][0]=0;self.record['complete']=False;self.save()
        with self.assertRaisesRegex(ValueError,'Incomplete'):self.inputs()
    def test_unsupported_mount_and_invalid_optics_rejected(self):
        self.cal['mount']['yaw_degrees']=90;self.save()
        with self.assertRaisesRegex(ValueError,'forward'):self.inputs()
        self.cal['mount']['yaw_degrees']=0;self.cal['optics']['fx']=float('nan');self.save()
        with self.assertRaisesRegex(ValueError,'Invalid measured'):self.inputs()

if __name__=='__main__':unittest.main()
