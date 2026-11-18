"""World-frame differential IK using the Apache-2.0 Mink library.

Mink handles SE(3) tasks, QP solution, position and velocity limits. This module
adds YMBOT joint selection and measured-base vs nominal-base ablation.
"""
import numpy as np
import mujoco
import mink
from scipy.spatial.transform import Rotation

DT=.01
SIDES=('left','right')

class Controller:
    def __init__(self,model,data,coupled=False):
        self.m=model
        self.config=mink.Configuration(model,data.qpos)
        self.jids=[i for i in range(model.njnt)
                     if 'Arm_Joint' in model.joint(i).name or model.joint(i).name in ('Body_Joint1','Body_Joint2','Body_Joint3')]
        self.active=[int(model.jnt_dofadr[i]) for i in self.jids]
        self.freeze=mink.DofFreezingTask(model,[i for i in range(model.nv) if i not in self.active])
        self.tasks=[mink.FrameTask(s+'_ee','site',position_cost=5.,orientation_cost=1.,lm_damping=.002) for s in SIDES]
        costs=np.zeros(model.nv); costs[self.active]=.003
        self.posture=mink.PostureTask(model,cost=costs)
        self.posture.set_target(data.qpos.copy())
        self.limits=[mink.ConfigurationLimit(model),mink.VelocityLimit(model,{model.joint(i).name:1.0 for i in self.jids})]
        self.qids=np.array([model.jnt_qposadr[i] for i in self.jids])
        self.aids=np.array([model.actuator(model.joint(i).name).id for i in self.jids])
        self.solve_times=[]
        self.relative=mink.RelativeFrameTask('left_ee','site','right_ee','site',position_cost=50.,orientation_cost=10.,lm_damping=.002) if coupled else None

    def step(self,data,positions,rotation,nominal_base=None,initial=False):
        q=data.qpos.copy()
        # Soft contact limits can penetrate slightly in the dynamics engine.
        # Project the IK observation onto the legal interval; physics states
        # are never overwritten. This avoids infeasible frozen finger rows.
        for j in range(self.m.njnt):
            if self.m.jnt_limited[j] and self.m.jnt_type[j] in (2,3):
                idx=self.m.jnt_qposadr[j]
                q[idx]=np.clip(q[idx],*self.m.jnt_range[j])
        if nominal_base is not None: q[:3]=nominal_base
        self.config.update(q)
        rot=mink.SO3.from_matrix(rotation)
        for t,p in zip(self.tasks,positions):
            t.set_target(mink.SE3.from_rotation_and_translation(rot,p))
        extra=[]
        if self.relative is not None:
            self.relative.set_target(mink.SE3.from_rotation_and_translation(mink.SO3.identity(),rotation.T@(positions[0]-positions[1])))
            extra=[self.relative]
        v=mink.solve_ik(self.config,[*self.tasks,self.posture,*extra],DT,'daqp',damping=1e-4,
                        limits=self.limits,constraints=[self.freeze])
        self.config.integrate_inplace(v,DT)
        data.ctrl[self.aids]=self.config.q[self.qids]
        return self.config.q.copy()

    def initialize(self,data,positions,rotation):
        # IK-only initialization before simulated time zero; never moves cargo.
        for _ in range(500):
            q=self.step(data,positions,rotation)
            data.qpos[self.qids]=q[self.qids]
        self.posture.set_target(data.qpos.copy())
        mujoco.mj_forward(self.m,data)

def rz(yaw):
    return Rotation.from_euler('z',yaw).as_matrix()

def smooth(x):
    x=np.clip(x,0,1)
    return x*x*x*(10+x*(-15+6*x))

def interp(a,b,t,t0,t1):
    return np.asarray(a)+(np.asarray(b)-np.asarray(a))*smooth((t-t0)/(t1-t0))
