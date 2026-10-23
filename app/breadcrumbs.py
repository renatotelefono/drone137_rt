"""A return route made solely from this flight's estimated, traversed poses."""
import math
import numpy as np


class Breadcrumbs:
    def __init__(self):self.points=[]

    def observe(self,position,yaw):
        if not 1.4<position[2]<1.6:return
        point=[*position,float(yaw)]
        if self.points and math.dist(position,self.points[-1][:3])<.05:return
        # Remove already-traversed loops, without creating an unobserved long
        # shortcut. A match is within the recorded trajectory's 0.04 m tube.
        for i in range(len(self.points)-3,-1,-1):
            if math.dist(position,self.points[i][:3])<.04:
                self.points=self.points[:i+1];break
        self.points.append(point)

    def route(self,position,yaw):
        path=[[*position,float(yaw)],*reversed(self.points)]
        result=[path[0]];index=0
        while index<len(path)-1:
            furthest=index+1
            for end in range(index+2,len(path)):
                a=np.array(path[index][:3]);b=np.array(path[end][:3]);delta=b-a
                if np.linalg.norm(delta)>1.5:break
                middle=np.array([p[:3] for p in path[index+1:end]])
                f=np.clip((middle-a)@delta/max(1e-8,delta@delta),0,1)
                if np.any(np.linalg.norm(middle-(a+f[:,None]*delta),axis=1)>.05):break
                furthest=end
            if math.dist(path[furthest][:3],result[-1][:3])>.08:result.append(path[furthest])
            index=furthest
        return result
