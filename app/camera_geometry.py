"""Brown-Conrady intrinsics shared by calibration files and localization."""
import math


def distort(x,y,coefficients):
    k1,k2,p1,p2,k3=coefficients;r2=x*x+y*y
    radial=1+k1*r2+k2*r2*r2+k3*r2*r2*r2
    return x*radial+2*p1*x*y+p2*(r2+2*x*x),y*radial+p1*(r2+2*y*y)+2*p2*x*y


def undistort(u,v,camera):
    xd,yd=(u-camera['cx'])/camera['fx'],(v-camera['cy'])/camera['fy'];x,y=xd,yd
    for _ in range(15):
        dx,dy=distort(x,y,camera['distortion']);x+=xd-dx;y+=yd-dy
    if not all(math.isfinite(t) for t in (x,y)) or math.hypot(*(a-b for a,b in zip(distort(x,y,camera['distortion']),(xd,yd))))>1e-6:
        raise ValueError('Pixel outside invertible lens calibration')
    return x,y
