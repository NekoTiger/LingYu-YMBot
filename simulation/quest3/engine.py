"""Live MuJoCo simulation; network clients supply intent, never physics states."""
from pathlib import Path
import sys,time,json,uuid
import numpy as np,mujoco
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'v2'))
from model import make_model,Servo,WHEEL_RADIUS,TRACK
from stable_control import StableController
from control import rz
from experiment import base_pose
from .protocol import Mailbox,RelativeTrayMapper
from .trial import Trial, observe
from .carry_assist import CarryAssist
from .workspace_follow import WorkspaceFollow, ProximityBrake

HERE=Path(__file__).resolve().parent

class Recorder:
    def __init__(self,root,xml):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=False)
        (self.root/'scene.xml').write_text(xml,encoding='utf-8')
        self.raw=(self.root/'raw_webxr.jsonl').open('w',encoding='utf-8');self.events=(self.root/'events.jsonl').open('w',encoding='utf-8')
        self.rows=[];self.index=0;self.frames=0;self.packets=0;self.start=time.time()
        self.meta={'source':'awaiting_client','hardware_verified':False,'device_claim':'not_connected','schema':1,'control_dt_s':.01,'physics_dt_s':.002,'start_unix_s':self.start,'view':'adjustable stereoscopic simulation, side-by-side default; not robot camera video','mapping':'relative controller center + limited yaw; level rigid tray, synchronized jaws; full raw head/hand poses retained'}
    def event(self,name,**extra):self.events.write(json.dumps({'wall_unix_s':time.time(),'event':name,**extra},ensure_ascii=False)+'\n');self.events.flush()
    def packet(self,raw,received):self.raw.write(json.dumps({'server_received_monotonic_s':received,'packet':raw},ensure_ascii=False,allow_nan=False)+'\n');self.packets+=1
    def step(self,engine,wall):
        self.rows.append((engine.d.time,wall,engine.d.qpos.copy(),engine.d.qvel.copy(),engine.d.ctrl.copy(),engine.target_world.copy(),engine.active,
                          engine.twist.copy(), engine.follow.speed, engine.proximity.scale,
                          getattr(engine.mapper, 'raw_center', engine.local.mean(axis=0)).copy()));self.frames+=1
        if len(self.rows)>=3000:self.flush()
    def flush(self):
        if not self.rows:return
        np.savez_compressed(self.root/f'states_{self.index:04d}.npz',sim_time=[r[0]for r in self.rows],wall_elapsed=[r[1]for r in self.rows],qpos=np.array([r[2]for r in self.rows]),qvel=np.array([r[3]for r in self.rows]),ctrl=np.array([r[4]for r in self.rows]),hand_target=np.array([r[5]for r in self.rows]),active=[r[6]for r in self.rows],
                            base_command=np.array([r[7]for r in self.rows]), follow_request=[r[8]for r in self.rows], proximity_scale=[r[9]for r in self.rows], raw_hand_center=np.array([r[10]for r in self.rows]))
        self.index+=1;self.rows=[];self.raw.flush()
    def close(self,engine):
        self.flush();self.raw.close();self.events.close()
        self.meta.update(control_frames=self.frames,received_packets=self.packets,chunks=self.index,simulated_seconds=engine.d.time,wall_seconds=time.time()-self.start,calibrations=engine.calibrations,final_status=engine.status,
                         follow_metrics=engine.follow.snapshot())
        (self.root/'session.json').write_text(json.dumps(self.meta,ensure_ascii=False,indent=2),encoding='utf-8')

class Engine:
    def __init__(self,record_root=None,mode='legacy',target_height=.70,seed=0,trial_config=None,follow_policy='gated',model_factory=make_model):
        if mode not in ('legacy', 'baseline', 'assisted', 'follow'):
            raise ValueError('Unknown control mode')
        self.mode = mode
        self.load_assist = mode in ('assisted', 'follow')
        self.follow = WorkspaceFollow(follow_policy if mode == 'follow' else 'off')
        self.last_follow_state = None
        self.carry_anchor_z = None
        self.m,self.d,self.info,self.xml=model_factory(True,seed,True,target_height);self.servo=Servo(self.m,self.d);self.ik=StableController(self.m,self.d,True)
        initial=np.array([[self.info['x'],self.info['y']+.30,.838],[self.info['x'],self.info['y']-.30,.838]])
        self.ik.initialize(self.d,initial,np.eye(3));self.servo.qtarget=self.d.qpos.copy();self.aperture=.045;self.aperture_goal=.045;self.last_trigger=0.
        self.d.ctrl[self.servo.fingers]=.045
        for a in self.servo.fingers:self.d.qpos[self.m.jnt_qposadr[self.m.actuator_trnid[a,0]]]=.045
        for _ in range(500):self.servo.apply(self.d);mujoco.mj_step(self.m,self.d)
        self.d.time=0.;mujoco.mj_forward(self.m,self.d)
        self.mail=Mailbox();self.mapper=RelativeTrayMapper();self.active=False;self.estop=False;self.must_release=True;self.status='waiting';self.calibrations=0
        self.local=initial.copy();self.local_yaw=0.;self.target_world=initial.copy();self.twist=np.zeros(2);self.started=time.monotonic();self.last_status=None
        self.visible=[i for i in range(self.m.ngeom)if self.m.geom_rgba[i,3]>.01 and self.m.geom_group[i]!=3]
        self.recorder=Recorder(record_root or HERE/'sessions'/(time.strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6]),self.xml)
        self.recorder.meta.update(control_mode=mode, scene=self.info, clock_mode='live_server_monotonic')
        self.proximity = ProximityBrake(self.m)
        if mode == 'follow':
            self.recorder.meta['workspace_follow'] = self.follow.metadata()
        self.observation = observe(self.m, self.d)
        self.assistance = CarryAssist()
        self.filtered_goal = self.local.copy()
        self.trial = Trial(self, trial_config) if trial_config else None
        if trial_config:
            (self.recorder.root/'experiment_config.json').write_text(json.dumps(trial_config, ensure_ascii=False, indent=2), encoding='utf-8')
    def connect(self,source,device):
        self.mail.clear();self.active=False;self.must_release=True
        sources=self.recorder.meta.setdefault('sources_seen',[])
        if source not in sources:sources.append(source)
        self.recorder.meta.update(source=source if len(sources)==1 else 'mixed_sources',device_claim=device,hardware_verified=False)
        self.recorder.event('client_connected',source=source,device_claim=device)
    def receive(self,raw,now=None):
        now=time.monotonic()if now is None else now
        try:p=self.mail.push(raw,now)
        except (ValueError,KeyError,TypeError,OverflowError)as exc:
            self.mail.rejected+=1;self.mail.packet=None;self.must_release=True
            self.recorder.event('packet_rejected',reason=str(exc));return False
        self.recorder.packet(raw,now)
        if p.estop:self.stop('operator_stop')
        return True
    def stop(self,reason='operator_stop'):
        changed = not self.estop or getattr(self, 'stop_reason', None) != reason
        self.stop_reason = reason
        self.estop=True;self.active=False;self.must_release=True;self.status=reason;self.d.ctrl[self.servo.wheels]=0;self.twist[:]=0
        self.follow.reset('inactive')
        if changed:
            self.recorder.event('stop',reason=reason)
    def clear_stop(self):
        p=self.mail.packet
        if p is not None and np.any(p.squeeze>.2):return False
        self.estop=False;self.must_release=True;self.active=False;self.recorder.event('stop_cleared');return True
    def disconnect(self):self.mail.packet=None;self.must_release=True;self.active=False;self.status='disconnected';self.d.ctrl[self.servo.wheels]=0;self.twist[:]=0;self.follow.reset('inactive');self.recorder.event('client_disconnected')
    def step(self,now=None):
        now=time.monotonic()if now is None else now;p=self.mail.packet;fresh=p is not None and now-self.mail.received<=.25
        enabled=fresh and p.tracked and bool(np.all(p.squeeze>.65)) and not self.estop
        if fresh and p.tracked and np.all(p.squeeze<.2):self.must_release=False
        if not fresh or (p is not None and not p.tracked):self.must_release=True
        enabled=bool(enabled and not self.must_release)
        if self.trial and self.trial.status != 'running':
            enabled = False
        pose=base_pose(self.d);rotbase=rz(pose[2]);translation=np.r_[pose[:2],0]
        if enabled and not self.active:
            hands=np.array([self.d.site(s+'_ee').xpos.copy()for s in ['left','right']]);self.local=(rotbase.T@(hands-translation).T).T
            self.mapper.calibrate(p,self.local);self.local_yaw=self.mapper.robot_yaw;self.calibrations+=1;self.recorder.event('clutch_calibrated',count=self.calibrations,seq=p.seq)
            self.aperture_goal=float(self.aperture);self.last_trigger=float(np.mean(p.trigger))
            self.filtered_goal = self.local.copy()
            self.assistance.reset_placement()
            self.follow.calibrate(self.mapper.robot_center[0])
            self.carry_anchor_z = None
            self.on_calibrate()
        if enabled:
            wanted,yaw=self.mapper.map(p)
            if self.mode == 'follow' and self.assistance.grasped and (
                    self.observation.source_support_n+self.observation.destination_support_n < .10*(self.info['mass']+.17)*9.81):
                # Same arm workspace in all three follow-policy comparisons.
                center = wanted.mean(axis=0)
                offset = self.follow.origin_x-.50
                bounded_x = np.clip(center[0], offset+self.follow.parameters.arm_lower, offset+self.follow.parameters.arm_upper)
                wanted[:, 0] += bounded_x-center[0]
            wanted = self.shape_hand_goal(wanted)
            if self.mode != 'legacy':
                self.filtered_goal += (1 - np.exp(-.01 / .06)) * (wanted - self.filtered_goal)
                wanted = self.filtered_goal
            if self.load_assist:
                wanted = self.assistance.placement_goal(wanted, self.observation, self.info, self.aperture_goal, self.aperture)
            delta=wanted-self.local
            self.local+=delta*np.minimum(1,.12*.01/np.maximum(np.linalg.norm(delta,axis=1,keepdims=True),1e-9));self.local_yaw+=np.clip(yaw-self.local_yaw,-.006,.006)
            sticks=np.where(np.abs(p.stick)>.15,p.stick,0);desired=np.array([-.16*sticks[1],-.4*sticks[0]])
            if self.mode == 'follow':
                obs = self.observation
                weight = (self.info['mass']+.17)*9.81
                supported = obs.source_support_n+obs.destination_support_n > .10*weight
                contacts = all(n >= 2 for n in obs.hand_contacts) and all(f > 3 for f in obs.hand_forces)
                # Opening intent blocks following in this very packet, before aperture integration.
                opening = np.mean(p.trigger) < self.last_trigger-.002 or self.aperture_goal > .004
                eligible = (self.assistance.grasped and contacts and not supported and not opening
                            and obs.cargo_position[2] > self.info['source_height']+.08
                            and obs.cargo_tilt_rad < .15 and self.assistance.slip < .012
                            and self.assistance.placement_target is None)
                manual = bool(np.any(sticks))
                auto = self.follow.update(self.mapper.raw_center[0], eligible=eligible, manual=manual)
                self.proximity.scale = 1.
                if not manual:
                    desired[0] = self.proximity.limit(self.d, auto, pose[2], self.twist[0])
                if self.follow.state != self.last_follow_state:
                    self.recorder.event('workspace_follow', **self.follow.snapshot())
                    self.last_follow_state = self.follow.state
            if self.load_assist:
                # Assist speed scaling protects the payload in the forward channel only;
                # steering the base does not disturb the lifted object.
                desired[0] *= self.assistance.speed_scale
                if self.assistance.placement_target is not None:
                    desired[:] = 0.
            self.twist+=np.clip(desired-self.twist,[-.002,-.008],[.002,.008])
            self.allocate_motion(desired, pose)
            self.target_world=(rotbase@self.local.T).T+translation
            anchor = self.mode != 'baseline' and np.linalg.norm(self.twist) > .01
            if self.mode == 'follow':
                # Keep the same torso reference through brief navigation pauses.
                # Explicit height changes and unloading still release the torso.
                z = float(wanted[:, 2].mean())
                keep = (self.assistance.grasped and contacts and not supported and not opening
                        and self.assistance.placement_target is None)
                if self.carry_anchor_z is not None and (not keep or abs(z-self.carry_anchor_z) > .02):
                    self.carry_anchor_z = None
                if anchor and keep and self.carry_anchor_z is None:
                    self.carry_anchor_z = z
                anchor = anchor or self.carry_anchor_z is not None
            self.ik.set_phase('navigate' if anchor else 'approach',self.d)
            try:
                solution=self.ik.step(self.d,self.target_world,rz(pose[2]+self.local_yaw));self.servo.qtarget[self.ik.qids]=solution[self.ik.qids]
            except Exception as exc:self.stop('ik_fault');self.recorder.event('ik_fault',error=repr(exc));enabled=False
            if enabled:
                trigger=float(np.mean(p.trigger))
                self.aperture_goal=float(np.clip(self.aperture_goal-.045*(trigger-self.last_trigger),0,.045));self.last_trigger=trigger
                grip_goal = self.aperture_goal
                if self.load_assist:
                    grip_goal = self.assistance.aperture_target(grip_goal, self.aperture)
                self.aperture=float(self.aperture+np.clip(grip_goal-self.aperture,-.00035,.00035))
                self.d.ctrl[self.servo.wheels]=[(self.twist[0]-self.twist[1]*TRACK/2)/WHEEL_RADIUS,(self.twist[0]+self.twist[1]*TRACK/2)/WHEEL_RADIUS]
                self.status='active'
        else:
            self.twist[:]=0;self.d.ctrl[self.servo.wheels]=0
            self.follow.reset('inactive')
            self.status='stopped'if self.estop else ('stale'if not fresh else ('tracking_lost'if not p.tracked else 'clutch_released'))
        self.active=enabled;self.d.ctrl[self.servo.fingers]=self.aperture
        for _ in range(5):self.servo.apply(self.d);mujoco.mj_step(self.m,self.d)
        if not np.all(np.isfinite(self.d.qpos)):raise RuntimeError('nonfinite physical state')
        mujoco.mj_forward(self.m, self.d)
        self.observation = observe(self.m, self.d)
        self.assistance.update(self.observation, self.info['mass'] + .17, self.target_world, self.aperture)
        self.after_observe(now)
        if self.status!=self.last_status:self.recorder.event('status',status=self.status,sim_time=self.d.time);self.last_status=self.status
        self.recorder.step(self,now-self.started)
        if self.trial:
            self.trial.update(self, self.observation, now)
    def on_calibrate(self):
        pass
    def shape_hand_goal(self, wanted):
        return wanted
    def allocate_motion(self, desired, pose):
        pass
    def after_observe(self, now):
        pass
    def snapshot(self):
        mujoco.mj_forward(self.m,self.d);transforms=[]
        for gid in self.visible:
            q=np.zeros(4);mujoco.mju_mat2Quat(q,self.d.geom_xmat[gid]);transforms.append(np.r_[self.d.geom_xpos[gid],q[[1,2,3,0]]].round(6).tolist())
        return {'type':'state','sim_time':self.d.time,'status':self.status,'active':self.active,'calibrations':self.calibrations,'packet_age_ms':None if self.mail.packet is None else round((time.monotonic()-self.mail.received)*1000,1),'rejected_packets':self.mail.rejected,'aperture':self.aperture,'base_twist':self.twist.tolist(),'transforms':transforms,'source':self.recorder.meta['source'],'hardware_verified':False,
                'control_mode': self.mode, 'release_blocked': self.load_assist and self.assistance.release_blocked,
                'workspace_follow': {**self.follow.snapshot(), 'proximity_scale': self.proximity.scale} if self.mode == 'follow' else None,
                'experiment': self.trial.snapshot(time.monotonic()) if self.trial else None}
    def close(self):
        if self.trial and self.trial.status == 'running':
            self.trial.finish(self, 'failure', 'reset_or_shutdown_during_trial')
        self.recorder.close(self)
