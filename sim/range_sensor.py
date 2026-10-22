"""Synthetic scanning range sensor. Only this simulator adapter sees geometry.

Returns a conservative vertical column scan, as a depth camera/multilayer lidar
would need to supply for a finite-height vehicle. Not a single planar lidar.
"""
import math
import random


class RangeSensor:
    def __init__(self, scene, parameters):
        self.parameters=parameters;self.rng=random.Random(scene['seed']+8901)
        self.boxes=[(b['x']-b['sx']/2,b['y']-b['sy']/2,b['x']+b['sx']/2,b['y']+b['sy']/2)
                    for b in scene['obstacles']+scene.get('fixtures',[])]
        self.width,self.depth=scene['width'],scene['depth'];self.actor=scene['moving_actor']

    def scan(self, truth, now):
        x,y=truth['position'][:2];q=truth['quaternion'];yaw=math.atan2(2*(q[3]*q[2]+q[0]*q[1]),1-2*(q[1]**2+q[2]**2))
        actor=self.actor;cx,cy=(truth['cart_position'][:2] if truth.get('cart_position') else actor['center'])
        boxes=self.boxes+[(cx-actor['size'][0]/2,cy-actor['size'][1]/2,cx+actor['size'][0]/2,cy+actor['size'][1]/2)]
        result=[];limit=self.parameters['range_m']
        for i in range(180):
            relative=i*2*math.pi/180;angle=yaw+relative;dx,dy=math.cos(angle),math.sin(angle)
            wall=min((self.width-x)/dx if dx>1e-10 else -x/dx if dx< -1e-10 else math.inf,
                     (self.depth-y)/dy if dy>1e-10 else -y/dy if dy< -1e-10 else math.inf)
            distance=min(limit,wall)
            for x0,y0,x1,y1 in boxes:
                near,far=0.,distance
                for origin,direction,lo,hi in ((x,dx,x0,x1),(y,dy,y0,y1)):
                    if abs(direction)<1e-10:
                        if not lo<=origin<=hi:far=-1;break
                    else:
                        a,b=(lo-origin)/direction,(hi-origin)/direction;near=max(near,min(a,b));far=min(far,max(a,b))
                if near<=far and near>=0:distance=min(distance,near)
            hit=distance<limit
            distance=max(.01,min(limit,distance+self.rng.gauss(0,self.parameters['range_noise_m'])))
            result.append({'angle_body':relative,'distance':distance,'hit':hit,'valid':self.rng.random()>=self.parameters['range_dropout'],
                           'time':now,'max_range':limit})
        return result
