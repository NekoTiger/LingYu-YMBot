"""Phase-conditioned waist anchoring: carry with arms, unlock for reach changes."""
import numpy as np,mujoco,mink
from control import Controller

class StableController(Controller):
    def __init__(self,model,data,coupled=True):
        super().__init__(model,data,coupled)
        self.torso_jids=[model.joint(f'Body_Joint{i}').id for i in [1,2,3]]
        self.torso_qids=model.jnt_qposadr[self.torso_jids]
        self.torso_dofs=model.jnt_dofadr[self.torso_jids]
        self.full_freeze=self.freeze
        self.arm_freeze=mink.DofFreezingTask(model,[i for i in range(model.nv) if i not in self.active or i in self.torso_dofs])
        self.anchored=False;self.anchor=None
        self.motion_limits=[mink.ConfigurationLimit(model),mink.VelocityLimit(model,{model.joint(i).name:1. for i in self.jids})]
    def initialize(self,data,positions,rotation):
        super().initialize(data,positions,rotation)
        self.limits=self.motion_limits
    def set_phase(self,phase,data):
        wanted=phase=='navigate'
        if wanted and not self.anchored:self.anchor=data.qpos[self.torso_qids].copy()
        self.anchored=wanted;self.freeze=self.arm_freeze if wanted else self.full_freeze
    def step(self,data,positions,rotation,nominal_base=None,initial=False):
        result=super().step(data,positions,rotation,nominal_base,initial)
        if self.anchored:result[self.torso_qids]=self.anchor
        return result
