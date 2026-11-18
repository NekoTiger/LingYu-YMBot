from pathlib import Path
import shutil,json
from model import HERE

root=HERE/'outputs';validation=root/'validation'
mapping={'demo_height':validation/'nominal_0.75_adaptive_200','demo_heavy':validation/'heavy_slippery_0.70_adaptive_201','demo_baseline':validation/'heavy_slippery_0.70_coupled_201'}
for name,source in mapping.items():
    dest=root/name;dest.mkdir(parents=True,exist_ok=True)
    for filename in ['scene.xml','summary.json','trajectory.npz','metrics.csv']:
        shutil.copy2(source/filename,dest/filename)
    (dest/'selection.json').write_text(json.dumps({'source':str(source.relative_to(HERE)),'selection':'normal: first held-out seed; stress comparison: first held-out seed where fixed-force coupling failed; illustrative only, all episodes included in aggregate'},ensure_ascii=False,indent=2),encoding='utf-8')
    print(dest)
