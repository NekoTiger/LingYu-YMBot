"""Render saved physics states, with grasp detail and measured telemetry."""
from pathlib import Path
import argparse,json,time
import numpy as np,mujoco,imageio.v2 as imageio
from PIL import Image,ImageDraw,ImageFont

FONT=Path('C:/Windows/Fonts/msyh.ttc');BOLD=Path('C:/Windows/Fonts/msyhbd.ttc')
def font(size,bold=False):return ImageFont.truetype(str(BOLD if bold else FONT),size)
BG='#101c28';PANEL='#1b2c3c';WHITE='#e6edf3';MUTED='#9aafbe';CYAN='#45d5d6';GREEN='#67dda8';ORANGE='#f6bc60'
PHASES={'approach':'对准把手','close':'确认双侧接触','lift':'抬升并检测滑移','navigate':'轮式底盘绕障','align':'目标对准','lower':'检测桌面支撑','release':'松开夹爪','retreat':'双手撤离','verify':'检查稳定与留存'}
METHODS={'uncoupled':'独立双臂','coupled':'双臂耦合 · 固定夹持','grip':'双臂耦合 · 反馈夹持','adaptive':'双臂耦合 · 反馈夹持与限速'}
METHODS.update(stable='分阶段腰部稳定',shared='任务坐标补偿 · 抓持约束 · 接触共享控制',shared_free_waist='消融：解除搬运腰部稳定',shared_no_contact='消融：取消接触目标保持',shared_no_frame='消融：取消任务坐标补偿')

class Film:
    def __init__(self,folder):
        self.root=Path(folder);self.meta=json.loads((self.root/'summary.json').read_text(encoding='utf-8'))
        self.m=mujoco.MjModel.from_xml_path(str(self.root/'scene.xml'));self.d=mujoco.MjData(self.m)
        z=np.load(self.root/'trajectory.npz');self.q=z['qpos'];self.v=z['qvel'];self.rows=z['metrics'];self.phase=z['phase'];self.ctrl=z['ctrl']
        held=np.array([self.meta['phases'][p] in ['lift','navigate','align','lower'] for p in self.phase])
        self.rows[~held,16]=0 # separation after release is not gripper slip
        self.waist=np.zeros(len(self.q));nav=np.array([self.meta['phases'][p]=='navigate' for p in self.phase])
        if np.any(nav):
            qi=[int(self.m.joint('Body_Joint'+str(j)).qposadr[0]) for j in [1,2,3]]
            first=np.flatnonzero(nav)[0];self.waist[nav]=np.max(np.abs(np.rad2deg(self.q[nav][:,qi]-self.q[first,qi])),axis=1)
        self.main=mujoco.Renderer(self.m,720,1280);self.detail=mujoco.Renderer(self.m,306,544)
        self.last=len(self.q)-1
    def close(self):self.main.close();self.detail.close()
    def frame(self,i):
        i=min(i,self.last);self.d.qpos[:]=self.q[i];self.d.qvel[:]=self.v[i];self.d.ctrl[:]=self.ctrl[i];mujoco.mj_forward(self.m,self.d)
        r=self.rows[i];t=r[0];name=self.meta['phases'][self.phase[i]];canvas=Image.new('RGB',(1920,1080),BG);draw=ImageDraw.Draw(canvas)
        research=self.meta.get('version',2)>=3
        draw.text((32,24),'灵驭  /  '+('共享控制与动态避障' if research else '轮式双臂协调搬运'),font=font(36,True),fill=WHITE)
        draw.text((34,78),METHODS[self.meta['method']],font=font(23),fill=CYAN)
        total=self.meta['mass']+.17
        draw.text((1260,28),f"台面 {self.meta['target_height']*100:.0f} cm    载荷 {total:.2f} kg",font=font(23),fill=WHITE)
        subtitle=(f"输入噪声 {self.meta['noise']*1000:.0f} mm  延迟 {self.meta['latency']*1000:.0f} ms  丢包 {self.meta['dropout']*100:.0f}%" if research else f"摩擦系数 {self.meta['friction']:.2f}    随机种子 {self.meta['seed']}")
        draw.text((1260,72),subtitle,font=font(21),fill=MUTED)
        draw.rounded_rectangle((32,124,1888,164),8,fill=PANEL)
        draw.text((48,128),PHASES.get(name,name),font=font(22,True),fill=GREEN)
        if research and name=='navigate' and r[14]<.01:draw.text((480,128),'检测到横穿障碍 · 停车让行',font=font(22,True),fill=ORANGE)
        status='完成并通过检查' if i==self.last and self.meta['success'] else (('终止：'+str(self.meta['failure'])) if i==self.last else f'{t:05.1f} s')
        draw.text((1460,129),status,font=font(21),fill=GREEN if self.meta['success'] else ORANGE)
        cam=mujoco.MjvCamera();cam.lookat[:]=[-.20,self.meta['distance']/2,.72];cam.distance=4.25;cam.azimuth=180;cam.elevation=-26
        self.main.update_scene(self.d,camera=cam);canvas.paste(Image.fromarray(self.main.render()),(32,180))
        cc=mujoco.MjvCamera();cc.lookat[:]=self.d.body('cargo').xpos+[0,0,.065];cc.distance=1.02;cc.azimuth=180+np.rad2deg(r[3]);cc.elevation=-28
        self.detail.update_scene(self.d,camera=cc);canvas.paste(Image.fromarray(self.detail.render()),(1344,180))
        draw.rectangle((1344,180,1888,214),fill=PANEL);draw.text((1358,184),'夹持与物件留存',font=font(20,True),fill=WHITE)
        self.map(draw,i)
        draw.text((1350,840),f'双侧接触力  {r[10]:.1f} / {r[11]:.1f} N',font=font(21),fill=WHITE)
        draw.text((1350,874),f'夹持滑移 {r[16]*1000:.1f} mm   腰部变化 {self.waist[i]:.1f}°',font=font(20),fill=CYAN)
        self.spark(draw,i,32,924,400,'托盘倾角',8,180/np.pi,'°',ORANGE)
        self.spark(draw,i,474,924,400,'滑移估计',16,1000,'mm',CYAN)
        self.spark(draw,i,916,924,400,'左 / 右接触力',10,1,'N',GREEN,second=11)
        draw.text((1350,940),'无货物绑定 · 重力与接触动力学',font=font(20),fill=MUTED)
        draw.text((1350,975),'合成遥操作输入 · 仿真理想状态观测' if research else '状态反馈控制 · 仿真理想状态观测',font=font(19),fill=MUTED)
        draw.text((32,1043),'MuJoCo + Mink  |  YMBOT 原始模型  |  本视频由保存的物理轨迹生成，未改变播放速度',font=font(18),fill=MUTED)
        return np.asarray(canvas)
    def map(self,draw,i):
        box=(1344,512,1888,820);draw.rounded_rectangle(box,10,fill=PANEL);draw.text((1358,523),'实际行驶轨迹',font=font(20,True),fill=WHITE)
        minx=-2.3 if self.meta.get('dynamic_obstacle') else -1.35
        def xy(p):return (1375+(p[1]+.52)/(self.meta['distance']+1.04)*475,790-(p[0]-minx)/(.85-minx)*216)
        for yy in [0,self.meta['distance']]:
            a=xy([.68,yy-.44]);b=xy([.32,yy+.44]);draw.rectangle((a[0],a[1],b[0],b[1]),fill='#6d6958')
        if self.meta['obstacle']:
            ox=self.meta['obstacle_x'];yy=self.meta['distance']/2;a=xy([ox+.18,yy-.16]);b=xy([ox-.18,yy+.16]);draw.rectangle((a[0],a[1],b[0],b[1]),fill=ORANGE)
        if self.meta.get('dynamic_obstacle'):
            cx,cy=self.d.body('crossing_cart').xpos[:2];a=xy([cx+.17,cy-.18]);b=xy([cx-.17,cy+.18]);draw.rectangle((a[0],a[1],b[0],b[1]),fill='#df6679')
        points=[xy(row[1:3]) for row in self.rows[:i+1:20]]
        if len(points)>1:draw.line(points,fill=CYAN,width=3)
        r=self.rows[i];center=xy(r[1:3]);draw.ellipse((center[0]-6,center[1]-6,center[0]+6,center[1]+6),fill=WHITE)
        front=xy(r[1:3]+.20*np.array([np.cos(r[3]),np.sin(r[3])]))
        draw.line([center,front],fill=WHITE,width=3)
        draw.text((1360,785),'源台',font=font(17),fill=MUTED);draw.text((1820,785),'目标台',font=font(17),fill=MUTED)
    def spark(self,draw,i,x,y,width,label,col,scale,unit,color,second=None):
        current=self.rows[i,col]*scale;draw.text((x,y),f'{label}  {current:.1f} {unit}',font=font(19),fill=WHITE)
        values=self.rows[:i+1:10,col]*scale;maxv=max(1.,float(np.max(self.rows[:,col]*scale))*1.05)
        def pts(c):return [(x+(k*10)/max(1,self.last)*(width-12),y+100-float(v)/maxv*60) for k,v in enumerate(self.rows[:i+1:10,c]*scale)]
        draw.line([(x,y+100),(x+width-12,y+100)],fill='#344858',width=1)
        points=pts(col)
        if len(points)>1:draw.line(points,fill=color,width=2)
        if second is not None:
            points=pts(second)
            if len(points)>1:draw.line(points,fill='#d8b879',width=2)

def render(folder,out=None,preview=False):
    film=Film(folder);out=Path(out or Path(folder)/'demo.mp4')
    try:
        if preview:
            for sec in [3,8,25,45,52]:Image.fromarray(film.frame(min(sec*100,film.last))).save(Path(folder)/f'preview_{sec}.jpg')
            return
        start=time.perf_counter()
        with imageio.get_writer(out,fps=25,codec='libx264',quality=8,macro_block_size=None,ffmpeg_params=['-pix_fmt','yuv420p','-movflags','+faststart']) as writer:
            for i in range(0,film.last+1,4):
                writer.append_data(film.frame(i))
                if i%1000==0:print(out.name,'t',i/100,'wall',round(time.perf_counter()-start),flush=True)
            final=film.frame(film.last)
            for _ in range(50):writer.append_data(final)
        Image.fromarray(film.frame(min(8*100,film.last))).save(out.with_suffix('.jpg'))
    finally:film.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder');p.add_argument('--out');p.add_argument('--preview',action='store_true');a=p.parse_args();render(**vars(a))
