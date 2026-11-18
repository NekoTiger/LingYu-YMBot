"""Frozen factorial/ablation protocol for moving-obstacle teleoperation."""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
import json,contextlib,hashlib,shutil,time
from research_runner import run,HERE

def worker(job):
    out=Path(job['out']);out.mkdir(parents=True,exist_ok=True)
    with (out/'run.log').open('w',encoding='utf-8') as f,contextlib.redirect_stdout(f):return run(**job)

def main():
    root=HERE/'outputs/validation';root.mkdir(parents=True,exist_ok=True);jobs=[]
    methods=['adaptive','stable','shared_free_waist','shared_no_contact','shared_no_frame','shared']
    for condition,noise,latency,dropout,ms,safety in [('clean',0.,0.,0.,methods,True),('tracking',.006,.08,.1,methods,True),('severe',.012,.16,.2,['adaptive','shared'],True),('without_safety',.006,.08,.1,['shared'],False)]:
        for seed in range(300,308):
            for method in ms:
                jobs.append(dict(seed=seed,method=method,dynamic=True,target_height=.55 if seed%2==0 else .75,noise=noise,latency=latency,dropout=dropout,safety=safety,out=str(root/f'{condition}_{method}_{seed}')))
    snapshot=root/'code_snapshot';snapshot.mkdir(exist_ok=True);hashes={}
    sources=[HERE/'research_runner.py',HERE/'world.py',HERE/'input_channel.py',HERE/'benchmark.py',HERE.parent/'v2/stable_control.py',HERE.parent/'v2/model.py',HERE.parent/'control.py']
    for source in sources:
        dest=snapshot/source.name;shutil.copy2(source,dest);hashes[str(source.relative_to(HERE.parent))]=hashlib.sha256(source.read_bytes()).hexdigest()
    protocol={'development_seeds':[0,1],'validation_seeds':list(range(300,308)),'num_episodes':len(jobs),'sha256':hashes,'trials':jobs,'tracking_source':'synthetic 50Hz independent hand Gaussian position noise + Gaussian angle noise + fixed latency + Bernoulli packet loss','observation':'perfect simulator robot/object/obstacle state; no hardware or perception validation','rule':'Do not change controller or remove failed seeds after this protocol is written. New development requires a separate validation version.'}
    (root/'protocol.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2),encoding='utf-8');results=[];start=time.perf_counter()
    with ProcessPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(worker,j):j for j in jobs}
        for future in as_completed(futures):
            result=future.result();result['trial_name']=Path(futures[future]['out']).name;results.append(result)
            print(f"{len(results)}/{len(jobs)} {result['trial_name']}: {result['success']} {result['failure']}",flush=True)
    (root/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8');print('wall_seconds',time.perf_counter()-start,flush=True)

if __name__=='__main__':main()
