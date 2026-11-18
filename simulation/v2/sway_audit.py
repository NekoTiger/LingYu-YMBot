from pathlib import Path
import sys,json
import numpy as np,mujoco
from scipy.signal import butter,sosfiltfilt
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scene import make_scene
from model import HERE

results=[]
for version,folder in [('v1',HERE.parent/'outputs/bimanual_demo'),('v2',HERE/'outputs/demo_height')]:
    z=np.load(folder/'trajectory.npz');q=z['qpos'];v=z['qvel'];info=json.loads(str(z['metadata']))
    if version=='v1':m,d,_=make_scene(info['task'],info['seed'],info['disturbance']);mask=(z['time']>5.5)&(z['time']<38.5)
    else:m=mujoco.MjModel.from_xml_path(str(folder/'scene.xml'));d=mujoco.MjData(m);mask=np.array([info['phases'][p]=='navigate' for p in z['phase']])
    row={'version':version,'trunk':{}}
    for name in ['Body_Joint1','Body_Joint2','Body_Joint3']:
        joint=m.joint(name);a=np.rad2deg(q[:,int(joint.qposadr[0])]);speed=np.rad2deg(v[:,int(joint.dofadr[0])]);hp=sosfiltfilt(butter(3,2.,fs=100,output='sos',btype='highpass'),a)
        row['trunk'][name]={'range_deg':np.ptp(a[mask]).item(),'rms_speed_deg_s':np.sqrt(np.mean(speed[mask]**2)).item(),'highpass_2hz_rms_deg':np.sqrt(np.mean(hp[mask]**2)).item(),'total_motion_deg':np.sum(np.abs(np.diff(a[mask]))).item()}
    results.append(row)
out=HERE/'outputs/analysis/sway_audit.json';out.write_text(json.dumps(results,indent=2),encoding='utf-8');print(json.dumps(results,indent=2))
