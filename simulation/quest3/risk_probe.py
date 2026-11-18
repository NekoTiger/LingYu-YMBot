"""Exploratory physical reversal probe with identical scheduled input packets.

No waypoint adaptation and no task-success labels. Frozen controller parameters
are reused. Reports motion tracking along with stability, not stability alone.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
import hashlib
import json
from pathlib import Path
import shutil
import numpy as np
from .risk_engine import RiskEngine
from .risk_protocol import hashes
from .risk_allocation import MotionAllocator
from .test_protocol import sample
from .risk_model import SCENARIOS

def run(args):
    root,policy,seed,offset,half_period=args;root=Path(root)
    SCENARIOS['combined']={**SCENARIOS['combined'],'parcel_offset':[offset,0.]}
    engine=RiskEngine(root,policy=policy,scenario='combined',seed=seed)
    engine.connect('synthetic_transport_test','identical scheduled reversal probe, not a human')
    engine.recorder.meta.update(clock_mode='synthetic_fixed_step',probe=f'reversal cycles, {half_period} s half period, negative first, joystick +/-1; no task completion claim')
    anchor_z=np.mean(engine.observation.hand_positions,axis=0)[2]
    rows=[];clock=engine.started
    try:
        for tick in range(2400):
            t=tick*.01
            z=0. if t<.41 else ((engine.info['grasp_z'] if t<5.94 else .89)-anchor_z)/.8
            trigger=float(t>=3.43)
            stick=[0.,0.]
            pulse_end=10.+(8 if half_period==.6 else 3)*2*half_period
            if 10.<=t<pulse_end:stick[1]=1. if int(round((t-10.)*100)/(half_period*100))%2==0 else -1.
            if tick%2==0:engine.receive(sample(tick,t,squeeze=0 if t<.2 else 1,trigger=trigger,shift=(0,z,0),stick=stick),clock+t)
            engine.step(clock+t)
            if t>=10.:
                state=engine.risk_observer.state
                rows.append(dict(t=t,grip=state.grip,payload=state.payload,edge_mm=state.edge_margin_m*1000,
                    slip_mm=engine.assistance.slip*1000,tilt_deg=float(np.rad2deg(engine.observation.cargo_tilt_rad)),
                    parcel_speed=float(np.linalg.norm(state.parcel_relative_velocity)),
                    base_x=float(engine.d.qpos[0]),tray_x=float(engine.d.body('cargo').xpos[0]),
                    requested=float(-.16*stick[1]),actual_base_command=float(engine.twist[0]),
                    **engine.allocator.snapshot()))
        result=dict(policy=policy,seed=seed,scenario='combined',probe_seconds=14.,
            source='synthetic_transport_test',scope='fixed-input reversal stress probe, not a full task',
            retained_at_end=bool(engine.observation.parcel_retained and engine.risk_observer.state.parcel_support_n>.1),
            both_grasped_at_end=all(n>=2 for n in engine.observation.hand_contacts),
            min_edge_margin_mm=min(r['edge_mm'] for r in rows),max_slip_mm=max(r['slip_mm'] for r in rows),
            max_tilt_deg=max(r['tilt_deg'] for r in rows),max_parcel_speed_m_s=max(r['parcel_speed'] for r in rows),
            object_excursion_mm=float(np.ptp([r['tray_x'] for r in rows])*1000),
            command_rmse_m_s=float(np.sqrt(np.mean([(r['object_command_m_s']-r['requested'])**2 for r in rows]))),
            session=str(root.resolve()))
        (root/'probe_trace.json').write_text(json.dumps(rows),encoding='utf-8')
        (root/'probe_result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        return result
    finally:engine.close()

def suite(root,offset=-.035,half_period=1.8):
    root=Path(root);root.mkdir(parents=True,exist_ok=False)
    protocol=dict(label='exploratory targeted mechanism test, designed after observing conventional-route results',
        source_sha256=hashes(),generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        seeds=[9602,9603],policies=list(MotionAllocator.POLICIES),scenario='combined',parcel_offset_override_m=[offset,0.],half_period_s=half_period,
        input='fixed time schedule, no noise, paired initial model; negative first, +/-0.16 m/s before common guards',
        physical_duration_s=24.,measurement_interval_s=[10.,24.],controller_retuned=False)
    (root/'protocol.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2),encoding='utf-8')
    shutil.copy2(__file__,root/'generator_snapshot.py')
    results=[]
    with ProcessPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(run,(str(root/f'{policy}_{seed}'),policy,seed,offset,half_period)) for seed in protocol['seeds'] for policy in protocol['policies']]
        for future in as_completed(futures):
            result=future.result();results.append(result)
            (root/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
            print('PROBE',len(results),result['policy'],result['seed'],result['retained_at_end'],flush=True)
    assert hashes()==protocol['source_sha256']

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--offset',type=float,default=-.035);p.add_argument('--half-period',type=float,default=1.8);suite(**vars(p.parse_args()))
