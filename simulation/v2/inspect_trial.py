from pathlib import Path
import sys,json,numpy as np,mujoco
from PIL import Image

folder=Path(sys.argv[1]);m=mujoco.MjModel.from_xml_path(str(folder/'scene.xml'));d=mujoco.MjData(m)
z=np.load(folder/'trajectory.npz');qs=z['qpos'];vs=z['qvel'];targets=z['targets'];metrics=z['metrics']
renderer=mujoco.Renderer(m,720,1200);cam=mujoco.MjvCamera();cam.lookat[:]=[0,.25,.78];cam.distance=2.6;cam.azimuth=145;cam.elevation=-22
for seconds in [0,2,5,9,20,35,50,65,80]:
    i=min(len(qs)-1,seconds*100);d.qpos[:]=qs[i];d.qvel[:]=vs[i];mujoco.mj_forward(m,d)
    print(seconds,'hands',np.array([d.site(s+'_ee').xpos for s in ['left','right']]),'goal',targets[i,:6].reshape(2,3),'row',metrics[i].round(4).tolist())
    if seconds in [0,5,9,35,65]:
        cam.lookat[:2]=d.body('base_footprint_link').xpos[:2]+[.2,0]
        renderer.update_scene(d,camera=cam);Image.fromarray(renderer.render()).save(folder/f'inspect_{seconds}.png')
    if seconds*100>=len(qs):break
renderer.close()
