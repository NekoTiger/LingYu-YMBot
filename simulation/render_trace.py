"""Render recorded physics states; never re-simulate or modify the evidence."""
import argparse,json
from pathlib import Path
import numpy as np
import mujoco
import imageio.v2 as imageio
from PIL import Image,ImageDraw,ImageFont
from scene import make_scene
from run import overlay,reference

def load(path):
    path=Path(path)
    with np.load(path/'trajectory.npz') as archive:
        traj={k:archive[k] for k in ['qpos','qvel','time','metadata']}
    info=json.loads(str(traj['metadata']))
    summary=json.loads((path/'summary.json').read_text(encoding='utf-8'))
    m,d,_=make_scene(info['task'],info['seed'],info['disturbance'])
    cam=mujoco.MjvCamera();cam.lookat[:]=[-.02,info['distance']/2,.82];cam.distance=3.95;cam.azimuth=145;cam.elevation=-23
    rend=mujoco.Renderer(m,720,1280)
    metrics=np.loadtxt(path/'metrics.csv',delimiter=',',skiprows=1)
    return path,traj,info,summary,m,d,cam,rend,metrics

def frame(state,i):
    path,traj,info,s,m,d,cam,rend,met=state
    d.qpos[:]=traj['qpos'][i];d.qvel[:]=traj['qvel'][i];d.time=float(traj['time'][i]);mujoco.mj_forward(m,d)
    rend.update_scene(d,camera=cam)
    phase=reference(d.time,info)[-1]
    return overlay(rend.render(),info,s['mode'],d.time,phase,met[i,1],met[i,4],int(met[i,6]))

def main():
    p=argparse.ArgumentParser();p.add_argument('path');p.add_argument('--compare');p.add_argument('--output');a=p.parse_args()
    one=load(a.path);two=load(a.compare) if a.compare else None
    output=Path(a.output) if a.output else Path(a.path)/'demo.mp4';output.parent.mkdir(parents=True,exist_ok=True)
    writer=imageio.get_writer(output,fps=25,codec='libx264',quality=8,macro_block_size=None)
    snaps={0,4,8,17,24,33,38,42}
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',28);small=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',21)
    try:
        for i in range(0,len(one[1]['time']),4):
            t=float(one[1]['time'][i]);a1=frame(one,i)
            if two:
                a2=frame(two,i);im=Image.new('RGB',(1920,800),(14,23,34));dr=ImageDraw.Draw(im)
                dr.text((30,20),'灵驭  |  相同任务与扰动下的协调控制对照',font=font,fill='white')
                dr.text((1250,26),'同一随机种子 · 物理仿真原始轨迹 · 1 倍速',font=small,fill=(177,196,214))
                im.paste(Image.fromarray(a1).resize((960,540)),(0,70));im.paste(Image.fromarray(a2).resize((960,540)),(960,70))
                for s,x,color in [(one,25,(245,174,91)),(two,985,(78,220,175))]:
                    met=s[8];err=met[:i+1,1]*1000; w=910;h=100
                    dr.text((x,624),f"末端误差 {met[i,1]*1000:.1f} mm   |   物体高度 {met[i,4]:.3f} m",font=small,fill=color)
                    dr.line((x,770,x+w,770),fill=(70,89,108),width=1)
                    pts=[(x+j/(len(met)-1)*w,770-min(float(v),100)/100*h) for j,v in enumerate(err)]
                    if len(pts)>1:dr.line(pts,fill=color,width=2)
                    dr.text((x,775),'0',font=small,fill=(141,163,180))
                out_frame=np.asarray(im)
            else:out_frame=a1
            writer.append_data(out_frame)
            sec=round(t)
            if sec in snaps and abs(sec-t)<.02:
                Image.fromarray(out_frame).save(output.parent/f'frame_{sec:02d}.png');snaps.remove(sec)
    finally:
        writer.close();one[7].close()
        if two:two[7].close()
    print(output,flush=True)

if __name__=='__main__':main()
