"""Unit-consistent, sustained success checks shared by online/offline evaluation."""
import numpy as np
from scipy.spatial.transform import Rotation

EVALUATION_VERSION='2.0'

def evaluate(model,info,qpos,qvel,metrics):
    qpos=np.asarray(qpos);qvel=np.asarray(qvel);metrics=np.asarray(metrics)
    j=model.joint('cargo_free');qa=int(j.qposadr[0]);va=int(j.dofadr[0])
    tail=metrics[:,0]>=metrics[-1,0]-1.
    pos=qpos[:,qa:qa+3];goal=np.array([info['x'],info['y']+info['distance']])
    expected=.740 if info['task']=='bimanual' else .750
    xy=np.linalg.norm(pos[:,:2]-goal,axis=1)
    linear=np.linalg.norm(qvel[:,va:va+3],axis=1)
    angular=np.linalg.norm(qvel[:,va+3:va+6],axis=1)
    released=bool(np.all(metrics[tail,6]==0))
    stable=bool(np.max(linear[tail])<.02 and np.max(angular[tail])<.1)
    located=bool(np.all(xy[tail]<.05) and np.all(np.abs(pos[tail,2]-expected)<.035))
    quats=qpos[:,qa+3:qa+7]
    rotations=Rotation.from_quat(quats[:,[1,2,3,0]]).as_matrix()
    upright=bool(np.all(rotations[tail,2,2]>np.cos(np.deg2rad(10))))
    parcel=True
    if info['task']=='bimanual':
        pa=int(model.joint('parcel_free').qposadr[0])
        delta=qpos[:,pa:pa+3]-pos
        local=np.einsum('nij,ni->nj',rotations,delta)
        parcel=bool(np.all(np.abs(local[tail,0])<.09) and np.all(np.abs(local[tail,1])<.34) and np.all((local[tail,2]>.03)&(local[tail,2]<.12)))
    lift=float(pos[:,2].max()-expected)
    grasped=bool(np.count_nonzero((metrics[:,6]>0)&(pos[:,2]>expected+.07))>=50)
    success=bool(lift>.07 and grasped and located and released and stable and upright and parcel)
    return dict(evaluation_version=EVALUATION_VERSION,success=success,placement_error_m=float(xy[-1]),lift_m=lift,
                final_z=float(pos[-1,2]),released=released,stable=stable,parcel_retained=parcel,
                sustained_position=located,upright=upright,grasp_contact_verified=grasped,
                last_second_max_linear_speed_m_s=float(np.max(linear[tail])),
                last_second_max_angular_speed_rad_s=float(np.max(angular[tail])),
                placement_settled_time_s=float(metrics[tail,0][0]) if success else None)

def reevaluate_all():
    import json,csv
    from build_model import HERE
    from scene import make_scene
    root=HERE/'outputs/benchmark';rows=[]
    for path in sorted(root.glob('*_a*_s*')):
        summary=json.loads((path/'summary.json').read_text(encoding='utf-8'))
        trace=np.load(path/'trajectory.npz');info=json.loads(str(trace['metadata']))
        model,_,_=make_scene(info['task'],info['seed'],info['disturbance'])
        met=np.loadtxt(path/'metrics.csv',delimiter=',',skiprows=1)
        summary.update(evaluate(model,info,trace['qpos'],trace['qvel'],met))
        (path/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
        rows.append(summary)
    (root/'results.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    with (root/'results.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=sorted(set().union(*(r.keys() for r in rows))));w.writeheader();w.writerows(rows)
    protocol=json.loads((root/'protocol.json').read_text(encoding='utf-8'))
    protocol.update(evaluation_version=EVALUATION_VERSION,success_rule='lift > 0.07 m; grasp contacts while lifted for >=0.5 s; final 1 s: xy error <0.05 m, z error <0.035 m, no finger contacts, linear speed <0.02 m/s, angular speed <0.1 rad/s, tilt <10 deg; tray retains loose parcel')
    (root/'protocol.json').write_text(json.dumps(protocol,indent=2),encoding='utf-8')
    print(f'Re-evaluated {len(rows)} complete traces with sustained success checks.')

if __name__=='__main__':reevaluate_all()
