"""Same waypoint operator, different allocation policies; no human labels."""
import argparse
import json
from pathlib import Path
import numpy as np
from .follow_benchmark import run as follow_run
from .risk_engine import RiskEngine
from .risk_protocol import configuration

def run(root, policy='dual', scenario='normal', height=.75, seed=9000, noise_mm=6.):
    root = Path(root)
    config = configuration(policy, scenario, height, seed)
    result = follow_run(root, policy='gated', height=height, seed=seed, noise_mm=noise_mm,
        trial_config=config, engine_factory=lambda folder,c: RiskEngine(folder, policy, scenario, height, seed, c))
    rows = [json.loads(line) for line in (root/'risk_control.jsonl').read_text(encoding='utf-8').splitlines()]
    active = [r for r in rows if r['allocation_active']]
    if active:
        result.update(min_edge_margin_mm=min(r['edge_margin_m'] for r in active)*1000,
            min_predicted_edge_margin_mm=min(r['predicted_edge_margin_m'] for r in active)*1000,
            max_grip_risk=max(r['grip'] for r in active), max_payload_risk=max(r['payload'] for r in active),
            mean_grip_risk=float(np.mean([r['grip'] for r in active])),
            mean_payload_risk=float(np.mean([r['payload'] for r in active])),
            arm_offset_max_mm=max(abs(r['arm_offset_m']) for r in active)*1000,
            arm_motion_m=sum(abs(r['arm_relative_m_s'])*.01 for r in active),
            intent_rmse_m_s=float(np.sqrt(np.mean([r['intent_error_m_s']**2 for r in active]))),
            max_sum_relaxation_m_s=max(r['sum_bound_relaxation_m_s'] for r in active),
            max_proximity_override_m_s=max(abs(r.get('proximity_override_m_s',0)) for r in active),
            allocation_p95_ms=float(np.percentile([r['solver_ms'] for r in active],95)))
    result.update(risk_policy=policy, risk_scenario=scenario)
    (root/'benchmark_result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--policy',default='dual')
    parser.add_argument('--scenario',default='normal')
    parser.add_argument('--seed',type=int,default=9000)
    args=parser.parse_args()
    run(**vars(args))
