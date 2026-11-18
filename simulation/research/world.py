"""A crossing cart with physical slide dynamics; cargo is always free."""
from pathlib import Path
import sys,xml.etree.ElementTree as E
import numpy as np,mujoco
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'v2'))
from model import make_model as original_model,Servo,WHEEL_RADIUS,TRACK
HERE=Path(__file__).resolve().parent

def make_model(scene=True,seed=0,obstacle=True,target_height=.70,load_scale=1.,friction_scale=1.,obstacle_x=-.24,dynamic=False):
    m,d,info,xml=original_model(scene,seed,obstacle,target_height,load_scale,friction_scale,obstacle_x)
    info.update(dynamic_obstacle=dynamic,version=3)
    if dynamic:
        root=E.fromstring(xml);world=root.find('worldbody');body=E.SubElement(world,'body',name='crossing_cart',pos=f"-.65 {info['distance']/2} .45")
        E.SubElement(body,'joint',name='cart_slide',type='slide',axis='1 0 0',range='-1.4 0',damping='10')
        E.SubElement(body,'geom',name='dynamic_cart',type='box',size='.17 .18 .45',mass='18',rgba='.72 .18 .29 1',friction='.8 .01 .001')
        E.SubElement(body,'geom',name='dynamic_cart_top',type='box',pos='0 0 .46',size='.19 .20 .01',mass='.2',rgba='.22 .23 .27 1')
        E.SubElement(root.find('actuator'),'position',name='cart_drive',joint='cart_slide',kp='1500',kv='150',forcerange='-100 100',ctrlrange='-1.4 0')
        xml=E.tostring(root,encoding='unicode');m=mujoco.MjModel.from_xml_string(xml);d=mujoco.MjData(m);mujoco.mj_forward(m,d)
    return m,d,info,xml

def cart_update(m,d,elapsed):
    # Scripted environment motion, independent of the robot controller.
    target=-np.clip(.19*max(0,elapsed-1.5),0,1.4)
    d.ctrl[m.actuator('cart_drive').id]=target

def collision_gate(m,d,pose,velocity):
    cart=d.body('crossing_cart').xpos[:2];cv=d.qvel[int(m.joint('cart_slide').dofadr[0])]
    # Axis-aligned swept boxes during the straight aisle segment. Conservative
    # base+payload envelope; predict 2 seconds with measured obstacle velocity.
    forward=np.array([np.cos(pose[2]),np.sin(pose[2])]);v=max(.12,abs(velocity))
    for dt in np.linspace(0,2,21):
        future_robot=pose[:2]+v*dt*forward;future_cart=cart+np.array([cv*dt,0])
        # The tray is wider and extends farther forward than the mobile base.
        if abs(future_robot[0]-future_cart[0])<.57 and abs(future_robot[1]-future_cart[1])<.78:return 0.
    return 1.
