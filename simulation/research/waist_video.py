"""Same-scene, same-clock waist ablation rendered directly from saved states."""
from pathlib import Path
import sys,json,time
import numpy as np,mujoco,imageio.v2 as imageio
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'v2'))
from render import font,BG,WHITE,MUTED,GREEN,ORANGE,CYAN

HERE=Path(__file__).resolve().parent;root=HERE/'outputs';trials=[]
for folder in ['demo_waist_baseline','demo_dynamic']:
    p=root/folder;info=json.loads((p/'summary.json').read_text(encoding='utf-8'));z=np.load(p/'trajectory.npz');q=z['qpos'];v=z['qvel'];rows=z['metrics'];phases=z['phase']
    m=mujoco.MjModel.from_xml_path(str(p/'scene.xml'));d=mujoco.MjData(m);renderer=mujoco.Renderer(m,576,896)
    qi=[int(m.joint('Body_Joint'+str(j)).qposadr[0])for j in [1,2,3]];mask=np.array([info['phases'][p]=='navigate'for p in phases]);first=np.flatnonzero(mask)[0];angles=np.rad2deg(q[:,qi]-q[first,qi]);excursion=float(np.max(np.ptp(np.rad2deg(q[mask][:,qi]),axis=0)))
    trials.append((m,d,renderer,info,q,v,rows,angles,excursion))
out=root/'waist_comparison';out.mkdir(exist_ok=True);start=time.perf_counter()
try:
    with imageio.get_writer(out/'comparison.mp4',fps=25,codec='libx264',quality=8,macro_block_size=None,ffmpeg_params=['-movflags','+faststart'])as writer:
        for frame in range(30*25):
            t=8+frame/25;canvas=Image.new('RGB',(1920,960),BG);draw=ImageDraw.Draw(canvas)
            draw.text((36,25),'身体为什么晃：同条件腰部控制消融',font=font(35,True),fill=WHITE)
            draw.text((36,81),'同一机器人、输入处理与场景，只改变搬运时是否保持腰部姿态 · 验证种子 401',font=font(22),fill=MUTED)
            for j,(m,d,renderer,info,q,v,rows,angles,excursion)in enumerate(trials):
                i=min(round(t*100),len(q)-1);d.qpos[:]=q[i];d.qvel[:]=v[i];mujoco.mj_forward(m,d);x=36+952*j;pose=rows[i,1:4]
                c=mujoco.MjvCamera();c.lookat[:]=np.r_[pose[:2],.82];c.distance=2.55;c.azimuth=225+np.rad2deg(pose[2]);c.elevation=-15
                renderer.update_scene(d,camera=c);canvas.paste(Image.fromarray(renderer.render()),(x,180))
                draw.text((x,133),['腰部持续参与 IK','搬运阶段保持腰部姿态'][j],font=font(27,True),fill=[ORANGE,GREEN][j])
                draw.text((x,775),f'搬运全程最大角度变化范围：{excursion:.2f}°',font=font(25,True),fill=[ORANGE,GREEN][j])
                draw.text((x,817),'腰部三关节相对搬运起点的角度',font=font(18),fill=MUTED)
                for col,color in enumerate([CYAN,ORANGE,GREEN]):
                    points=[(x+(k-800)/3000*880,float(np.clip(875-float(angles[k,col])*1.8,845,915)))for k in range(800,min(i+1,3800),10)]
                    if len(points)>1:draw.line(points,fill=color,width=2)
                draw.line([(x,875),(x+880,875)],fill='#64798c',width=1)
            draw.text((1730,81),f'{t:04.1f} s',font=font(24),fill=CYAN)
            draw.text((36,931),'两侧均为原速物理轨迹的 8–38 s 片段；关节保持通过限矩伺服实现，未锁死物理关节。',font=font(18),fill=MUTED)
            writer.append_data(np.asarray(canvas))
            if frame==375:canvas.save(out/'comparison.jpg')
            if frame%250==0:print('waist',t,'wall',round(time.perf_counter()-start),flush=True)
finally:
    for m,d,r,*_ in trials:r.close()
