from pathlib import Path
import mujoco,numpy as np
from PIL import Image,ImageDraw
root=Path(__file__).resolve().parent/'outputs/dev_stress02';m=mujoco.MjModel.from_xml_path(str(root/'scene.xml'));d=mujoco.MjData(m)
z=np.load(root/'trajectory.npz');d.qpos[:]=z['qpos'][500];mujoco.mj_forward(m,d)
r=mujoco.Renderer(m,360,640);grid=Image.new('RGB',(1920,720))
for i,az in enumerate([0,90,150,180,210,270]):
    c=mujoco.MjvCamera();c.lookat[:]=[-.15,.8,.65];c.distance=4.4;c.azimuth=az;c.elevation=-28;r.update_scene(d,camera=c)
    image=Image.fromarray(r.render());ImageDraw.Draw(image).text((10,10),str(az),fill='red');grid.paste(image,((i%3)*640,(i//3)*360))
grid.save(root/'cameras.jpg');r.close()
