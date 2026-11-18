"""Build a MuJoCo model from the supplied YMBOT URDF without changing the source.

The URDF has rigid hands/wheels. We add explicit research parallel-jaw grippers
and a planar base servo. These are simulation assumptions, not hardware claims.
"""
from pathlib import Path
import xml.etree.ElementTree as ET
import json
import numpy as np
from scipy.spatial.transform import Rotation
import mujoco

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MODEL = HERE / 'models' / 'lingyu.xml'

def vec(v):
    return ' '.join(f'{float(x):.9g}' for x in v)

def quat(rpy):
    q = Rotation.from_euler('xyz', [float(x) for x in rpy.split()]).as_quat()
    return vec(q[[3,0,1,2]])

def build():
    MODEL.parent.mkdir(parents=True, exist_ok=True)
    src = ET.parse(ROOT/'ym_assets/ym/ymbot_d.urdf').getroot()
    root = ET.Element('mujoco', model='LingYu YMBOT simulation')
    ET.SubElement(root,'compiler',angle='radian',balanceinertia='true',fusestatic='false')
    ET.SubElement(root,'option',timestep='0.002',integrator='implicitfast',cone='elliptic',iterations='60',gravity='0 0 -9.81')
    visual=ET.SubElement(root,'visual')
    ET.SubElement(visual,'global',offwidth='1280',offheight='720')
    ET.SubElement(visual,'quality',shadowsize='2048',offsamples='4')
    ET.SubElement(visual,'headlight',ambient='.35 .35 .35',diffuse='.6 .6 .6',specular='.2 .2 .2')
    asset=ET.SubElement(root,'asset')
    ET.SubElement(asset,'texture',name='floor_tex',type='2d',builtin='checker',rgb1='.18 .22 .28',rgb2='.23 .28 .34',width='512',height='512')
    ET.SubElement(asset,'material',name='floor_mat',texture='floor_tex',texrepeat='8 8',reflectance='.12')
    world=ET.SubElement(root,'worldbody')
    ET.SubElement(world,'light',pos='0 -2 4',dir='0 .4 -1',diffuse='.8 .8 .8',castshadow='true')
    ET.SubElement(world,'light',pos='2 3 3',dir='-.3 -.5 -1',diffuse='.5 .5 .5',castshadow='false')
    ET.SubElement(world,'geom',name='floor',type='plane',size='6 6 .1',material='floor_mat')
    base=ET.SubElement(world,'body',name='base_footprint_link',pos='0 0 .065')
    for name,typ,axis in [('base_x','slide','1 0 0'),('base_y','slide','0 1 0'),('base_yaw','hinge','0 0 1')]:
        ET.SubElement(base,'joint',name=name,type=typ,axis=axis,damping='80',armature='1')
    joints=[]
    linkmap={x.get('name'):x for x in src.findall('link')}
    children={}
    for j in src.findall('joint'):
        children.setdefault(j.find('parent').get('link'),[]).append(j)
    def add_link(name,b,world_rotation=np.eye(3)):
        b.set('gravcomp','1')
        link=linkmap[name]
        inert=link.find('inertial')
        if inert is not None:
            mass=float(inert.find('mass').get('value'))
            if mass>0:
                origin=inert.find('origin')
                ii=inert.find('inertia')
                ET.SubElement(b,'inertial',pos=origin.get('xyz','0 0 0'),mass=str(mass),fullinertia=' '.join(ii.get(k) for k in ['ixx','iyy','izz','ixy','ixz','iyz']))
        for v in ([] if name in ['Left_Arm_Link8','Right_Arm_Link8'] else link.findall('visual')):
            mesh=v.find('geometry/mesh')
            if mesh is None: continue
            fname=Path(mesh.get('filename').replace('package://','')).name
            mp=ROOT/'ym_assets/ym/meshes'/fname
            if not mp.exists() or mp.suffix.lower()!='.stl': continue
            mn=name+'_mesh'
            if asset.find(f"mesh[@name='{mn}']") is None:
                ET.SubElement(asset,'mesh',name=mn,file=mp.as_posix())
            color='.78 .82 .86 1'
            if 'Wheel' in name: color='.055 .065 .08 1'
            if 'Arm' in name: color='.82 .86 .89 1'
            if 'Link8' in name and 'Arm' in name: color='.12 .17 .22 1'
            o=v.find('origin')
            ET.SubElement(b,'geom',type='mesh',mesh=mn,rgba=color,contype='0',conaffinity='0',group='1',pos=o.get('xyz','0 0 0') if o is not None else '0 0 0',quat=quat(o.get('rpy','0 0 0')) if o is not None else '1 0 0 0')
        for j in children.get(name,[]):
            child=j.find('child').get('link')
            o=j.find('origin')
            nb=ET.SubElement(b,'body',name=child,pos=o.get('xyz','0 0 0'),quat=quat(o.get('rpy','0 0 0')))
            if j.get('type')!='fixed':
                lim=j.find('limit')
                ET.SubElement(nb,'joint',name=j.get('name'),type='hinge',axis=j.find('axis').get('xyz'),range=lim.get('lower')+' '+lim.get('upper'),damping='4',armature='.04')
                joints.append(j.get('name'))
            add_link(child,nb,world_rotation@Rotation.from_euler('xyz',[float(x) for x in o.get('rpy','0 0 0').split()]).as_matrix())
        if name in ['Left_Arm_Link7','Right_Arm_Link7']:
            side='left' if name.startswith('Left') else 'right'
            # End effector extends along the original wrist's -Z axis.
            adapter=Rotation.from_matrix(world_rotation.T).as_quat()[[3,0,1,2]]
            palm=ET.SubElement(b,'body',name=side+'_gripper',pos='0 0 -.135',quat=vec(adapter),gravcomp='1')
            ET.SubElement(palm,'geom',name=side+'_palm',type='box',size='.04 .025 .018',rgba='.10 .18 .24 1',mass='.12',contype='2',conaffinity='1')
            ET.SubElement(palm,'site',name=side+'_ee',pos='0 0 -.080',size='.008',rgba='0 0 0 0')
            for sign in [-1,1]:
                fn=f'{side}_finger_{sign}'
                fb=ET.SubElement(palm,'body',name=fn,pos=f'{sign*.022} 0 -.057',gravcomp='1')
                ET.SubElement(fb,'joint',name=fn,type='slide',axis=f'{sign} 0 0',range='0 .045',damping='2',armature='.005')
                ET.SubElement(fb,'geom',name=fn+'_pad',type='box',size='.009 .026 .045',rgba='.06 .11 .15 1',mass='.045',friction='2 .02 .002',condim='4',contype='2',conaffinity='1',solref='.006 1')
    add_link('base_footprint_link',base)
    ET.SubElement(base,'geom',name='base_collision',type='box',pos='-.03 0 .11',size='.29 .20 .10',rgba='0 0 0 0',group='3',contype='2',conaffinity='1',mass='0')
    act=ET.SubElement(root,'actuator')
    for n in ['base_x','base_y','base_yaw']:
        ET.SubElement(act,'position',name=n,joint=n,kp='15000',kv='1500',forcerange='-3000 3000')
    for n in joints:
        ET.SubElement(act,'position',name=n,joint=n,kp='1200',kv='65',forcerange='-100 100')
    for side in ['left','right']:
        for sign in [-1,1]:
            n=f'{side}_finger_{sign}'
            ET.SubElement(act,'position',name=n,joint=n,kp='700',kv='12',forcerange='-35 35',ctrlrange='0 .045')
    ET.indent(root)
    ET.ElementTree(root).write(MODEL,encoding='utf-8',xml_declaration=True)
    model=mujoco.MjModel.from_xml_path(str(MODEL))
    data=mujoco.MjData(model)
    mujoco.mj_forward(model,data)
    print('model',model.nq,model.nv,model.nu)
    for s in ['left_ee','right_ee']:
        print(s, data.site(s).xpos, data.site(s).xmat.reshape(3,3))
    report={'nq':model.nq,'nv':model.nv,'nu':model.nu,'source':'ym_assets/ym/ymbot_d.urdf','added':'planar base servos and research parallel-jaw grippers','joint_names':[model.joint(i).name for i in range(model.njnt)]}
    (MODEL.parent/'model_manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return model,data

if __name__=='__main__':
    m,d=build()
    r=mujoco.Renderer(m,720,1280)
    c=mujoco.MjvCamera(); c.lookat[:]=[0,0,.8]; c.distance=2.8; c.azimuth=135; c.elevation=-15
    r.update_scene(d,camera=c)
    from PIL import Image
    Image.fromarray(r.render()).save(HERE/'models'/'initial.png')
    r.close()
