"""Live wheel/arm simulation: W/S drive, A/D turn (short pulses), arrows hand XY,
Q/E down/up, G close/open, SPACE pause. JSONL poses use the same input adapter.
"""
from pathlib import Path
import argparse,time,json
import numpy as np,mujoco,mujoco.viewer
from model import make_model,Servo,WHEEL_RADIUS,TRACK,HERE
from control import Controller,rz
from stable_control import StableController
from teleop import PosePacket
from experiment import base_pose

def main():
    p=argparse.ArgumentParser();p.add_argument('--headless',action='store_true');p.add_argument('--seconds',type=float);p.add_argument('--packets');p.add_argument('--out',default=str(HERE/'outputs/live_last'));a=p.parse_args()
    m,d,info,xml=make_model(True,0,True,.70);servo=Servo(m,d);ik=StableController(m,d,True)
    local=np.array([[info['x'],info['y']+.30,.838],[info['x'],info['y']-.30,.838]])
    ik.initialize(d,local,np.eye(3));servo.qtarget=d.qpos.copy();d.ctrl[servo.fingers]=.045
    for actuator in servo.fingers:d.qpos[m.jnt_qposadr[m.actuator_trnid[actuator,0]]]=.045
    for _ in range(500):servo.apply(d);mujoco.mj_step(m,d)
    d.time=0.;state={'paused':False,'grip':.045,'twist':np.zeros(2),'until':0.,'arm_edit_until':0.}
    packets=[]
    if a.packets:
        for line in Path(a.packets).read_text(encoding='utf-8').splitlines():
            raw=json.loads(line);packet=PosePacket.from_dict(raw);twist=np.asarray(raw.get('base_twist',[0,0]),float)
            if twist.shape!=(2,) or not np.all(np.isfinite(twist)):raise ValueError('invalid base_twist')
            if packets and packet.timestamp<=packets[-1][0].timestamp:raise ValueError('timestamps must increase')
            packets.append((packet,twist))
        if not packets:raise ValueError('empty input stream')
    def key(k):
        if k==32:state['paused']=not state['paused']
        if k==71:state['grip']=0 if state['grip']>.02 else .045
        twists={87:[.12,0],83:[-.12,0],65:[0,.3],68:[0,-.3]}
        if k in twists:state['twist']=np.array(twists[k]);state['until']=d.time+.35
        shift={265:[.01,0,0],264:[-.01,0,0],263:[0,.01,0],262:[0,-.01,0],81:[0,0,-.01],69:[0,0,.01]}
        if k in shift:local[:]+=shift[k];local[:,0]=np.clip(local[:,0],.22,.55);local[:,2]=np.clip(local[:,2],.58,.93);state['arm_edit_until']=d.time+.5
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True);(out/'scene.xml').write_text(xml,encoding='utf-8')
    viewer=None;frames=[];vel=[];idx=0;last=np.zeros(2);inputs=[]
    if not a.headless:
        viewer=mujoco.viewer.launch_passive(m,d,key_callback=key,show_left_ui=False,show_right_ui=False)
        viewer.cam.lookat[:]=[0,.4,.75];viewer.cam.distance=2.9;viewer.cam.azimuth=180;viewer.cam.elevation=-24
    limit=a.seconds if a.seconds is not None else (packets[-1][0].timestamp if packets else float('inf'))
    print(__doc__,flush=True)
    try:
        while d.time<limit and (viewer is None or viewer.is_running()):
            tick=time.perf_counter()
            if not state['paused']:
                pose=base_pose(d);rot=rz(pose[2]);target=(rot@local.T).T+np.r_[pose[:2],0];twist=state['twist'] if d.time<state['until'] else np.zeros(2);aperture=state['grip']
                if packets:
                    while idx+1<len(packets) and packets[idx+1][0].timestamp<=d.time:idx+=1
                    pkt,twist=packets[idx];target=np.array([pkt.left,pkt.right]);rot=pkt.rotation;aperture=pkt.aperture
                last+=np.clip(np.clip(twist,[-.23,-.55],[.23,.55])-last,[-.002,-.008],[.002,.008])
                d.ctrl[servo.wheels]=[(last[0]-last[1]*TRACK/2)/WHEEL_RADIUS,(last[0]+last[1]*TRACK/2)/WHEEL_RADIUS]
                ik.set_phase('navigate' if np.linalg.norm(last)>.01 and d.time>state['arm_edit_until'] else 'approach',d)
                solution=ik.step(d,target,rot);servo.qtarget[ik.qids]=solution[ik.qids];d.ctrl[servo.fingers]=aperture
                inputs.append(json.dumps({'timestamp':float(d.time),'frame':'world_meters','left':target[0].tolist(),'right':target[1].tolist(),'rotation':rot.tolist(),'aperture':float(aperture),'base_twist':last.tolist(),'source':'packet_replay' if packets else 'keyboard','hardware_verified':False}))
                for _ in range(5):servo.apply(d);mujoco.mj_step(m,d)
                frames.append(np.r_[d.time,d.qpos]);vel.append(d.qvel.copy())
            if viewer:viewer.sync();time.sleep(max(0,.01-(time.perf_counter()-tick)))
        np.savez_compressed(out/'states.npz',states=np.asarray(frames),qvel=np.asarray(vel))
        (out/'input.jsonl').write_text('\n'.join(inputs)+'\n',encoding='utf-8');print(f'FINISHED {len(frames)} frames: {out}',flush=True)
    finally:
        if viewer:viewer.close()

if __name__=='__main__':main()
