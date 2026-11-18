"""Render saved MuJoCo states as presentation evidence, without resimulation."""
from pathlib import Path
import json
import numpy as np
import mujoco
from PIL import Image

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent/'assets'
OUT.mkdir(exist_ok=True)
records=[]
def draw(folder,filename,index,lookat,distance,azimuth,elevation,source):
    model=mujoco.MjModel.from_xml_path(str(folder/'scene.xml'))
    model.vis.global_.offwidth=1600; model.vis.global_.offheight=1000
    state=mujoco.MjData(model)
    data=np.load(folder/filename)
    for key in ['qpos','qvel','ctrl']: getattr(state,key)[:]=data[key][index]
    mujoco.mj_forward(model,state)
    cam=mujoco.MjvCamera();cam.lookat[:]=lookat;cam.distance=distance;cam.azimuth=azimuth;cam.elevation=elevation
    with mujoco.Renderer(model,1000,1600) as renderer:
        renderer.update_scene(state,camera=cam)
        Image.fromarray(renderer.render()).save(OUT/source)
    records.append({'image':source,'source':str(folder/filename),'frame_index':index,'render_only':True})

demo=ROOT/'simulation/research/outputs/demo_dynamic'
draw(demo,'trajectory.npz',800,[0,.05,.88],2.30,205,-16,'cover.png')
draw(demo,'trajectory.npz',2500,[-.20,.88,.72],4.3,180,-26,'task.png')
draw(demo,'trajectory.npz',5450,[.25,1.65,.85],2.25,160,-20,'placement.png')
live=ROOT/'simulation/quest3/sessions/20261116_115607_04cd8e'
chunks=[(p,np.load(p)) for p in sorted(live.glob('states_*.npz'))]
# Select the largest recorded cargo height, then render that actual recorded state.
m=mujoco.MjModel.from_xml_path(str(live/'scene.xml'))
joint=m.joint('cargo_free') if 'cargo_free' in [m.joint(i).name for i in range(m.njnt)] else None
if joint is None:
    body=m.body('cargo'); joint=m.joint(int(body.jntadr[0]))
zadr=int(joint.qposadr[0])+2
best=max([(float(d['qpos'][:,zadr].max()),p,int(np.argmax(d['qpos'][:,zadr]))) for p,d in chunks])
draw(live,best[1].name,best[2],[.05,.15,.85],3.4,220,-20,'quest_live.png')
(OUT/'provenance.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
print('Rendered',len(records),'saved-state evidence images')
