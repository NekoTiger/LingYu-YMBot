from pathlib import Path
import json,numpy as np,mujoco
from model import HERE
out={}
for name in ['dev_075_final','dev_stable03']:
    p=HERE/'outputs'/name;z=np.load(p/'trajectory.npz');meta=json.loads(str(z['metadata']));m=mujoco.MjModel.from_xml_path(str(p/'scene.xml'));q=z['qpos']
    mask=np.array([meta['phases'][i]=='navigate' for i in z['phase']]);out[name]=[]
    for j in [1,2,3]:
        jname='Body_Joint'+str(j);qi=int(m.joint(jname).qposadr[0]);vi=int(m.joint(jname).dofadr[0]);arr=np.rad2deg(q[mask,qi]);ctrl=z['ctrl'];tau=1200*(ctrl[:,m.actuator(jname).id]-q[:,qi])-65*z['qvel'][:,vi]+ctrl[:,m.actuator(jname+'_ff').id]
        out[name].append({'joint':j,'range_deg':np.ptp(arr).item(),'motion_deg':np.abs(np.diff(arr)).sum().item(),'max_requested_torque_Nm':float(np.max(np.abs(tau[mask]))),'sat_fraction':float(np.mean(np.abs(tau[mask])>99))})
print(json.dumps(out,indent=2))
(HERE/'outputs/analysis/paired_sway_development.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
