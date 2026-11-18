"""V2: free-floating chassis, driven wheels, passive ball-caster contacts.

Geometry and inertia of the robot come from the original YMBOT conversion.
Wheel radii are checked against supplied STL bounds. Casters are a declared
ball-contact approximation. No planar base actuators or body gravity removal.
"""
from pathlib import Path
import sys,xml.etree.ElementTree as E,json
import numpy as np
import mujoco
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from build_model import MODEL,vec

HERE=Path(__file__).resolve().parent
WHEEL_RADIUS=.085
TRACK=.36

def make_model(scene=True,seed=0,obstacle=True,target_height=.72,load_scale=1.,friction_scale=1.,obstacle_x=-.24):
    rng=np.random.default_rng(seed)
    root=E.parse(MODEL).getroot();world=root.find('worldbody');base=world.find("body[@name='base_footprint_link']");act=root.find('actuator')
    root.set('model','LingYu V2 contact-driven mobile manipulation')
    root.find('option').set('iterations','80')
    root.find('option').set('impratio','10')
    base.set('pos','0 0 .020')
    for j in list(base.findall('joint')):base.remove(j)
    E.SubElement(base,'freejoint',name='chassis_free')
    for b in base.iter('body'):b.set('gravcomp','0')
    for a in act.findall('position'):
        if 'finger' in a.get('name'):a.set('ctrlrange','-.020 .045')
    for a in list(act):
        if a.get('name').startswith('base_'):act.remove(a)
        elif 'finger' not in a.get('name'):
            name=a.get('name');act.remove(a)
            # MuJoCo integrates actuator damping implicitly. Explicit high-gain
            # torque PD is unstable for the small wrist inertias at 2 ms.
            E.SubElement(act,'position',name=name,joint=name,kp='1200',kv='65')
            E.SubElement(act,'motor',name=name+'_ff',joint=name,ctrlrange='-100 100')
            base.find(f".//joint[@name='{name}']").set('actuatorfrcrange','-100 100')
    # Existing drive wheel local Z points towards world -Y.
    for i,side in [(1,'left'),(2,'right')]:
        body=base.find(f".//body[@name='Driving_Wheel_Link{i}']")
        E.SubElement(body,'joint',name=side+'_wheel',type='hinge',axis='0 0 -1',damping='.03',armature='.03')
        E.SubElement(body,'geom',name=side+'_wheel_contact',type='cylinder',size=f'{WHEEL_RADIUS} .026',pos='0 0 -.015',rgba='.06 .075 .09 1',mass='0',contype='2',conaffinity='1',condim='6',friction='1.0 .001 .0001',margin='.0012',solref='.005 1')
        E.SubElement(act,'velocity',name=side+'_wheel',joint=side+'_wheel',kv='20',ctrlrange='-8 8',forcerange='-20 20')
        E.SubElement(body,'geom',type='box',pos=f'{WHEEL_RADIUS*.5} 0 -.044',size='.028 .004 .001',rgba='.18 .65 .75 1',contype='0',conaffinity='0',mass='0')
    # Four low-friction passive point supports, matched to small caster radii.
    for i in [2,4,6,8]:
        body=base.find(f".//body[@name='Driven_Wheel_Link{i}']")
        E.SubElement(body,'geom',name=f'caster_{i}',type='sphere',size='.020',rgba='0 0 0 0',mass='0',group='3',contype='2',conaffinity='1',condim='3',friction='.015 .0001 .00001',priority='2',solref='.005 1')
    # Upper-arm and forearm collision proxies use the URDF link translations.
    for side in ['Left','Right']:
        for idx,child in [(3,4),(5,6),(6,7)]:
            body=base.find(f".//body[@name='{side}_Arm_Link{idx}']")
            cb=body.find(f"body[@name='{side}_Arm_Link{child}']")
            endpoint=np.fromstring(cb.get('pos'),sep=' ')
            if np.linalg.norm(endpoint)>.06:
                E.SubElement(body,'geom',name=f'{side.lower()}_arm_collision_{idx}',type='capsule',fromto='0 0 0 '+vec(endpoint),size='.032',rgba='0 0 0 0',mass='0',group='3',contype='2',conaffinity='1')
    # Better lit, neutral room; floor has no mirror reflection.
    root.find("asset/material[@name='floor_mat']").set('reflectance','0')
    tex=root.find("asset/texture[@name='floor_tex']");tex.set('rgb1','.23 .28 .33');tex.set('rgb2','.27 .32 .37')
    E.SubElement(root.find('asset'),'texture',type='skybox',builtin='gradient',rgb1='.25 .33 .42',rgb2='.08 .12 .18',width='512',height='2048')
    E.SubElement(world,'light',pos='-2 1 4',dir='.3 -.1 -1',diffuse='.5 .5 .5',castshadow='false')
    info={'version':2,'seed':seed,'wheel_radius':WHEEL_RADIUS,'track':TRACK,'base_model':'free_joint_driven_wheels','caster_model':'low_friction_ball_contacts','target_height':target_height,'obstacle':obstacle}
    if scene:
        sx=.40+float(rng.uniform(-.008,.008));sy=float(rng.uniform(-.006,.006));dist=1.8+float(rng.uniform(-.05,.05))
        source_z=.675;mass=float(rng.uniform(.45,.75))*load_scale;friction=float(rng.uniform(.9,1.5))*friction_scale
        # Handle and finger friction are varied together; MuJoCo combines equal
        # priority contact friction using the maximum of the two surfaces.
        for geom in base.iter('geom'):
            if '_pad' in geom.get('name',''):geom.set('friction',f'{friction} .02 .002')
        for name,yy,top in [('source',0,source_z),('destination',dist,target_height)]:
            E.SubElement(world,'geom',name=name+'_top',type='box',pos=vec([.50,yy,top-.025]),size='.18 .44 .025',rgba='.60 .48 .35 1',friction='1 .01 .001')
            for xx in [.37,.63]:
                for y in [-.35,.35]:
                    E.SubElement(world,'geom',name=f'{name}_leg_{xx}_{y}',type='box',pos=vec([xx,yy+y,(top-.05)/2]),size=vec([.022,.022,(top-.05)/2]),rgba='.12 .19 .23 1')
            E.SubElement(world,'geom',name=name+'_zone',type='box',pos=vec([sx,yy,top+.001]),size='.075 .35 .001',rgba=('.1 .56 .66 1' if name=='source' else '.22 .64 .44 1'),contype='0',conaffinity='0')
        cargo=E.SubElement(world,'body',name='cargo',pos=vec([sx,sy,source_z+.021]));E.SubElement(cargo,'freejoint',name='cargo_free')
        E.SubElement(cargo,'geom',name='cargo_main',type='box',size='.09 .34 .02',mass=str(mass),rgba='.08 .49 .61 1',friction=f'{friction} .02 .002',condim='4')
        for side,yy in [('left',.30),('right',-.30)]:
            E.SubElement(cargo,'geom',name='cargo_'+side+'_handle',type='box',pos=f'0 {yy} .052',size='.025 .027 .032',mass='.025',rgba='.05 .20 .25 1',friction=f'{friction} .02 .002',condim='4',solref='.006 1')
        parcel=E.SubElement(world,'body',name='parcel',pos=vec([sx,sy,source_z+.074]));E.SubElement(parcel,'freejoint',name='parcel_free')
        E.SubElement(parcel,'geom',name='parcel_geom',type='box',size='.033 .05 .03',mass='.12',rgba='.97 .63 .19 1',friction='.8 .01 .001')
        # A real central obstruction; route must go around its left side.
        if obstacle:
            E.SubElement(world,'geom',name='aisle_obstacle',type='box',pos=vec([obstacle_x,dist/2,.34]),size='.18 .16 .34',rgba='.80 .46 .18 1',friction='1 .01 .001')
            E.SubElement(world,'geom',name='aisle_obstacle_cap',type='box',pos=vec([obstacle_x,dist/2,.69]),size='.20 .18 .01',rgba='.18 .22 .27 1')
        # Storage backdrop is geometry, not a generated image.
        for yy in [-.75,dist+.75]:
            for zz in [.3,.8,1.3]:
                E.SubElement(world,'geom',type='box',pos=vec([1.15,yy,zz]),size='.24 .28 .025',rgba='.24 .32 .39 1')
            for ox in [-.23,.23]:
                for oy in [-.26,.26]:
                    E.SubElement(world,'geom',type='box',pos=vec([1.15+ox,yy+oy,.66]),size='.014 .014 .66',rgba='.18 .24 .29 1')
            for zz in [.41,.91]:
                E.SubElement(world,'geom',type='box',pos=vec([1.15,yy,zz]),size='.15 .20 .08',rgba='.55 .44 .31 1')
        info.update(x=sx,y=sy,distance=dist,mass=mass,friction=friction,load_scale=load_scale,friction_scale=friction_scale,obstacle_x=obstacle_x,source_height=source_z,grasp_z=source_z+.073,goal=[sx,sy+dist,target_height+.020])
    xml=E.tostring(root,encoding='unicode');m=mujoco.MjModel.from_xml_string(xml);d=mujoco.MjData(m)
    mujoco.mj_forward(m,d)
    return m,d,info,xml

class Servo:
    """Joint gravity feedforward through torque-limited motors, not body lift."""
    def __init__(self,m,d):
        self.m=m;self.qtarget=d.qpos.copy()
        self.motor_ids=np.array([i for i in range(m.nu) if 'Joint' in m.actuator(i).name and not m.actuator(i).name.endswith('_ff')])
        self.ff_ids=np.array([m.actuator(m.actuator(i).name+'_ff').id for i in self.motor_ids])
        self.jids=m.actuator_trnid[self.motor_ids,0];self.qids=m.jnt_qposadr[self.jids];self.vids=m.jnt_dofadr[self.jids]
        self.wheels=[m.actuator(s+'_wheel').id for s in ['left','right']]
        self.fingers=[m.actuator(f'{s}_finger_{i}').id for s in ['left','right'] for i in [-1,1]]
    def apply(self,d):
        d.ctrl[self.motor_ids]=self.qtarget[self.qids]
        d.ctrl[self.ff_ids]=np.clip(d.qfrc_bias[self.vids],-100,100)

if __name__=='__main__':
    m,d,info,xml=make_model(scene=False);servo=Servo(m,d)
    rows=[]
    for i in range(5000):
        t=i*.002
        d.ctrl[servo.wheels]=0 if t<2 else (2 if t<6 else 0)
        servo.apply(d);mujoco.mj_step(m,d)
        if i%500==0: print(t,d.qpos[:7],d.subtree_com[1],flush=True)
        rows.append([t,*d.qpos[:7]])
    out=HERE/'outputs/base_check';out.mkdir(parents=True,exist_ok=True)
    np.savetxt(out/'base.csv',rows,delimiter=',');(out/'model.xml').write_text(xml,encoding='utf-8')
    from PIL import Image
    r=mujoco.Renderer(m,720,1280);cam=mujoco.MjvCamera();cam.lookat[:]=[.5,0,.7];cam.distance=2.8;cam.azimuth=135;cam.elevation=-18
    r.update_scene(d,camera=cam);Image.fromarray(r.render()).save(out/'base.png');r.close()
