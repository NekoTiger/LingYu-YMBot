"""Contact-coupling ablation plus previously unused validation seeds.

Controller weights are fixed before validation seeds 100..111 are run.
Development uses existing seeds 0..11, retaining earlier two-method trials.
"""
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import json,csv,time
from run import run
from build_model import HERE

def trial(spec):
    split,mode,seed,amp=spec
    out=HERE/'outputs/ablation'/split/f'bimanual_{mode}_a{round(amp*1000):02d}_s{seed:03d}'
    r=run('bimanual',mode,seed,amp,False,out,True);r['split']=split
    return r

def main():
    root=HERE/'outputs/ablation';root.mkdir(exist_ok=True)
    specs=[('development','coupled',seed,amp) for amp in [0,.018,.035,.05] for seed in range(12)]
    specs += [('validation',method,seed,amp) for amp in [0,.018,.035,.05] for seed in range(100,112) for method in ['independent','coordinated','coupled']]
    protocol={'controller_fixed_before_validation':True,'relative_position_cost':50,'relative_orientation_cost':10,'development_seeds':list(range(12)),'validation_seeds':list(range(100,112)),'amplitudes_m':[0,.018,.035,.05],'new_trials':len(specs),'evaluation_version':'2.0','other_parameters_unchanged':True}
    (root/'protocol.json').write_text(json.dumps(protocol,indent=2),encoding='utf-8')
    results=[];started=time.perf_counter()
    with ProcessPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(trial,s):s for s in specs}
        for f in as_completed(futures):
            r=f.result();results.append(r)
            (root/'results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
            print(f'PROGRESS {len(results)}/{len(specs)} elapsed={time.perf_counter()-started:.1f}s',flush=True)
    with (root/'results.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=sorted(set().union(*(r.keys() for r in results))));w.writeheader();w.writerows(results)
    print('COMPLETE',flush=True)

if __name__=='__main__':main()
