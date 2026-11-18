"""Saved-state inspection. SPACE pause, R restart; mouse orbit and zoom."""
from pathlib import Path
import argparse,json,time
import numpy as np,mujoco,mujoco.viewer

def replay(folder,seconds=None):
    root=Path(folder);info=json.loads((root/'summary.json').read_text(encoding='utf-8'))
    m=mujoco.MjModel.from_xml_path(str(root/'scene.xml'));d=mujoco.MjData(m)
    z=np.load(root/'trajectory.npz');q=z['qpos'];v=z['qvel'];rows=z['metrics'];state={'paused':False,'restart':False}
    def key(k):
        if k==32:state['paused']=not state['paused']
        if k in [82,114]:state['restart']=True
    with mujoco.viewer.launch_passive(m,d,key_callback=key,show_left_ui=False,show_right_ui=False) as viewer:
        viewer.cam.lookat[:]=[-.20,info['distance']/2,.72];viewer.cam.distance=4.25;viewer.cam.azimuth=180;viewer.cam.elevation=-26
        print(__doc__,flush=True);start=time.perf_counter();clock=0
        while viewer.is_running():
            tick=time.perf_counter()
            if seconds is not None and tick-start>seconds:break
            if state['restart']:clock=0;state['restart']=False
            i=min(int(clock/.01),len(q)-1)
            with viewer.lock():d.qpos[:]=q[i];d.qvel[:]=v[i];d.time=rows[i,0];mujoco.mj_forward(m,d)
            viewer.sync();time.sleep(max(0,1/30-(time.perf_counter()-tick)))
            if not state['paused']:clock=(clock+time.perf_counter()-tick)%(len(q)*.01+2)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder');p.add_argument('--seconds',type=float);replay(**vars(p.parse_args()))
