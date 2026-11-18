"""Independent artifact and physical-state checks, without trusting success flags."""
from pathlib import Path
import argparse,json,hashlib
import numpy as np,mujoco

def verify(folder):
    root=Path(folder);protocol=json.loads((root/'protocol.json').read_text(encoding='utf-8'));results=json.loads((root/'results.json').read_text(encoding='utf-8'));issues=[];paired={};checked=0;success_checks=0
    for source,expected in protocol['sha256'].items():
        saved=root/'code_snapshot'/Path(source).name
        if hashlib.sha256(saved.read_bytes()).hexdigest()!=expected:issues.append('snapshot hash: '+source)
    for r in results:
        trial=root/r['trial_name'];z=np.load(trial/'trajectory.npz');q=z['qpos'];v=z['qvel'];u=z['ctrl'];rows=z['metrics']
        if not all(np.all(np.isfinite(x))for x in [q,v,u,rows]):issues.append(r['trial_name']+': nonfinite')
        if len(q)!=r['steps'] or len(v)!=len(q)or len(rows)!=len(q):issues.append(r['trial_name']+': lengths')
        if len(rows)>1 and not np.allclose(np.diff(rows[:,0]),.01,atol=1e-8):issues.append(r['trial_name']+': clock')
        key=(r['seed'],r['noise'],r['latency'],r['dropout'],r['safety']);fingerprint=hashlib.sha256((trial/'scene.xml').read_bytes()).hexdigest()
        if key in paired and paired[key]!=fingerprint:issues.append(r['trial_name']+': unpaired physical scene')
        paired[key]=fingerprint
        m=mujoco.MjModel.from_xml_path(str(trial/'scene.xml'));d=mujoco.MjData(m)
        if m.neq or m.nmocap or np.any(m.body_gravcomp):issues.append(r['trial_name']+': attachment or gravity override')
        if r['success']:
            good=[];joint=m.joint('cargo_free');vid=int(joint.dofadr[0])
            for i in range(max(0,len(q)-100),len(q)):
                d.qpos[:]=q[i];d.qvel[:]=v[i];d.ctrl[:]=u[i];mujoco.mj_forward(m,d)
                cargo=d.body('cargo').xpos;rot=d.body('cargo').xmat.reshape(3,3);offset=rot.T@(d.body('parcel').xpos-cargo)
                hand_contacts=False
                for c in d.contact:
                    names=[m.geom(c.geom1).name,m.geom(c.geom2).name]
                    if any(n.startswith('cargo_')for n in names)and any(n.startswith(('left_finger','right_finger'))for n in names):hand_contacts=True
                good.append(np.linalg.norm(cargo[:2]-np.array(r['goal'][:2]))<.035 and abs(cargo[2]-r['goal'][2])<.01 and np.linalg.norm(d.qvel[vid:vid+3])<.02 and np.linalg.norm(d.qvel[vid+3:vid+6])<.1 and abs(offset[0])<.09 and abs(offset[1])<.34 and .03<offset[2]<.12 and np.arccos(np.clip(rot[2,2],-1,1))<.12 and not hand_contacts)
            if not all(good)or len(good)!=100:issues.append(f"{r['trial_name']}: independent final states {sum(good)}/{len(good)}")
            success_checks+=1
        checked+=1
    report={'episodes':checked,'independent_final_state_checks':success_checks,'paired_scene_groups':len(paired),'protocol_episodes':protocol['num_episodes'],'issues':issues,'note':'100 saved states = final 1 second; scene hashes paired across controllers; snapshots checked independently of current source.'}
    (root.parent/(root.name+'_verification.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False,indent=2))
    if issues:raise SystemExit(1)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder');verify(p.parse_args().folder)
