"""Predeclared synthetic generalization cases; not independent physical sites."""
import copy
from sim.hard_flight import cases as earlier


def cases():
    result=[]
    for i,old in enumerate(earlier()):
        c=copy.deepcopy(old);c['id']=old['id'].replace('hard-','realism-');c['seed']+=310007
        c['stress']['furniture_xy']['bottle-table']=[2.65,2.5]
        c['stress']['furniture_xy']['stock-rack'][1]-=.25
        c['extra_obstacles']=[dict(id='unseen-pallet',x=7.2,y=6.8,sx=.75,sy=.65,height=.5,bottom=0.,kind='carton',detail=True,color='#7f785d')]
        # Fault injection times are relative to confirmed takeoff, fixed for both
        # members of each pair. They are retained even if no inference sees them.
        if i//2==2:c['sensor_faults']=[{'sensor':'range','start_s':10.,'duration_s':.8}]
        if i//2==3:c['sensor_faults']=[{'sensor':'odometry','start_s':12.,'duration_s':.6}]
        result.append(c)
    return result
