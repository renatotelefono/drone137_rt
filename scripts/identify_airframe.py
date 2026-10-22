"""Offline motor identification and matched trajectory agreement, never auto-tuning flight."""
import argparse
import hashlib
import json
from pathlib import Path


def motor_fit(samples):
    import numpy as np
    t=np.asarray([s['time_s'] for s in samples],float);rpm=np.asarray([s['rotor_rad_s'] for s in samples],float)
    command=np.asarray([s['command_rad_s'] for s in samples],float);thrust=np.asarray([s['thrust_n'] for s in samples],float)
    if len(t)<20 or not all(np.all(np.isfinite(a)) for a in (t,rpm,command,thrust)) or np.any(np.diff(t)<=0) or np.any(rpm<0) or np.any(thrust<0):raise ValueError('Invalid ordered motor bench samples')
    x=rpm**2
    if np.ptp(rpm)<100 or np.dot(x,x)==0:raise ValueError('Insufficient motor excitation')
    k=float(np.dot(x,thrust)/np.dot(x,x));dt=np.diff(t);results={}
    for name,mask in [('up',command[:-1]>rpm[:-1]+10),('down',command[:-1]<rpm[:-1]-10)]:
        if mask.sum()<5:raise ValueError('Need both spin-up and spin-down excitation')
        candidates=np.geomspace(.002,.5,1000)
        errors=[np.mean((command[:-1][mask]+(rpm[:-1][mask]-command[:-1][mask])*np.exp(-dt[mask]/tau)-rpm[1:][mask])**2) for tau in candidates]
        i=int(np.argmin(errors));results['motor_time_'+name+'_s']=float(candidates[i]);results[name+'_fit_rmse_rad_s']=float(np.sqrt(errors[i]))
    return {'motor_constant':k,'thrust_fit_rmse_n':float(np.sqrt(np.mean((x*k-thrust)**2))),**results}


def trajectory_agreement(reference,simulation):
    import numpy as np
    def arrays(rows):
        t=np.asarray([s['time_s'] for s in rows],float);p=np.asarray([s['position_m'] for s in rows],float)
        if len(t)<3 or p.shape!=(len(t),3) or not np.isfinite(t).all() or not np.isfinite(p).all() or np.any(np.diff(t)<=0):raise ValueError('Invalid trajectory')
        return t,p
    tr,pr=arrays(reference);ts,ps=arrays(simulation)
    mask=(tr>=ts[0])&(tr<=ts[-1])
    if mask.sum()<3 or tr[mask][-1]-tr[mask][0]<1:raise ValueError('Insufficient time overlap')
    predicted=np.column_stack([np.interp(tr[mask],ts,ps[:,i]) for i in range(3)])
    err=np.linalg.norm(predicted-pr[mask],axis=1)
    return {'samples':len(err),'overlap_s':float(tr[mask][-1]-tr[mask][0]),'position_rmse_m':float(np.sqrt(np.mean(err**2))),
            'position_p95_m':float(np.quantile(err,.95)),'position_max_m':float(err.max()),
            'alignment':'Caller supplies the same measured coordinate frame and synchronized time; no best-fit pose/time alignment'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['motor','trajectory']);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():raise ValueError('Output must be new')
    data=json.loads(a.input.read_text());result=motor_fit(data['samples']) if a.mode=='motor' else trajectory_agreement(data['reference'],data['simulation'])
    result.update(source_kind=data['source_kind'],input_sha256=hashlib.sha256(a.input.read_bytes()).hexdigest(),qualification='Fit/diagnostic only. Validate on separate recordings before assigning measured parameters to a hardware revision.')
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
