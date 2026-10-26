"""Tag column of dock A: detection, pose in the dock frame, and a renderer for synthetic frames.

Dock frame: forward (toward the tag stand), left, up; origin at the pocket centre on the
pocket floor. The hardware drawings call the same axes +Y, -X, +Z. Aircraft body frame:
forward-left-up at the aircraft reference point on the feet plane. Camera frame: OpenCV,
x right, y down, z along the optical axis.
"""
import json
import math
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT/'config/dock-a.json'


def load_geometry(path=CONFIG):
    return json.loads(Path(path).read_text())


def rot_z(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0.], [s, c, 0.], [0., 0., 1.]])


def rot_y(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0., s], [0., 1., 0.], [-s, 0., c]])


def rot_x(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1., 0., 0.], [0., c, -s], [0., s, c]])


def mount_rotation(pitch_deg):
    """Columns are the camera axes (right, down, optical) expressed in the FLU body frame."""
    t = math.radians(pitch_deg)
    return np.array([[0., math.sin(t), math.cos(t)], [-1., 0., 0.], [0., -math.cos(t), math.sin(t)]])


def body_rotation(yaw, pitch=0., roll=0.):
    return rot_z(yaw) @ rot_y(pitch) @ rot_x(roll)


def tag_ids(dock_index):
    return [3*dock_index, 3*dock_index+1, 3*dock_index+2]


def tag_corners(geometry, dock_index=0):
    """{tag id: 4x3 corners in the dock frame} in ArUco order: top-left, top-right, bottom-right, bottom-left."""
    f = geometry['tag_plane_f_m']; out = {}
    for tag_id, t in zip(tag_ids(dock_index), geometry['tags']):
        s, z = t['size_m']/2, t['height_m']
        out[tag_id] = np.array([[f, s, z+s], [f, -s, z+s], [f, -s, z-s], [f, s, z-s]])
    return out


def extrinsics(position_d, rotation_db, mount):
    """Dock-to-camera rotation and translation for a body pose in the dock frame."""
    R_bc = mount_rotation(mount['camera_pitch_deg']); o = np.asarray(mount['camera_offset_flu_m'], float)
    R_dc = rotation_db @ R_bc
    R_cd = R_dc.T
    t = -R_cd @ (rotation_db @ o + np.asarray(position_d, float))
    return R_cd, t


def body_pose(R_cd, t, mount):
    """Body position, yaw, pitch, roll in the dock frame from a dock-to-camera transform."""
    R_bc = mount_rotation(mount['camera_pitch_deg']); o = np.asarray(mount['camera_offset_flu_m'], float)
    R_dc = R_cd.T; p_c = -R_dc @ t
    R_db = R_dc @ R_bc.T
    p_b = p_c - R_db @ o
    yaw = math.atan2(R_db[1, 0], R_db[0, 0])
    pitch = math.atan2(-R_db[2, 0], math.hypot(R_db[2, 1], R_db[2, 2]))
    roll = math.atan2(R_db[2, 1], R_db[2, 2])
    return {'position_m': p_b.tolist(), 'yaw_rad': yaw, 'pitch_rad': pitch, 'roll_rad': roll, 'camera_m': p_c.tolist()}


def intrinsics(optics):
    K = np.array([[optics['fx'], 0., optics['cx']], [0., optics['fy'], optics['cy']], [0., 0., 1.]])
    return K, np.asarray(optics.get('distortion', [0, 0, 0, 0, 0]), float)


def optics_from_scene_camera(camera):
    """Nominal pinhole parameters from a simulated scene camera (vertical field of view and radial distortion)."""
    w, h = camera['width'], camera['height']
    f = h/(2*math.tan(math.radians(camera['vertical_fov']/2)))
    k1 = camera.get('effects', {}).get('distortion', 0.)
    return {'width': w, 'height': h, 'fx': f, 'fy': f, 'cx': w/2, 'cy': h/2, 'distortion': [k1, 0., 0., 0., 0.]}


class TagDetector:
    def __init__(self, geometry, dock_index, optics, max_reprojection_px=2.):
        self.geometry, self.dock_index, self.optics = geometry, dock_index, optics
        self.corners = tag_corners(geometry, dock_index)
        self.sizes = {i: t['size_m'] for i, t in zip(tag_ids(dock_index), geometry['tags'])}
        self.K, self.dist = intrinsics(optics)
        self.max_reprojection_px = max_reprojection_px
        self.dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
        params = cv2.aruco.DetectorParameters()
        params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        params.minMarkerPerimeterRate = .01
        self.detector = cv2.aruco.ArucoDetector(self.dictionary, params)

    def detect(self, image):
        """Detections of this dock's tags: {id: 4x2 image corners}. Other ids are ignored."""
        gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = self.detector.detectMarkers(gray)
        found = {}
        if ids is not None:
            for c, i in zip(corners, ids.reshape(-1)):
                if int(i) in self.corners and int(i) not in found:
                    found[int(i)] = c.reshape(4, 2).astype(float)
        return found

    def solve(self, detections):
        """Dock-to-camera transform from the detected corners, or None when the solution is unusable."""
        if not detections:
            return None
        ids = sorted(detections)
        if len(ids) == 1:
            i = ids[0]; s = self.sizes[i]/2
            square = np.array([[-s, s, 0.], [s, s, 0.], [s, -s, 0.], [-s, -s, 0.]])
            ok, rvec, tvec = cv2.solvePnP(square, detections[i], self.K, self.dist, flags=cv2.SOLVEPNP_IPPE_SQUARE)
            if not ok:
                return None
            R_ct = cv2.Rodrigues(rvec)[0]; t_ct = tvec.reshape(3)
            centre = self.corners[i].mean(0)
            R_dt = np.array([[0., 0., -1.], [-1., 0., 0.], [0., 1., 0.]])   # tag right = -left, tag up = up, tag out = -forward
            R_cd = R_ct @ R_dt.T; t = t_ct - R_cd @ centre
        else:
            obj = np.concatenate([self.corners[i] for i in ids]); img = np.concatenate([detections[i] for i in ids])
            ok, rvec, tvec = cv2.solvePnP(obj, img, self.K, self.dist, flags=cv2.SOLVEPNP_IPPE)
            if not ok:
                return None
            rvec, tvec = cv2.solvePnPRefineLM(obj, img, self.K, self.dist, rvec, tvec)
            R_cd = cv2.Rodrigues(rvec)[0]; t = tvec.reshape(3)
        obj = np.concatenate([self.corners[i] for i in ids]); img = np.concatenate([detections[i] for i in ids])
        projected = cv2.projectPoints(obj, cv2.Rodrigues(R_cd)[0], t, self.K, self.dist)[0].reshape(-1, 2)
        error = float(np.linalg.norm(projected-img, axis=1).mean())
        if not np.isfinite(error) or error > self.max_reprojection_px or (R_cd @ obj[0] + t)[2] <= 0:
            return None
        width = min(float(np.linalg.norm(detections[i][0]-detections[i][1])) for i in ids)
        return {'R_cd': R_cd, 't': t, 'reprojection_px': error, 'tags': ids, 'min_tag_px': width}

    def measure(self, image, mount):
        detections = self.detect(image)
        solution = self.solve(detections)
        if solution is None:
            return {'detected': sorted(detections), 'pose': None}
        pose = body_pose(solution['R_cd'], solution['t'], mount)
        return {'detected': solution['tags'], 'pose': pose, 'reprojection_px': solution['reprojection_px'], 'min_tag_px': solution['min_tag_px']}


class TagRenderer:
    """Draws the stand, the pocket and the tag column into a frame for a camera pose in the dock frame."""
    def __init__(self, geometry, dock_index, optics, effects=None, seed=0):
        self.geometry, self.optics = geometry, optics
        self.effects = {'blur': .6, 'noise': .018, 'exposure': .38, 'vignette': .28, **(effects or {})}
        self.K, self.dist = intrinsics(optics)
        self.corners = tag_corners(geometry, dock_index)
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
        self.markers = {}
        for i in self.corners:
            marker = cv2.aruco.generateImageMarker(dictionary, i, 160)   # 8 cells of 20 px including the black border
            canvas = np.full((200, 200), 255, np.uint8); canvas[20:180, 20:180] = marker
            self.markers[i] = canvas
        self.rng = np.random.default_rng(seed)
        w, h = optics['width'], optics['height']
        grid = np.stack(np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32)), -1).reshape(-1, 1, 2)
        undistorted = cv2.undistortPoints(grid, self.K, self.dist, P=self.K).reshape(h, w, 2)
        self.map_x, self.map_y = undistorted[..., 0].astype(np.float32), undistorted[..., 1].astype(np.float32)

    def project(self, points, R_cd, t):
        cam = (R_cd @ np.asarray(points, float).T).T + t
        if (cam[:, 2] <= .02).any():
            return None
        return cv2.projectPoints(np.asarray(points, float), cv2.Rodrigues(R_cd)[0], t, self.K, None)[0].reshape(-1, 2)

    def render(self, R_cd, t, jpeg_quality=None):
        g = self.geometry; w, h = self.optics['width'], self.optics['height']
        canvas = np.empty((h, w, 3), np.uint8)
        canvas[:] = (58, 60, 62)
        canvas[h//2:] = (74, 76, 78)
        ph = g['pocket_half_m']
        pocket = self.project([[-ph, ph, 0], [ph, ph, 0], [ph, -ph, 0], [-ph, -ph, 0]], R_cd, t)
        if pocket is not None:
            cv2.fillConvexPoly(canvas, np.round(pocket).astype(np.int32), (96, 98, 100))
        f0, lh, sh = g['stand']['f_m'][0], g['stand']['l_half_m'], g['stand']['height_m']
        plate = self.project([[f0, lh, 0], [f0, -lh, 0], [f0, -lh, sh], [f0, lh, sh]], R_cd, t)
        camera_f = (-R_cd.T @ t)[0]
        if plate is not None and camera_f < f0:
            cv2.fillConvexPoly(canvas, np.round(plate).astype(np.int32), (214, 214, 212))
            for i, corners in self.corners.items():
                s = self.geometry['tags'][i % 3]['size_m']; q = s/8
                quiet = corners + np.array([[0, q, q], [0, -q, q], [0, -q, -q], [0, q, -q]])
                target = self.project(quiet, R_cd, t)
                if target is None:
                    continue
                source = np.array([[0, 0], [200, 0], [200, 200], [0, 200]], np.float32)
                H = cv2.getPerspectiveTransform(source, target.astype(np.float32))
                marker = cv2.cvtColor(self.markers[i], cv2.COLOR_GRAY2BGR)
                warped = cv2.warpPerspective(marker, H, (w, h), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0))
                mask = cv2.warpPerspective(np.full((200, 200), 255, np.uint8), H, (w, h), flags=cv2.INTER_NEAREST)
                canvas[mask > 0] = warped[mask > 0]
        image = cv2.remap(canvas, self.map_x, self.map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        e = self.effects
        if e['blur'] > 0:
            image = cv2.GaussianBlur(image, (0, 0), e['blur'])
        if e['vignette'] > 0:
            yy, xx = np.mgrid[0:h, 0:w]; r = np.hypot((xx-w/2)/(w/2), (yy-h/2)/(h/2))
            image = (image*(1-e['vignette']*np.clip(r, 0, 1)**2)[..., None]).astype(np.uint8)
        if e['noise'] > 0:
            image = np.clip(image.astype(np.float32)+self.rng.normal(0, e['noise']*255, image.shape), 0, 255).astype(np.uint8)
        if jpeg_quality is not None:
            ok, data = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, int(round(jpeg_quality*100))])
            return data.tobytes()
        return image
