from pathlib import Path
import json,shutil

HERE=Path(__file__).resolve().parent;root=HERE/'outputs';validation=root/'validation_r2'
mapping={'demo_dynamic':'tracking_shared_401','demo_low':'tracking_shared_400','demo_waist_baseline':'tracking_shared_free_waist_401'}
for name,trial in mapping.items():
    dest=root/name;source=validation/trial;dest.mkdir(parents=True,exist_ok=True)
    for filename in ['scene.xml','summary.json','trajectory.npz','metrics.csv','input_packets.jsonl']:shutil.copy2(source/filename,dest/filename)
    (dest/'selection.json').write_text(json.dumps({'source':trial,'selection':'First held-out odd seed for high destination, first even seed for low destination; paired waist ablation uses the same seed. Not selected by score.'},indent=2),encoding='utf-8')
    print(dest)
