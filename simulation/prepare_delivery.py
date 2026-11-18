"""Collect representative trials (fixed a priori seed 0) and provenance."""
from pathlib import Path
import shutil,json,hashlib,sys,subprocess
from build_model import HERE,ROOT
from teleop import export_npz

def main():
    selections=[('ablation/development/bimanual_coupled_a35_s000','bimanual_demo'),('benchmark/single_coordinated_a18_s00','single_demo'),('benchmark/bimanual_independent_a35_s00','baseline_demo')]
    for src,dest in selections:
        source=HERE/'outputs'/src;target=HERE/'outputs'/dest;target.mkdir(exist_ok=True)
        for f in ['summary.json','metrics.csv','trajectory.npz']:shutil.copyfile(source/f,target/f)
        export_npz(target/'trajectory.npz',target/'hand_targets.jsonl')
    req=subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True)
    (HERE/'requirements-lock.txt').write_text(req,encoding='utf-8')
    files=list(HERE.glob('*.py'))+[ROOT/'ym_assets/ym/ymbot_d.urdf',HERE/'models/lingyu.xml']
    hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    (HERE/'outputs/provenance.json').write_text(json.dumps({'python':sys.version,'source_hashes':hashes,'demo_seed':0,'demo_amplitudes_m':{'single':.018,'bimanual':.035},'demo_split':'development; independent validation statistics are separate','timestamp_timezone':'Asia/Shanghai','date':'2026-11-15'},indent=2),encoding='utf-8')
    print('Prepared representative trials and source hashes.')

if __name__=='__main__':main()
