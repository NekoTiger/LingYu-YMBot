"""Low-speed vertical admittance until the destination supports the load."""
import numpy as np,mujoco

class SupportTransfer:
    def __init__(self,mass):
        self.target=None;self.floor=None;self.force=0.;self.desired_force=.75*mass*9.81
    def update(self,m,d,hands,dt=.01):
        force=0.
        for i in range(d.ncon):
            c=d.contact[i];names=[m.geom(c.geom1).name,m.geom(c.geom2).name]
            if 'destination_top' in names and 'cargo_main' in names:
                wrench=np.zeros(6);mujoco.mj_contactForce(m,d,i,wrench);force+=max(0.,wrench[0])
        self.force=.85*self.force+.15*force
        if force>.1 and self.target is None:
            self.target=hands.copy();self.floor=self.target[:,2]-.04
        if self.target is not None:
            descent=.008*np.clip(1-self.force/max(self.desired_force,1.),0,1)*dt
            self.target[:,2]=np.maximum(self.floor,self.target[:,2]-descent)
        return self.target,self.force
