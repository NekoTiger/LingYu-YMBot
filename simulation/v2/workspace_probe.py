from model import make_model
from control import Controller
import numpy as np,mujoco
for x in [.25,.40,.55]:
    for z in [.85,.93,.97]:
        m,d,*_=make_model(False);ik=Controller(m,d,True)
        for task in ik.tasks:task.set_orientation_cost(3.)
        target=np.array([[x,.30,z],[x,-.30,z]])
        ik.initialize(d,target,np.eye(3))
        actual=np.array([d.site(s+'_ee').xpos for s in ['left','right']]);r=d.site('left_ee').xmat.reshape(3,3)
        print(x,z,'error',np.linalg.norm(actual-target,axis=1).round(5),'angle',np.arccos(np.clip((np.trace(r)-1)/2,-1,1)).round(4),'torso',d.qpos[7:10].round(3),flush=True)
