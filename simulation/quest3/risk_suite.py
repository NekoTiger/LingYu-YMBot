"""Freeze the protocol before running paired policies; preserve every failure."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import shutil
from pathlib import Path
from .risk_benchmark import run
from .risk_model import SCENARIOS
from .risk_protocol import hashes, VERSION

def job(args):
    root,policy,scenario,seed=args
    return run(root,policy=policy,scenario=scenario,seed=seed)

def suite(root, policies, scenarios, seeds, workers=2, label='development'):
    root=Path(root); root.mkdir(parents=True,exist_ok=False)
    protocol=dict(version=VERSION,label=label,policies=policies,scenarios=scenarios,seeds=seeds,
        scene_parameters=SCENARIOS,source_sha256=hashes(),height=.75,noise_mm=6.,
        input='identical closed-loop waypoint rule and seed; not identical physical trajectories; not human data')
    (root/'protocol.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2),encoding='utf-8')
    simulation=Path(__file__).resolve().parents[1]
    for name in protocol['source_sha256']:
        src=simulation/name
        dst=root/'source_snapshot'/name
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(src,dst)
    jobs=[(str(root/f'{s}_{p}_{seed}'),p,s,seed) for s in scenarios for seed in seeds for p in policies]
    results=[]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures={pool.submit(job,a):a for a in jobs}
        for future in as_completed(futures):
            try: result=future.result()
            except Exception as exc:
                a=futures[future]
                result=dict(outcome='error',reason=repr(exc),session=a[0],risk_policy=a[1],risk_scenario=a[2],seed=a[3])
            results.append(result)
            (root/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
            print('COMPLETED',len(results),'/',len(jobs),result['risk_scenario'],result['risk_policy'],result['outcome'],flush=True)
    if hashes()!=protocol['source_sha256']:
        (root/'SOURCE_CHANGED.txt').write_text('Sources changed during this run. Development only.',encoding='utf-8')
    return results

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--policies',nargs='+',default=['fixed','grip_only','payload_only','dual','slow'])
    p.add_argument('--scenarios',nargs='+',default=list(SCENARIOS));p.add_argument('--seeds',nargs='+',type=int,default=[9000]);p.add_argument('--workers',type=int,default=2);p.add_argument('--label',default='development')
    suite(**vars(p.parse_args()))
