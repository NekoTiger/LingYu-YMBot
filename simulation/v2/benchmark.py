"""Frozen validation matrix; seeds 200..207 were not used during development."""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
import json,contextlib,time,hashlib
from experiment import run,HERE

def worker(job):
    out=Path(job['out']);out.mkdir(parents=True,exist_ok=True)
    with (out/'run.log').open('w',encoding='utf-8') as log,contextlib.redirect_stdout(log):
        return run(**job)

def main():
    root=HERE/'outputs/validation';root.mkdir(parents=True,exist_ok=True)
    jobs=[]
    for condition,heights,load,friction,push in [('nominal',[.55,.70,.75],1.,1.,0.),('heavy_slippery',[.70],2.5,.35,8.)]:
        for height in heights:
            for seed in range(200,208):
                for method in ['uncoupled','coupled','grip','adaptive']:
                    jobs.append(dict(seed=seed,method=method,target_height=height,load_scale=load,friction_scale=friction,push=push,obstacle_x=-.16-.02*(seed%5),out=str(root/f'{condition}_{height:.2f}_{method}_{seed}')))
    protocol={'development_seeds':[0,1],'validation_seeds':list(range(200,208)),'episodes':len(jobs),'model_sha256':hashlib.sha256((HERE/'model.py').read_bytes()).hexdigest(),'controller_sha256':hashlib.sha256((HERE/'experiment.py').read_bytes()).hexdigest(),'jobs':jobs}
    (root/'protocol.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2),encoding='utf-8')
    results=[];started=time.perf_counter()
    with ProcessPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(worker,j):j for j in jobs}
        for future in as_completed(futures):
            r=future.result();results.append(r)
            print(f"{len(results)}/{len(jobs)} {Path(futures[future]['out']).name}: {r['success']} {r['failure']}",flush=True)
    (root/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print('wall_seconds',time.perf_counter()-started,flush=True)

if __name__=='__main__':main()
