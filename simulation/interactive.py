"""Live keyboard teleoperation of the same contact model and controller.

W/S: drive; A/D: turn; arrows: both hands in world XY; Q/E: hands down/up;
G: toggle grip; C: toggle measured-base compensation; SPACE: pause.
Optional --packets JSONL replays pose packets through the actual controller.
"""
import argparse,time
from pathlib import Path
import numpy as np
import mujoco,mujoco.viewer
from scene import make_scene
from control import Controller,DT,rz
from run import reference
from teleop import load_packets
from build_model import HERE

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--packets');ap.add_argument('--seconds',type=float);ap.add_argument('--headless',action='store_true');args=ap.parse_args()
    m,d,info=make_scene('bimanual',0,0)
    b,p,r,g,_=reference(0,info);ctrl=Controller(m,d,coupled=True);ctrl.initialize(d,p,r)
    for i in range(m.nu): d.ctrl[i]=d.qpos[m.jnt_qposadr[m.actuator_trnid[i,0]]]
    fids=[m.actuator(f'{s}_finger_{i}').id for s in ['left','right'] for i in [-1,1]]
    state={'base':b,'target':p,'grip':.045,'rotation':r,'paused':False,'mode':'coupled'}
    packets=load_packets(args.packets) if args.packets else None
    def key(k):
        nonlocal ctrl
        if k==32:state['paused']=not state['paused']
        if k==87:state['base'][:2]+=.025*np.array([np.cos(b[2]),np.sin(b[2])])
        if k==83:state['base'][:2]-=.025*np.array([np.cos(b[2]),np.sin(b[2])])
        if k==65:state['base'][2]+=.04
        if k==68:state['base'][2]-=.04
        if k==262:state['target'][:,1]-=.012
        if k==263:state['target'][:,1]+=.012
        if k==265:state['target'][:,0]+=.012
        if k==264:state['target'][:,0]-=.012
        if k==81:state['target'][:,2]-=.012
        if k==69:state['target'][:,2]+=.012
        if k==71:state['grip']=0 if state['grip']>.02 else .045
        if k==67:
            modes=['independent','coordinated','coupled'];state['mode']=modes[(modes.index(state['mode'])+1)%3]
            ctrl=Controller(m,d,coupled=state['mode']=='coupled');print(state['mode'],flush=True)
    v=None;frames=[];packet_idx=0
    if not args.headless:
        v=mujoco.viewer.launch_passive(m,d,key_callback=key,show_left_ui=False,show_right_ui=False)
        v.cam.lookat[:]=[0,.4,.75];v.cam.distance=3;v.cam.azimuth=145;v.cam.elevation=-20
    limit=args.seconds or (packets[-1].timestamp if packets else float('inf'))
    print(__doc__,flush=True)
    try:
        while d.time<limit and (v is None or v.is_running()):
            start=time.perf_counter()
            if not state['paused']:
                if packets:
                    while packet_idx+1<len(packets) and packets[packet_idx+1].timestamp<=d.time:packet_idx+=1
                    pkt=packets[packet_idx];state['target']=np.array([pkt.left,pkt.right]);state['rotation']=pkt.rotation;state['grip']=pkt.aperture
                    if pkt.base is not None:state['base'][:]=pkt.base
                d.ctrl[:3]=state['base']
                ctrl.step(d,state['target'],state['rotation'],state['base'] if state['mode']=='independent' else None)
                d.ctrl[fids]=state['grip']
                for _ in range(5):mujoco.mj_step(m,d)
                frames.append(np.r_[d.time,d.qpos])
            if v:v.sync();time.sleep(max(0,DT-(time.perf_counter()-start)))
        out=HERE/'outputs/interactive_last.npz';np.savez_compressed(out,states=np.asarray(frames),source='keyboard_or_pose_packet',hardware_verified=False)
        print(f'FINISHED {len(frames)} control frames -> {out}',flush=True)
    finally:
        if v:v.close()

if __name__=='__main__':main()
