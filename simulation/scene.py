from pathlib import Path
import xml.etree.ElementTree as E
import numpy as np
import mujoco
from build_model import MODEL,vec

def make_scene(task='bimanual',seed=0,disturbance=.0):
    rng=np.random.default_rng(seed)
    root=E.parse(MODEL).getroot(); world=root.find('worldbody')
    # Same paired seeds across methods. Small spatial/mass/friction variations.
    x=.40+float(rng.uniform(-.008,.008)); y=float(rng.uniform(-.006,.006))
    distance=1.50+float(rng.uniform(-.03,.03))
    friction=float(rng.uniform(1.2,1.7))
    mass=float(rng.uniform(.45,.65) if task=='bimanual' else rng.uniform(.10,.18))
    for name,yy in [('source',0),('destination',distance)]:
        E.SubElement(world,'geom',name=name+'_top',type='box',pos=f'.50 {yy} .69',size='.18 .44 .03',rgba='.53 .36 .22 1',friction='1 .01 .001')
        for xx in [.37,.63]:
            for oy in [-.35,.35]:
                E.SubElement(world,'geom',name=f'{name}_leg_{xx}_{oy}',type='box',pos=vec([xx,yy+oy,.33]),size='.022 .022 .33',rgba='.13 .18 .22 1')
        E.SubElement(world,'geom',name=name+'_zone',type='box',pos=f'{x} {yy} .721',size='.07 .35 .0008',rgba=('.10 .65 .78 .65' if name=='source' else '.2 .8 .45 .65'),contype='0',conaffinity='0')
    # Aisle line segments, visual only.
    for yy in np.linspace(-.4,distance+.4,15):
        E.SubElement(world,'geom',type='box',pos=f'-.53 {yy} .001',size='.006 .035 .001',rgba='.85 .68 .20 1',contype='0',conaffinity='0')
    if task=='bimanual':
        cargo=E.SubElement(world,'body',name='cargo',pos=vec([x,y,.741]))
        E.SubElement(cargo,'freejoint',name='cargo_free')
        E.SubElement(cargo,'geom',name='cargo_main',type='box',size='.09 .34 .020',mass=str(mass),rgba='.08 .53 .64 1',friction=f'{friction} .02 .002',condim='4')
        for side,yy in [('left',.30),('right',-.30)]:
            E.SubElement(cargo,'geom',name='cargo_'+side+'_handle',type='box',pos=f'0 {yy} .052',size='.025 .027 .032',mass='.025',rgba='.04 .20 .27 1',friction=f'{friction} .02 .002',condim='4',solref='.006 1')
        # Loose, dynamic parcel tests whether contents remain on the tray.
        parcel=E.SubElement(world,'body',name='parcel',pos=vec([x,y,.794]))
        E.SubElement(parcel,'freejoint',name='parcel_free')
        E.SubElement(parcel,'geom',name='parcel_geom',type='box',size='.033 .05 .03',mass='.08',rgba='.95 .59 .16 1',friction='.9 .01 .001')
        grasp_z=.793
    else:
        y+=.28
        cargo=E.SubElement(world,'body',name='cargo',pos=vec([x,y,.751]))
        E.SubElement(cargo,'freejoint',name='cargo_free')
        E.SubElement(cargo,'geom',name='cargo_main',type='box',size='.025 .028 .030',mass=str(mass),rgba='.95 .59 .16 1',friction=f'{friction} .02 .002',condim='4',solref='.006 1')
        grasp_z=.755
    info=dict(task=task,seed=seed,x=x,y=y,distance=distance,mass=mass,friction=friction,grasp_z=grasp_z,disturbance=disturbance)
    model=mujoco.MjModel.from_xml_string(E.tostring(root,encoding='unicode'))
    return model,mujoco.MjData(model),info
