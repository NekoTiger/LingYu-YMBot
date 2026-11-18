"""Contact-driven, guarded pick/carry/place with wheel-level control."""
from pathlib import Path
import sys,time,json,argparse
import numpy as np
import mujoco
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'v2'))
from control import Controller,rz
from world import make_model,Servo,HERE,WHEEL_RADIUS,TRACK,cart_update,collision_gate
from input_channel import InputChannel

DT=.01
def wrap(x):return (x+np.pi)%(2*np.pi)-np.pi
def base_pose(d):
    r=d.body('base_footprint_link').xmat.reshape(3,3)
    return np.r_[d.body('base_footprint_link').xpos[:2],np.arctan2(r[1,0],r[0,0])]

def contacts(m,d):
    normals=np.zeros(2);counts=np.zeros(2,dtype=int);forbidden=[]
    for i in range(d.ncon):
        c=d.contact[i];names=[m.geom(c.geom1).name,m.geom(c.geom2).name]
        if any(n.startswith('cargo_') for n in names):
            for j,side in enumerate(['left','right']):
                if any(n.startswith(side+'_finger') for n in names):
                    force=np.zeros(6);mujoco.mj_contactForce(m,d,i,force);counts[j]+=1;normals[j]+=force[0]
        if any(n.startswith(('aisle_obstacle','dynamic_cart')) for n in names) and any(n.startswith(('base_collision','left_arm','right_arm','cargo_','left_finger','right_finger','left_palm','right_palm')) for n in names):forbidden.append(i)
    return counts,normals,len(forbidden)

class WheelNavigator:
    def __init__(self,servo,adaptive):self.servo=servo;self.adaptive=adaptive;self.last=np.zeros(2)
    def step(self,d,goal,turn=False,reverse=False,stability=1.):
        pose=base_pose(d)
        if turn:
            err=wrap(goal[2]-pose[2]);desired=np.array([0,np.clip(3.0*err,-.55,.55)])
            done=abs(err)<.012 and abs(d.qvel[5])<.025
        else:
            delta=np.asarray(goal[:2])-pose[:2];dist=float(np.linalg.norm(delta))
            heading=np.arctan2(delta[1],delta[0])+(np.pi if reverse else 0)
            err=wrap(heading-pose[2]);sgn=-1 if reverse else 1
            desired=np.array([sgn*min(.23,1.2*dist)*max(0,np.cos(err)),np.clip(2.8*err,-.5,.5)])
            done=dist<.010
            if done:desired[:]=0
        if self.adaptive:desired*=stability
        accel=np.array([.20,.8])*DT
        self.last+=np.clip(desired-self.last,-accel,accel)
        v,w=self.last;d.ctrl[self.servo.wheels]=[(v-w*TRACK/2)/WHEEL_RADIUS,(v+w*TRACK/2)/WHEEL_RADIUS]
        return done

def run(seed=0,method='shared',target_height=.70,obstacle=True,out=None,max_time=100.,video=False,load_scale=1.,friction_scale=1.,obstacle_x=-.24,push=0.,dynamic=False,noise=0.,latency=0.,dropout=0.,safety=True):
    start=time.perf_counter();m,d,info,xml=make_model(True,seed,obstacle,target_height,load_scale,friction_scale,obstacle_x,dynamic)
    out=Path(out or HERE/'outputs'/f'{method}_{seed:03d}');out.mkdir(parents=True,exist_ok=True)
    (out/'scene.xml').write_text(xml,encoding='utf-8')
    info.update(method=method,push=push,noise=noise,latency=latency,dropout=dropout,safety=safety,trajectory_source='synthetic_tracking_packets_with_state_guards',controller_observation='ideal_simulated_state_and_contact_force')
    ik=Controller(m,d,coupled=method!='uncoupled');servo=Servo(m,d);nav=WheelNavigator(servo,True)
    shared=method.startswith('shared');anchor_waist=method=='stable' or (shared and method!='shared_free_waist')
    if anchor_waist:
        from stable_control import StableController
        ik=StableController(m,d,True)
        nav.adaptive=True
    for task in ik.tasks:task.set_orientation_cost(1.)
    grip_z=info['grasp_z'];carry_z=max(grip_z+.10,target_height+.12)
    p0=np.array([[info['x'],info['y']+.30,grip_z+.09],[info['x'],info['y']-.30,grip_z+.09]])
    ik.initialize(d,p0,np.eye(3));servo.qtarget=d.qpos.copy();d.ctrl[servo.fingers]=.045
    for a in servo.fingers:d.qpos[m.jnt_qposadr[m.actuator_trnid[a,0]]]=.045
    for _ in range(500):servo.apply(d);mujoco.mj_step(m,d)
    mujoco.mj_forward(m,d);d.time=0
    p=np.array([d.site(s+'_ee').xpos.copy() for s in ['left','right']]);R=np.eye(3);phase='approach';phase_start=0.;ap=.045
    events=[];hold=0.;success=False;failure='timeout';retry=0
    # Geometric corridor construction: swept base envelope plus 24 cm margin.
    lane=min(-.62,obstacle_x-.18-.22-.24) if obstacle else -.62
    info['planned_lane_x']=lane
    route=[('back',[lane,0,0],False,True),('turn_out',[lane,0,np.pi/2],True,False),('travel',[lane,info['distance'],np.pi/2],False,False),('turn_in',[lane,info['distance'],0],True,False),('dock',[0,info['distance'],0],False,False),('square_up',[0,info['distance'],0],True,False)]
    nav_index=0;grip_gap=.054;slip=0.;max_slip=0.;push_time=None;previous_slip=0.;slip_rate=0.;cart_start=None;wait_frames=0;placement_anchor=None
    channel=InputChannel(seed,noise,latency,dropout,shared=shared)
    channel.compensate=method!='shared_no_frame'
    rows=[];qposes=[];qvels=[];commands=[];targets=[];phase_ids=[];phase_names=[];max_lift=0.;max_tilt=0.;max_base_tilt=0.;forbidden_total=0;grasped=False
    renderer=writer=None
    def transition(name):
        nonlocal phase,phase_start,hold
        events.append({'time':float(d.time),'from':phase,'to':name});print(f'{d.time:.2f} {phase} -> {name}',flush=True)
        phase=name;phase_start=d.time;hold=0
    try:
        for step in range(round(max_time/DT)):
            t=float(d.time);elapsed=t-phase_start;mujoco.mj_forward(m,d)
            pose=base_pose(d);counts,forces,bad=contacts(m,d);forbidden_total+=bad
            if bad:
                failure='obstacle_collision';events.append({'time':t,'safety_termination':failure});break
            cargo=d.body('cargo').xpos.copy();matrix=d.body('cargo').xmat.reshape(3,3)
            tilt=np.arccos(np.clip(matrix[2,2],-1,1));base_tilt=np.arccos(np.clip(d.body('base_footprint_link').xmat.reshape(3,3)[2,2],-1,1))
            max_lift=max(max_lift,cargo[2]-(info['source_height']+.020));max_tilt=max(max_tilt,tilt);max_base_tilt=max(max_base_tilt,base_tilt)
            measured=np.array([d.site(s+'_ee').xpos.copy() for s in ['left','right']]);error=float(np.max(np.linalg.norm(measured-p,axis=1)))
            slip=max(0.,float(np.mean(measured[:,2])-cargo[2]-grip_gap))
            slip_rate=.9*slip_rate+.1*(slip-previous_slip)/DT;previous_slip=slip
            if phase in ['lift','navigate','align']:max_slip=max(max_slip,slip)
            stability=float(np.clip(min((.05-error)/.035,(.20-tilt)/.14,(.03-slip_rate)/.025),.25,1.0))
            if phase in ['lift','navigate','align']:
                # Additional closure preload (motor force still capped at 35 N)
                # responds to measured vertical slip, without changing physics.
                ap=-float(np.clip(2.0*(slip-.001),0,.020))
            d.xfrc_applied[:]=0
            if phase=='navigate' and nav_index==2 and push_time is None:push_time=t+1.0
            if push_time is not None and push_time<t<push_time+1.0:
                d.xfrc_applied[m.body('base_footprint_link').id,5]=push
            wanted=p.copy()
            if phase=='approach':
                wanted[:]=[[info['x'],info['y']+.30,grip_z],[info['x'],info['y']-.30,grip_z]]
                if np.max(np.linalg.norm(measured-wanted,axis=1))<.008:hold+=DT
                else:hold=0
                if hold>.25:transition('close')
                if elapsed>10:failure='approach_not_reached';break
            elif phase=='close':
                ap=max(0,ap-.035*DT)
                if np.all(counts>=2) and np.all(forces>3):hold+=DT
                else:hold=0
                if hold>.4:grasped=True;grip_gap=float(np.mean(measured[:,2])-cargo[2]);transition('lift')
                if elapsed>5:failure='grasp_contact_not_established';break
            elif phase=='lift':
                wanted[:,2]=carry_z
                if cargo[2]>info['source_height']+.10 and error<.015 and np.max(np.abs(measured[:,2]-carry_z))<.012:hold+=DT
                else:hold=0
                if hold>.5:transition('navigate')
                if elapsed>12:failure='lift_not_verified';break
            elif phase=='navigate':
                name,goal,turn,reverse=route[nav_index]
                R=rz(pose[2]);local=np.array([[info['x'],info['y']+.30,carry_z],[info['x'],info['y']-.30,carry_z]])
                wanted=(R@local.T).T+np.r_[pose[:2],0]
                if dynamic:
                    if nav_index==2 and cart_start is None:cart_start=t
                    if cart_start is not None:cart_update(m,d,t-cart_start)
                    gate=collision_gate(m,d,pose,nav.last[0]) if safety and nav_index==2 else 1.
                    if gate==0:wait_frames+=1
                    stability*=gate
                done=nav.step(d,goal,turn,reverse,stability)
                if done:
                    events.append({'time':t,'navigation_completed':name,'base':pose.tolist()});nav_index+=1
                    if nav_index==len(route):
                        nav.last[:]=0;d.ctrl[servo.wheels]=0;R=np.eye(3);transition('align')
                if cargo[2]<.30 or tilt>.75:failure='payload_dropped';break
            elif phase=='align':
                d.ctrl[servo.wheels]=0
                wanted[:]=[[info['x'],info['y']+.30+info['distance'],carry_z],[info['x'],info['y']-.30+info['distance'],carry_z]];R=np.eye(3)
                if np.max(np.linalg.norm(measured-wanted,axis=1))<.010:hold+=DT
                else:hold=0
                if hold>.4:transition('lower')
                if elapsed>10:failure='target_alignment_failed';break
            elif phase=='lower':
                wanted[:,2]=target_height+.073
                supported=any('destination_top' in [m.geom(c.geom1).name,m.geom(c.geom2).name] and 'cargo_main' in [m.geom(c.geom1).name,m.geom(c.geom2).name] for c in d.contact)
                if shared and method!='shared_no_contact' and supported and placement_anchor is None:
                    placement_anchor=measured.copy();placement_anchor[:,2]-=.003
                if supported and abs(cargo[2]-(target_height+.020))<.004:hold+=DT;wanted=measured.copy()
                else:hold=0
                if hold>.5:transition('release')
                if elapsed>10:failure='placement_contact_not_reached';break
            elif phase=='release':
                ap=min(.045,ap+.04*DT)
                if ap>=.044 and np.sum(counts)==0:hold+=DT
                else:hold=0
                if hold>.3:transition('retreat')
            elif phase=='retreat':
                wanted[:,2]=target_height+.16
                if np.max(np.abs(measured[:,2]-wanted[:,2]))<.012:transition('verify')
                if elapsed>8:failure='hand_retreat_failed';break
            elif phase=='verify':
                joint=m.joint('cargo_free');vid=int(joint.dofadr[0]);linear=np.linalg.norm(d.qvel[vid:vid+3]);angular=np.linalg.norm(d.qvel[vid+3:vid+6])
                offset=matrix.T@(d.body('parcel').xpos-cargo)
                retained=abs(offset[0])<.09 and abs(offset[1])<.34 and .03<offset[2]<.12
                good=(np.linalg.norm(cargo[:2]-np.array(info['goal'][:2]))<.035 and abs(cargo[2]-info['goal'][2])<.01 and linear<.02 and angular<.1 and retained and np.sum(counts)==0 and tilt<.12 and forbidden_total==0)
                hold=hold+DT if good else 0
                if hold>1.0:success=True;failure=None;transition('complete');break
                if elapsed>6:failure='final_stability_check_failed';break
            delta=wanted-p
            # Limit synthetic hand goals to a continuous, 8 cm/s trajectory.
            speed=.08 if phase not in ['navigate'] else .45
            p+=delta*np.minimum(1,speed*DT/np.maximum(np.linalg.norm(delta,axis=1,keepdims=True),1e-8))
            input_p,input_R,input_age=channel.update(t,p,R,pose,phase=='navigate')
            if shared and placement_anchor is not None and phase in ['lower','release']:
                input_p=placement_anchor.copy();input_R=R.copy()
            try:
                if anchor_waist:ik.set_phase(phase,d)
                qsolution=ik.step(d,input_p,input_R)
                servo.qtarget[ik.qids]=qsolution[ik.qids]
            except Exception as exc:failure='ik_failure: '+repr(exc);break
            d.ctrl[servo.fingers]=ap
            for _ in range(5):servo.apply(d);mujoco.mj_step(m,d)
            if phase not in phase_names:phase_names.append(phase)
            phase_ids.append(phase_names.index(phase));qposes.append(d.qpos.copy());qvels.append(d.qvel.copy());commands.append(d.ctrl.copy());targets.append(np.r_[p.ravel(),R.ravel(),ap])
            rows.append([t,*pose,*cargo,error,tilt,base_tilt,*forces,*counts,stability,bad,slip,ap,float(d.xfrc_applied[m.body('base_footprint_link').id,5]),input_age])
        summary={**info,'success':success,'failure':failure,'completion_time_s':float(d.time),'grasp_contact_verified':grasped,'max_lift_m':float(max_lift),'max_slip_m':max_slip,'max_payload_tilt_deg':float(np.rad2deg(max_tilt)),'max_base_tilt_deg':float(np.rad2deg(max_base_tilt)),'obstacle_contact_frames':forbidden_total,'final_payload_position':d.body('cargo').xpos.tolist(),'final_base_pose':base_pose(d).tolist(),'wall_seconds':time.perf_counter()-start,'steps':len(rows),'phases':phase_names,'events':events}
        (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
        summary.update(safety_wait_s=wait_frames*DT,dropped_packets=channel.gaps,packets=len(channel.packet_log))
        (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
        with (out/'input_packets.jsonl').open('w',encoding='utf-8') as f:
            for timestamp,position,rotation,base,dropped in channel.packet_log:
                f.write(json.dumps({'timestamp':timestamp,'frame':'world_meters','left':position[0].tolist(),'right':position[1].tolist(),'rotation':rotation.tolist(),'base_at_capture':base.tolist(),'dropped':bool(dropped),'source':'synthetic_tracking_model','hardware_verified':False})+'\n')
        np.savez_compressed(out/'trajectory.npz',qpos=np.asarray(qposes),qvel=np.asarray(qvels),ctrl=np.asarray(commands),targets=np.asarray(targets),phase=np.asarray(phase_ids),metrics=np.asarray(rows),metadata=json.dumps(summary))
        np.savetxt(out/'metrics.csv',rows,delimiter=',',header='time,base_x,base_y,base_yaw,cargo_x,cargo_y,cargo_z,ee_error,tilt,base_tilt,left_force,right_force,left_contacts,right_contacts,speed_scale,obstacle_contacts,slip,aperture_command,push_yaw_torque,input_age',comments='')
        print(json.dumps({k:v for k,v in summary.items() if k!='events'},ensure_ascii=False),flush=True)
        if video:
            from render import render
            render(out)
        return summary
    finally:
        if writer:writer.close()
        if renderer:renderer.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--seed',type=int,default=0);p.add_argument('--method',choices=['adaptive','stable','shared','shared_free_waist','shared_no_contact','shared_no_frame'],default='shared');p.add_argument('--target-height',type=float,default=.70);p.add_argument('--out');p.add_argument('--max-time',type=float,default=100.);p.add_argument('--load-scale',type=float,default=1.);p.add_argument('--friction-scale',type=float,default=1.);p.add_argument('--obstacle-x',type=float,default=-.24);p.add_argument('--push',type=float,default=0.);p.add_argument('--dynamic',action='store_true');p.add_argument('--noise',type=float,default=0.);p.add_argument('--latency',type=float,default=0.);p.add_argument('--dropout',type=float,default=0.);p.add_argument('--unsafe',action='store_true');a=p.parse_args();dct=vars(a);dct['safety']=not dct.pop('unsafe');run(**dct)
