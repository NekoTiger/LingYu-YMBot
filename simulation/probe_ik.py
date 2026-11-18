from build_model import MODEL,HERE
import mujoco,mink,numpy as np
from PIL import Image

m=mujoco.MjModel.from_xml_path(str(MODEL)); d=mujoco.MjData(m)
c=mink.Configuration(m)
rotations=[mink.SO3.from_matrix(c.data.site(s+'_ee').xmat.reshape(3,3)) for s in ['left','right']]
arm_ids=[m.joint(i).id for i in range(m.njnt) if 'Arm_Joint' in m.joint(i).name or m.joint(i).name in ['Body_Joint1','Body_Joint2','Body_Joint3']]
freeze=mink.DofFreezingTask(m,[i for i in range(m.nv) if i not in arm_ids])
tasks=[mink.FrameTask(s+'_ee','site',position_cost=5,orientation_cost=1,lm_damping=.01) for s in ['left','right']]
limits=[mink.ConfigurationLimit(m)]
for xyz in [[.38,.30,.78],[.4,.30,.9],[.45,.30,1.0],[.35,.30,.95]]:
    c.update(np.zeros(m.nq))
    for t,sign,rot in zip(tasks,[1,-1],rotations):
        t.set_target(mink.SE3.from_rotation_and_translation(rot,np.array(xyz)*[1,sign,1]))
    for _ in range(300):
        v=mink.solve_ik(c,tasks,.02,'daqp',damping=.001,limits=limits,constraints=[freeze]); c.integrate_inplace(v,.02)
    print(xyz,'errors',[np.round(t.compute_error(c),4).tolist() for t in tasks], 'q',np.round(c.q[arm_ids],3))
    d.qpos[:]=c.q; mujoco.mj_forward(m,d)
    r=mujoco.Renderer(m,720,1280); cam=mujoco.MjvCamera(); cam.lookat[:]=[.1,0,.8];cam.distance=2.7;cam.azimuth=140;cam.elevation=-18
    r.update_scene(d,camera=cam); Image.fromarray(r.render()).save(HERE/'models'/f'ik_{xyz[2]}.png');r.close()
