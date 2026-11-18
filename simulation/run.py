"""Contact-based pick, transport and place; logs all simulation states.

No welds, mocap objects, or per-step object-pose writes. Synthetic hand goals
stand in for a replayable teleoperation stream. Base motion is a prescribed
nonholonomic route executed with ideal planar position servos.
"""
import argparse,json,time
from pathlib import Path
import numpy as np
import mujoco
from PIL import Image,ImageDraw,ImageFont
import imageio.v2 as imageio
from scene import make_scene
from control import Controller,DT,rz,interp,smooth
from build_model import HERE
from evaluation import evaluate

DURATION=43.
def reference(t,info):
    x,y,z=info['x'],info['y'],info['grasp_z']; dist=info['distance']
    base=np.zeros(3)
    if t<11: phase='Approach / grasp / lift'
    elif t<15: base[0]=interp(0,-.38,t,11,15); phase='Back away'
    elif t<19: base[:]=[-.38,0,interp(0,np.pi/2,t,15,19)]; phase='Turn into aisle'
    elif t<27: base[:]=[-.38,interp(0,dist,t,19,27),np.pi/2];phase='Transport'
    elif t<31: base[:]=[-.38,dist,interp(np.pi/2,0,t,27,31)];phase='Turn to destination'
    elif t<35: base[:]=[interp(-.38,0,t,31,35),dist,0];phase='Dock'
    else: base[:]=[0,dist,0];phase='Place / release'
    yy=[y+.30,y-.30] if info['task']=='bimanual' else [y,-.30]
    zz=interp(z+.09,z,t,1,4) if t<5.5 else interp(z,z+.12,t,5.5,9)
    if t>=35: zz=interp(z+.12,z+.002,t,35,38)
    if t>=40: zz=interp(z+.002,z+.15,t,40,42.5)
    pos=np.array([[x,yy[0],zz],[x,yy[1],zz]])
    if info['task']!='bimanual': pos[1]=[.23,-.32,.84]
    rot=rz(base[2]); pos=(rot@pos.T).T+np.r_[base[:2],0]
    # At pickup and placement the work surface is a world-fixed reference.
    # During transit the goal moves along the nominal route.
    aperture=.045 if t<4 else float(interp(.045,0,t,4,5.5))
    if t>=38.5: aperture=float(interp(0,.045,t,38.5,40))
    return base,pos,rot,aperture,phase

def overlay(frame,info,mode,t,phase,err,height,contacts):
    im=Image.fromarray(frame); draw=ImageDraw.Draw(im)
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',23)
    small=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',17)
    draw.rectangle((0,0,1280,82),fill=(14,23,34))
    title='灵驭  |  双臂托盘搬运' if info['task']=='bimanual' else '灵驭  |  单臂取物搬运'
    draw.text((24,12),title,font=font,fill='white')
    draw.text((24,48),'MuJoCo 接触动力学  ·  合成遥操作目标回放  ·  简化夹爪与底盘',font=small,fill=(161,182,202))
    label={'coordinated':'协调补偿','coupled':'双臂耦合补偿','independent':'独立控制基线'}[mode]
    draw.text((1000,18),label,font=font,fill=(78,220,175) if mode!='independent' else (255,184,100))
    draw.rectangle((0,652,1280,720),fill=(14,23,34))
    phase_cn={'Approach / grasp / lift':'接近 · 夹持 · 抬升','Back away':'后退离开工作台','Turn into aisle':'转向运输通道','Transport':'双臂保持与移动搬运','Turn to destination':'转向目标工作台','Dock':'靠近目标工作台','Place / release':'放置 · 松手 · 稳定检查'}[phase]
    draw.text((24,663),f'{t:05.1f} s  ·  {phase_cn}',font=small,fill='white')
    draw.text((24,690),f'末端误差 {err*1000:5.1f} mm    物体高度 {height:.3f} m    夹爪接触数 {contacts}',font=small,fill=(166,193,211))
    return np.asarray(im)

def run(task='bimanual',mode='coordinated',seed=0,disturbance=.018,video=False,out=None,save_trace=True):
    start=time.perf_counter(); m,d,info=make_scene(task,seed,disturbance)
    out=Path(out or HERE/'outputs'/f'{task}_{mode}_{seed:03d}'); out.mkdir(parents=True,exist_ok=True)
    ctrl=Controller(m,d,coupled=(mode=='coupled' and task=='bimanual')); b,p,r,ap,phase=reference(0,info)
    ctrl.initialize(d,p,r)
    robot_nq=27
    for i in range(m.nu):
        jid=m.actuator_trnid[i,0]; d.ctrl[i]=d.qpos[m.jnt_qposadr[jid]]
    fingers=[m.actuator(f'{s}_finger_{v}').id for s in ['left','right'] for v in [-1,1]]
    d.ctrl[fingers]=.045
    for i in fingers: d.qpos[m.jnt_qposadr[m.actuator_trnid[i,0]]]=.045
    # Settle contacts at the source table, before the experiment clock.
    for _ in range(250): mujoco.mj_step(m,d)
    d.time=0
    renderer=writer=cam=None
    if video:
        renderer=mujoco.Renderer(m,720,1280)
        cam=mujoco.MjvCamera(); cam.lookat[:]=[-.02,info['distance']/2,.63];cam.distance=3.65;cam.azimuth=145;cam.elevation=-23
        writer=imageio.get_writer(out/'demo.mp4',fps=25,codec='libx264',quality=8,macro_block_size=None)
    rows=[]; states=[]; qs=[]; velocities=[]; inputs=[]; controls=[]; contacts_log=[]; solves=[]
    cargo_id=m.body('cargo').id
    cgids=[i for i in range(m.ngeom) if m.geom_bodyid[i]==cargo_id]
    padids=[m.geom(f'{s}_finger_{v}_pad').id for s in ['left','right'] for v in [-1,1]]
    snap_times={0,4,8,17,24,33,38,42}
    try:
        for k in range(round(DURATION/DT)):
            t=k*DT; b,p,r,ap,phase=reference(t,info)
            # Base servo disturbance mimics localization/drive error; paired
            # experiments use exactly the same deterministic perturbation.
            ramp=smooth(t/2)
            perturb=np.array([disturbance*np.sin(2*np.pi*.65*t+.3*seed),
                              disturbance*.65*np.sin(2*np.pi*.47*t+.7*seed),
                              disturbance*.9*np.sin(2*np.pi*.39*t)])*ramp
            d.ctrl[:3]=b+perturb
            tick=time.perf_counter()
            ctrl.step(d,p,r,nominal_base=b if mode=='independent' else None)
            solves.append(time.perf_counter()-tick)
            d.ctrl[fingers]=ap
            if task!='bimanual': d.ctrl[fingers[2:]]=.045
            for _ in range(5): mujoco.mj_step(m,d)
            actual=np.array([d.site(s+'_ee').xpos.copy() for s in ['left','right']])
            err=float(np.sqrt(np.mean(np.sum((actual-p)**2,axis=1))))
            cargo=d.xpos[cargo_id].copy(); tilt=float(np.arccos(np.clip(d.xmat[cargo_id].reshape(3,3)[2,2],-1,1)))
            cnt=0; normals=[]
            for con_i in range(d.ncon):
                con=d.contact[con_i]
                if (con.geom1 in padids and con.geom2 in cgids) or (con.geom2 in padids and con.geom1 in cgids):
                    cnt+=1; f=np.zeros(6);mujoco.mj_contactForce(m,d,con_i,f);normals.append(float(f[0]))
            rows.append([t,err,cargo[0],cargo[1],cargo[2],tilt,cnt,float(sum(normals)),*b,*d.qpos[:3]])
            qs.append(d.qpos.copy()); velocities.append(d.qvel.copy()); inputs.append(np.r_[p.ravel(),b,ap]);states.append(actual.ravel());controls.append(d.ctrl.copy())
            contacts_log.append(cnt)
            if video and k%4==0:
                renderer.update_scene(d,camera=cam)
                frame=overlay(renderer.render(),info,mode,t,phase,err,cargo[2],cnt)
                writer.append_data(frame)
                sec=round(t)
                if sec in snap_times and abs(t-sec)<.02:
                    Image.fromarray(frame).save(out/f'frame_{sec:02d}.png');snap_times.remove(sec)
        arr=np.array(rows)
        goal=np.array([info['x'],info['y']+info['distance']])
        error=float(np.linalg.norm(d.xpos[cargo_id,:2]-goal))
        expected_z=.740 if task=='bimanual' else .750
        lift=float(np.max(arr[:,4])-expected_z)
        on_table=abs(d.xpos[cargo_id,2]-expected_z)<.035
        released=int(arr[-1,6])==0
        stable=np.linalg.norm(d.qvel[m.jnt_dofadr[m.joint('cargo_free').id]:][:6])<.10
        parcel_ok=True
        if task=='bimanual':
            delta=d.body('parcel').xpos-d.body('cargo').xpos
            parcel_ok=bool(abs(delta[0])<.09 and abs(delta[1])<.34 and .03<delta[2]<.12)
        success=bool(lift>.07 and error<.05 and on_table and released and stable and parcel_ok)
        transit=(arr[:,0]>=9)&(arr[:,0]<35)
        after_release=arr[:,0]>=40
        joint_penetrations=[]
        qmatrix=np.asarray(qs)
        for ji in range(m.njnt):
            if m.jnt_limited[ji] and 'finger' not in m.joint(ji).name:
                val=qmatrix[:,m.jnt_qposadr[ji]];lo,hi=m.jnt_range[ji]
                joint_penetrations.append(max(float(np.max(lo-val)),float(np.max(val-hi)),0.))
        summary={**info,'mode':mode,'success':success,'placement_error_m':error,'lift_m':lift,'final_z':float(d.xpos[cargo_id,2]),
                 'released':released,'stable':bool(stable),'parcel_retained':parcel_ok,'ee_rmse_m':float(np.sqrt(np.mean(arr[:,1]**2))),
                 'ee_p95_m':float(np.quantile(arr[:,1],.95)),'max_tilt_deg':float(np.rad2deg(arr[:,5].max())),
                 'mean_solve_ms':1000*float(np.mean(solves)),'p95_solve_ms':1000*float(np.quantile(solves,.95)),
                 'contact_frames':int(np.count_nonzero(arr[:,6])),'duration_s':DURATION,'wall_seconds':time.perf_counter()-start,
                 'transport_max_tilt_deg':float(np.rad2deg(arr[transit,5].max())),
                 'max_joint_limit_penetration_rad':max(joint_penetrations),
                 'placement_settled_time_s':float(arr[np.flatnonzero(after_release & (np.linalg.norm(arr[:,2:4]-goal,axis=1)<.05) & (np.abs(arr[:,4]-expected_z)<.035))[0],0]) if success else None,
                 'trajectory_source':'synthetic_reference','grasp_model':'frictional_contact_no_weld','engine':mujoco.__version__}
        summary.update(evaluate(m,info,qs,velocities,arr))
        (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
        np.savetxt(out/'metrics.csv',arr,delimiter=',',header='time,ee_rmse,cargo_x,cargo_y,cargo_z,tilt_rad,contacts,normal_force,nominal_x,nominal_y,nominal_yaw,actual_x,actual_y,actual_yaw',comments='')
        if save_trace:
            np.savez_compressed(out/'trajectory.npz',qpos=qmatrix,qvel=np.array(velocities),ctrl=np.array(controls),hand_targets=np.array(inputs),hand_actual=np.array(states),time=arr[:,0],ctrl_dt=DT,metadata=json.dumps(info))
        print(json.dumps(summary,ensure_ascii=False),flush=True)
        return summary
    finally:
        if writer: writer.close()
        if renderer: renderer.close()

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--task',choices=['single','bimanual'],default='bimanual');a.add_argument('--mode',choices=['coordinated','independent','coupled'],default='coordinated');a.add_argument('--seed',type=int,default=0);a.add_argument('--disturbance',type=float,default=.018);a.add_argument('--video',action='store_true');a.add_argument('--out');args=a.parse_args();run(**vars(args))
