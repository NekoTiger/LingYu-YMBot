from pathlib import Path
import json,time
import mujoco,numpy as np,imageio.v2 as imageio
from PIL import Image,ImageDraw
from render import font,BG,PANEL,WHITE,MUTED,CYAN,GREEN,ORANGE
from model import HERE

root=HERE/'outputs';trials=[]
for name in ['demo_baseline','demo_heavy']:
    folder=root/name;info=json.loads((folder/'summary.json').read_text(encoding='utf-8'));z=np.load(folder/'trajectory.npz')
    m=mujoco.MjModel.from_xml_path(str(folder/'scene.xml'));d=mujoco.MjData(m);r=mujoco.Renderer(m,576,896)
    trials.append((m,d,r,info,z['qpos'],z['qvel'],z['metrics']))
out=root/'comparison';out.mkdir(parents=True,exist_ok=True);started=time.perf_counter()
try:
    with imageio.get_writer(out/'comparison.mp4',fps=25,codec='libx264',quality=8,macro_block_size=None,ffmpeg_params=['-movflags','+faststart']) as writer:
        for frame in range(18*25):
            t=frame/25;canvas=Image.new('RGB',(1920,900),BG);draw=ImageDraw.Draw(canvas)
            draw.text((36,26),'同一载荷、摩擦系数与场景：夹持反馈消融',font=font(34,True),fill=WHITE)
            info=trials[0][3];draw.text((36,82),f"独立验证种子 {info['seed']}  ·  总载荷 {info['mass']+.17:.2f} kg  ·  摩擦系数 {info['friction']:.2f}  ·  同步原速回放",font=font(22),fill=MUTED)
            for j,(m,d,r,info,q,v,rows) in enumerate(trials):
                idx=min(round(t*100),len(q)-1);d.qpos[:]=q[idx];d.qvel[:]=v[idx];mujoco.mj_forward(m,d);x=36+j*952
                cam=mujoco.MjvCamera();cam.lookat[:]=d.body('base_footprint_link').xpos+[.20,0,.67];cam.distance=2.7;cam.azimuth=180;cam.elevation=-23
                r.update_scene(d,camera=cam);canvas.paste(Image.fromarray(r.render()),(x,178))
                draw.text((x,132),['固定夹持力度','根据滑移反馈调整夹持'][j],font=font(28,True),fill=[ORANGE,GREEN][j])
                lift=(rows[idx,6]-info['source_height']-.020)*1000
                slip=rows[idx,16]*1000 if t>2.82 else 0
                draw.text((x,775),f'抬升 {lift:.0f} mm     滑移 {slip:.1f} mm     接触力 {rows[idx,10]:.1f} N',font=font(23),fill=WHITE)
                status='抬升未通过守卫，任务终止' if idx==len(q)-1 and not info['success'] else ('已抬升，继续绕障搬运' if lift>70 else '接触与抬升阶段')
                draw.text((x,818),status,font=font(23,True),fill=[ORANGE,GREEN][j])
            draw.text((1670,82),f'{t:04.1f} s',font=font(24),fill=CYAN);writer.append_data(np.asarray(canvas))
            if frame==250:canvas.save(out/'comparison.jpg')
            if frame%125==0:print('comparison',t,'wall',round(time.perf_counter()-started),flush=True)
finally:
    for m,d,r,*_ in trials:r.close()
