"""Final artifact/data checks. Does not alter or discard any trial."""
from pathlib import Path
import json,re,urllib.parse
import numpy as np
import imageio.v2 as imageio
from build_model import HERE

def main():
    report={'trial_count':0,'frames_per_trial':4300,'issues':[],'videos':[]}
    for root in [HERE/'outputs/benchmark',HERE/'outputs/ablation']:
        for p in root.rglob('summary.json'):
            s=json.loads(p.read_text(encoding='utf-8'));report['trial_count']+=1
            if s.get('evaluation_version')!='2.0':report['issues'].append(str(p)+': evaluation version')
            with np.load(p.parent/'trajectory.npz') as z:
                for key in ['qpos','qvel','ctrl','hand_targets','hand_actual','time']:
                    a=z[key]
                    if len(a)!=4300 or not np.isfinite(a).all():report['issues'].append(str(p)+': '+key)
                if not np.allclose(np.diff(z['time']),.01,atol=1e-8):report['issues'].append(str(p)+': clock')
    if report['trial_count']!=384:report['issues'].append('Expected 384 trials')
    for rel in ['bimanual_demo/demo.mp4','single_demo/demo.mp4','comparison/comparison.mp4']:
        p=HERE/'outputs'/rel
        with imageio.get_reader(p) as reader:
            meta=reader.get_meta_data();n=reader.count_frames()
            for i in [0,n//4,n//2,3*n//4,n-1]:
                a=reader.get_data(i)
                if a.std()<5:report['issues'].append(str(p)+': blank frame')
            report['videos'].append({'path':rel,'frames':n,'fps':meta['fps'],'duration':meta['duration'],'size':meta['size']})
            if n!=1075 or abs(meta['duration']-43)>.05:report['issues'].append(str(p)+': duration')
    page=(HERE/'验收.html').read_text(encoding='utf-8')
    for ref in re.findall(r'(?:src|href|poster)="([^"]+)"',page):
        if not ref.startswith(('#','http')) and not (HERE/urllib.parse.unquote(ref)).exists():report['issues'].append('Missing page resource: '+ref)
    a=np.load(HERE/'outputs/benchmark/bimanual_coordinated_a18_s00/trajectory.npz')['qpos']
    b=np.load(HERE/'dev/repro_check/trajectory.npz')['qpos']
    report['reproduction_max_qpos_difference']=float(np.max(np.abs(a-b)))
    if report['reproduction_max_qpos_difference']>1e-9:report['issues'].append('Deterministic replay mismatch')
    report['output_bytes']=sum(p.stat().st_size for p in (HERE/'outputs').rglob('*') if p.is_file())
    (HERE/'outputs/verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if report['issues']:raise SystemExit(1)

if __name__=='__main__':main()
