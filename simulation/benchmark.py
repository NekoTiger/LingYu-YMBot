"""Paired factorial evaluation; each trial writes raw metrics, including failures."""
import argparse,json,csv,os,time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
from run import run
from build_model import HERE

def trial(spec):
    task,mode,seed,amp,out=spec
    dest=Path(out)/f'{task}_{mode}_a{round(amp*1000):02d}_s{seed:02d}'
    return run(task,mode,seed,amp,False,dest,True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--seeds',type=int,default=12);p.add_argument('--workers',type=int,default=2);p.add_argument('--out',default=str(HERE/'outputs'/'benchmark'));a=p.parse_args()
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    specs=[(task,mode,s,amp,str(out)) for task in ['single','bimanual'] for amp in [0,.018,.035,.05] for s in range(a.seeds) for mode in ['independent','coordinated']]
    manifest={'seeds':list(range(a.seeds)),'disturbance_m':[0,.018,.035,.05],'tasks':['single','bimanual'],'methods':['independent','coordinated'],'trials':len(specs),'success_rule':'lift > 7 cm; placement xy error < 5 cm; table height +/- 3.5 cm; fingers released; speed norm < 0.1; tray retains loose parcel','trajectory_source':'synthetic','identical_paired_conditions':True}
    (out/'protocol.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    results=[];started=time.perf_counter()
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        futures={pool.submit(trial,s):s for s in specs}
        for future in as_completed(futures):
            spec=futures[future]
            try: result=future.result()
            except Exception as exc:
                result={'task':spec[0],'mode':spec[1],'seed':spec[2],'disturbance':spec[3],'success':False,'error':repr(exc)}
            results.append(result)
            (out/'results.json').write_text(json.dumps(results,indent=2,ensure_ascii=False),encoding='utf-8')
            print(f'PROGRESS {len(results)}/{len(specs)} elapsed={time.perf_counter()-started:.1f}s',flush=True)
    fields=sorted(set().union(*(r.keys() for r in results)))
    with (out/'results.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(results)
    errors=[r for r in results if 'error' in r]
    print(f'COMPLETE trials={len(results)} runtime_errors={len(errors)}',flush=True)
    if errors: raise SystemExit(1)

if __name__=='__main__': main()
