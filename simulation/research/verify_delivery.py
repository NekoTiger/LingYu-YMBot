from pathlib import Path
import json,re,subprocess
import numpy as np
import imageio.v2 as imageio,imageio_ffmpeg

HERE=Path(__file__).resolve().parent;SIM=HERE.parent
files=[HERE/'outputs/demo_dynamic/demo.mp4',HERE/'outputs/demo_low/demo.mp4',HERE/'outputs/waist_comparison/comparison.mp4',SIM/'v2/outputs/comparison/comparison.mp4',SIM/'v2/outputs/demo_heavy/demo.mp4']
report={'videos':[],'missing_page_assets':[],'issues':[]}
for p in files:
    reader=imageio.get_reader(p);meta=reader.get_meta_data();frames=reader.count_frames();reader.close()
    result=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-i',str(p),'-f','null','-'],capture_output=True)
    entry={'file':str(p.relative_to(SIM)),'frames':frames,'fps':meta['fps'],'duration':meta['duration'],'size':meta['size'],'bytes':p.stat().st_size,'decode_returncode':result.returncode}
    report['videos'].append(entry)
    if result.returncode or result.stderr.strip():report['issues'].append({'file':str(p),'decode_error':result.stderr.decode(errors='replace')[:1000]})
    if frames<400 or meta['fps']!=25:report['issues'].append('bad video length/fps: '+str(p))
    print(entry,flush=True)
page=(SIM/'验收.html').read_text(encoding='utf-8')
for attr,target in re.findall(r'(src|href|poster)="([^"]+)"',page):
    if target.startswith(('http:','https:','#')):continue
    if not (SIM/target).exists():report['missing_page_assets'].append(target)
if report['missing_page_assets']:report['issues'].append('missing page resources')
report['page_visual_qa']='Static references verified; browser visual QA not performed.'
(HERE/'outputs/delivery_verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2));raise SystemExit(1 if report['issues']else 0)
