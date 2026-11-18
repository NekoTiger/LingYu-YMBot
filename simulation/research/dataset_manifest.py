from pathlib import Path
import json,hashlib,numpy as np
HERE=Path(__file__).resolve().parent;root=HERE/'outputs/validation_r2'
results=json.loads((root/'results.json').read_text(encoding='utf-8'));entries=[]
for r in sorted(results,key=lambda x:x['trial_name']):
    p=root/r['trial_name'];entries.append({'episode':r['trial_name'],'seed':r['seed'],'method':r['method'],'success':r['success'],'failure':r['failure'],'steps':r['steps'],'trajectory_sha256':hashlib.sha256((p/'trajectory.npz').read_bytes()).hexdigest(),'input_sha256':hashlib.sha256((p/'input_packets.jsonl').read_bytes()).hexdigest()})
manifest={'source':'synthetic tracking packets and feedback-controlled MuJoCo simulation','human_demonstrations':False,'hardware_verified':False,'physics_dt_s':.002,'control_dt_s':.01,'tracking_dt_s':.02,'time_convention':{'metrics_time':'control-cycle start, before the five physics steps','qpos_qvel':'state at metrics.time + 0.01 s','ctrl':'final command used within that cycle; gravity feedforward updated each physics step','targets':'nominal task intention at cycle start, not noisy delivered packet','input_packets':'capture timestamp; input packet contains sensor poses only; gripper actions are separately stored in targets[:,15] and ctrl'},'units':{'qpos':'MuJoCo joint coordinates, SI, quaternion wxyz','qvel':'MuJoCo generalized velocity, SI','base_twist':'m/s and rad/s','hand_targets':'m and 3x3 rotation','negative_aperture_command':'bounded preload request to the servo, not negative physical jaw opening'},'episodes':entries}
(HERE/'outputs/dataset_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
reference=np.load(HERE/'outputs/demo_dynamic/trajectory.npz');rerun=np.load(HERE/'outputs/acceptance_verify/trajectory.npz')
comparison={'same_shape':reference['qpos'].shape==rerun['qpos'].shape,'max_qpos_difference':float(np.max(np.abs(reference['qpos']-rerun['qpos']))),'max_qvel_difference':float(np.max(np.abs(reference['qvel']-rerun['qvel']))),'source':'same CLI command and seed as selected held-out demonstration'}
(HERE/'outputs/determinism.json').write_text(json.dumps(comparison,indent=2),encoding='utf-8');print(comparison)
if not comparison['same_shape']or comparison['max_qpos_difference']>1e-8:raise SystemExit(1)
