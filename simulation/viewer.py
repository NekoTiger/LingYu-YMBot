"""Inspect a saved physics rollout, with pause and restart controls."""
import argparse,json,time
from pathlib import Path
import numpy as np
import mujoco
import mujoco.viewer
from scene import make_scene
from build_model import HERE

def replay(path,speed=1.,seconds=None):
    p=Path(path)
    with np.load(p/'trajectory.npz') as archive:
        data={k:archive[k] for k in ['qpos','qvel','time','metadata']}
    info=json.loads(str(data['metadata']))
    m,d,_=make_scene(info['task'],info['seed'],info['disturbance'])
    state={'paused':False,'restart':False}
    def key(k):
        if k==32:state['paused']=not state['paused']
        if k in [82,114]:state['restart']=True
    with mujoco.viewer.launch_passive(m,d,key_callback=key,show_left_ui=False,show_right_ui=False) as v:
        v.cam.lookat[:]=[0,info['distance']/2,.8];v.cam.distance=3.9;v.cam.azimuth=145;v.cam.elevation=-23
        i=0.;start=time.perf_counter()
        print('Replay: SPACE pause, R restart, mouse orbit/zoom. ESC closes. Saved dynamics, not new simulation.',flush=True)
        while v.is_running():
            tick=time.perf_counter()
            if seconds is not None and tick-start>seconds:break
            if state['restart']:i=0.;state['restart']=False
            idx=min(int(i),len(data['time'])-1)
            with v.lock():
                d.qpos[:]=data['qpos'][idx];d.qvel[:]=data['qvel'][idx];d.time=float(data['time'][idx])
                mujoco.mj_forward(m,d)
            v.sync()
            if not state['paused']:i=(i+speed*3.333333)%len(data['time'])
            time.sleep(max(0,1/30-(time.perf_counter()-tick)))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('path',nargs='?',default=str(HERE/'outputs/bimanual_demo'));p.add_argument('--speed',type=float,default=1.);p.add_argument('--seconds',type=float);a=p.parse_args();replay(**vars(a))
