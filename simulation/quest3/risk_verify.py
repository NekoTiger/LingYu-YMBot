"""Post-run evidence checks: freeze, real contact friction, loss replay, latency."""
import argparse
import json
from pathlib import Path
import tempfile
import time
from dataclasses import fields
import mujoco
import numpy as np
from .risk_protocol import hashes,configuration
from .risk_allocation import ContactRisk,MotionAllocator
from .risk_engine import RiskEngine
from .trial import observe

def verify(root):
    root=Path(root)
    protocol=json.loads((root/'protocol.json').read_text(encoding='utf-8'))
    assert hashes()==protocol['source_sha256'],'Source changed after freeze'
    results=json.loads((root/'results.json').read_text(encoding='utf-8'))
    expected={(s,p,n) for s in protocol['scenarios'] for p in protocol['policies'] for n in protocol['seeds']}
    actual={(r['risk_scenario'],r['risk_policy'],r['seed']) for r in results}
    assert actual==expected and len(results)==len(expected),'Incomplete or duplicate runs'
    assert all(r['source_sha256']==protocol['source_sha256'] for r in results),'Mixed versions'
    assert all(r['source']=='synthetic_transport_test' for r in results)
    checks={'frozen_sources_match':True,'trials':len(results),'unique_paired_conditions':len(actual),'contact_friction':{}}
    for scenario in protocol['scenarios']:
        trial=next(r for r in results if r['risk_scenario']==scenario and r['risk_policy']=='dual' and r['seed']==min(protocol['seeds']))
        session=Path(trial['session']);model=mujoco.MjModel.from_xml_path(str(session/'scene.xml'));data=mujoco.MjData(model)
        with np.load(session/'states_0000.npz') as a:
            i=int(np.searchsorted(a['sim_time'],14.));data.qpos[:]=a['qpos'][i];data.qvel[:]=a['qvel'][i];data.ctrl[:]=a['ctrl'][i]
        mujoco.mj_forward(model,data)
        pairs={}
        for c in data.contact:
            names=[model.geom(c.geom1).name or '',model.geom(c.geom2).name or '']
            if any(n.startswith('cargo_') for n in names) and any(n.endswith('_pad') or n=='parcel_geom' for n in names):
                pairs[' + '.join(sorted(names))]=float(c.friction[0])
        settings=protocol['scene_parameters'][scenario]
        assert pairs,'No contact pairs found at carried state'
        handle=[mu for pair,mu in pairs.items() if '_handle' in pair]
        surface=[mu for pair,mu in pairs.items() if 'parcel_geom' in pair]
        assert handle and all(abs(mu-settings['grip_mu'])<1e-9 for mu in handle)
        assert surface and all(abs(mu-settings['surface_mu'])<1e-9 for mu in surface)
        checks['contact_friction'][scenario]=pairs
    # Replay an actual earlier failure to test the new outcome detector. This is
    # a regression replay, NOT another policy performance trial.
    old=Path(__file__).parent/'outputs/risk_dev2/payload_dual_9001'
    with tempfile.TemporaryDirectory() as temporary:
        engine=RiskEngine(Path(temporary)/'loss_replay',trial_config=configuration())
        try:
            engine.connect('synthetic_transport_test','saved failure detector regression')
            engine.trial.start(engine,0.);engine.trial.grasped=engine.trial.lifted=True
            engine.assistance.grasped=True
            with np.load(old/'states_0000.npz') as a:
                for i,t in enumerate(a['sim_time']):
                    if t<7.:continue
                    engine.d.qpos[:]=a['qpos'][i];engine.d.qvel[:]=a['qvel'][i];engine.d.ctrl[:]=a['ctrl'][i];engine.d.time=t
                    mujoco.mj_forward(engine.m,engine.d);engine.observation=observe(engine.m,engine.d)
                    engine.after_observe(float(t))
                    if engine.trial.result:break
            assert engine.trial.result and engine.trial.result['reason']=='parcel_left_tray'
            checks['loss_detection_replay']={'source':str(old.resolve()),'detected_sim_s':engine.trial.result['elapsed_sim_s'],
                'scope':'regression replay of saved states; not a new physical policy trial'}
        finally:engine.close()
    # Timing excludes rendering, observer, network, IK and physics. It cannot be
    # called end-to-end latency. Use recorded observations at 100 Hz.
    session=Path(next(r['session'] for r in results if r['risk_scenario']=='combined' and r['risk_policy']=='dual' and r['seed']==min(protocol['seeds'])))
    rows=[json.loads(line) for line in (session/'risk_control.jsonl').read_text(encoding='utf-8').splitlines()]
    alloc=MotionAllocator('dual');cost=[]
    for r in rows:
        if not r['allocation_active']:continue
        state=ContactRisk(**{f.name:r[f.name] for f in fields(ContactRisk)})
        start=time.perf_counter();alloc.allocate(r['requested_m_s'],state);cost.append((time.perf_counter()-start)*1000)
    checks['isolated_allocator_replay_ms']={'n':len(cost),'median':float(np.median(cost)),'p95':float(np.percentile(cost,95)),'max':max(cost),
        'scope':'allocator only; not full loop or VR latency'}
    (root/'evidence_checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(checks,ensure_ascii=False,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root');verify(parser.parse_args().root)
