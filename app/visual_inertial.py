"""Sensor-only process interface to OpenVINS; no simulator geometry or true pose."""
import asyncio
import json
import math
from pathlib import Path
import shutil

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def displacement_std(joint):
    """Largest-axis uncertainty of p(now)-p(reference), with correlation."""
    p=np.asarray(joint,float)
    if p.shape!=(6,6) or not np.isfinite(p).all():raise ValueError('Invalid relative position covariance')
    covariance=p[:3,:3]+p[3:,3:]-p[:3,3:]-p[3:,:3]
    eigenvalues=np.linalg.eigvalsh((covariance+covariance.T)/2)
    if eigenvalues[0]<-1e-8:raise ValueError('Indefinite relative position covariance')
    return float(np.sqrt(max(0.,eigenvalues[-1])))


def tracking_faults(result,tilt_error,initialized):
    """Keep short-term tracking health distinct from accumulated map drift."""
    reasons=[]
    values=[*result['position_std_m'],*result['velocity'],tilt_error]
    if not np.isfinite(values).all():return ['non-finite estimator quality']
    if result['stable_image_tracks']<25:reasons.append('too few stable image tracks')
    if max(result['position_std_m'])>=.4:reasons.append('accumulated position uncertainty exceeds hard limit')
    if np.linalg.norm(result['velocity'])>=1:reasons.append('estimated velocity exceeds flight envelope')
    if tilt_error>=1:reasons.append('gravity disagreement exceeds one degree')
    if initialized:
        relative=result.get('relative_position_std_m')
        span=result.get('relative_position_span_s',0)
        if relative is None or not np.isfinite(relative) or not .25<=span<=2 or relative>=.05:
            reasons.append('recent displacement uncertainty unavailable or exceeds 0.05 m')
    elif max(result['position_std_m'])>=.15:reasons.append('initial position uncertainty exceeds 0.15 m')
    return reasons


def gravity_disagreement_degrees(a,b):
    """Compare gravity direction without constraining unobservable absolute yaw."""
    def gravity(q):
        x,y,z,w=np.asarray(q,dtype=float)/np.linalg.norm(q)
        return np.array([2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)])
    return math.degrees(math.acos(float(np.clip(gravity(a)@gravity(b),-1,1))))


def quaternion(rotation):
    axis = cv2.Rodrigues(np.asarray(rotation, np.float64))[0].reshape(3)
    angle = float(np.linalg.norm(axis))
    return ([*(axis/angle*math.sin(angle/2)), math.cos(angle/2)] if angle > 1e-9 else [0.,0.,0.,1.])


class VisualInertial:
    async def start(self, calibration, folder, launch_height, *, stationary_phase=None):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.height = float(launch_height)
        self.stationary_phase = stationary_phase
        self.last_imu = -1.
        self.last_camera = -1.
        self.sequence = 0
        self.alignment = None
        pitch = math.radians(calibration['mount']['pitch_degrees'])
        t = np.eye(4)
        t[:3,:3] = [[0,math.sin(pitch),math.cos(pitch)],[-1,0,0],[0,-math.cos(pitch),math.sin(pitch)]]
        t[:3,3] = calibration['mount']['body_offset_flu_m']
        optics = calibration['optics']
        if not optics:
            raise ValueError('VIO requires standard calibrated camera optics')
        self.k=np.array([[optics['fx'],0,optics['cx']],[0,optics['fy'],optics['cy']],[0,0,1.]])
        self.rectify=cv2.initUndistortRectifyMap(self.k,np.asarray(optics['distortion'],float),
                      None,self.k,(optics['width'],optics['height']),cv2.CV_32FC1)
        camera = '%YAML:1.0\ncam0:\n  T_imu_cam:\n'
        camera += ''.join('    - '+json.dumps(row)+'\n' for row in t.tolist())
        camera += ('  cam_overlaps: []\n  camera_model: pinhole\n  distortion_model: radtan\n'
                   '  distortion_coeffs: [0.0, 0.0, 0.0, 0.0]\n'
                   '  intrinsics: '+json.dumps([optics[k] for k in ('fx','fy','cx','cy')])+'\n'
                   '  resolution: '+json.dumps([optics['width'],optics['height']])+'\n'
                   '  rostopic: /camera\n')
        (self.folder/'camera.yaml').write_text(camera)
        for name in ('estimator.yaml','imu.yaml'):
            shutil.copyfile(ROOT/'config/openvins'/name, self.folder/name)
        self.log = (self.folder/'native.log').open('wb')
        self.process = await asyncio.create_subprocess_exec(str(ROOT/'.local/build/openvins/drone137_openvins'),
            str(self.folder/'estimator.yaml'), stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=self.log, limit=1024*1024)
        line = await asyncio.wait_for(self.process.stdout.readline(), 30)
        if not line: raise RuntimeError('VIO exited during startup; inspect native.log')
        ready = json.loads(line)
        if not ready.get('ready'):
            raise RuntimeError('VIO startup failed: '+str(ready))
        self.audit = (self.folder/'estimates.jsonl').open('w')

    async def observe(self, frame, jpeg, imu):
        timestamp = frame['capture_time_s']
        if timestamp <= self.last_camera:
            return None
        if imu['oldest_time_s'] > self.last_imu+.02 and self.last_imu >= 0:
            raise RuntimeError('IMU ring overrun; visual-inertial trajectory is discontinuous')
        self.sequence += 1
        path = self.folder/f'image-{self.sequence:06}.jpg'
        path.write_bytes(jpeg)
        # Track on the calibrated pinhole image, as the metric mapper does.
        # With a wide lens, distorted sensor-edge pixels can lie outside the
        # renderer's pinhole image and contain stretched border texels. Those
        # cannot be treated as valid feature bearings. Rectification retains
        # only the common pinhole view; original sensor JPEGs remain evidence.
        gray=cv2.imdecode(np.frombuffer(jpeg,np.uint8),cv2.IMREAD_GRAYSCALE)
        rectified=cv2.remap(gray,*self.rectify,cv2.INTER_LINEAR)
        input_path=self.folder/'rectified-current.png'
        cv2.imwrite(str(input_path),rectified)
        request = {'imu': imu['imu'], 'camera': {'time_s': timestamp, 'path': str(input_path.resolve())}}
        if self.stationary_phase is not None:
            request['stationary_phase'] = self.stationary_phase
        self.process.stdin.write((json.dumps(request)+'\n').encode())
        await self.process.stdin.drain()
        line = await asyncio.wait_for(self.process.stdout.readline(), 8)
        if not line:
            raise RuntimeError('Native visual-inertial process exited')
        result = json.loads(line)
        if 'error' in result:
            raise RuntimeError(result['error'])
        if 'relative_position_joint_covariance' in result:
            result['relative_position_std_m']=displacement_std(result['relative_position_joint_covariance'])
        self.last_imu = result['last_imu_time_s']
        self.last_camera = timestamp
        if result['initialized']:
            rotation=np.asarray(result['rotation_imu_to_global'])
            if self.alignment is None:
                yaw=math.atan2(rotation[1,0],rotation[0,0])
                self.alignment=np.array([[math.cos(yaw),math.sin(yaw),0],[-math.sin(yaw),math.cos(yaw),0],[0,0,1.]])
            result['rotation_imu_to_global']=(self.alignment@rotation).tolist()
            result['position']=(self.alignment@result['position']).tolist()
            result['velocity']=(self.alignment@result['velocity']).tolist()
            # OpenVINS initializes its origin at the IMU. The known aircraft
            # geometry locates that IMU above the launch floor; no room pose.
            result['position'][2] += self.height
            for landmark in result['landmarks']:
                landmark['point']=(self.alignment@landmark['point']).tolist()
                landmark['point'][2] += self.height
            result['quaternion'] = quaternion(result['rotation_imu_to_global'])
        self.audit.write(json.dumps({'capture_time_s': timestamp, 'image': path.name, **result})+'\n')
        self.audit.flush()
        return result

    async def close(self):
        if hasattr(self,'process') and self.process.returncode is None:
            self.process.stdin.close()
            try:
                await asyncio.wait_for(self.process.wait(), 5)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()
        if hasattr(self,'log'): self.log.close()
        if hasattr(self,'audit'): self.audit.close()
