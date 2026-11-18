"""Frozen, independent-seed engineering checks for the workspace-follow pilot."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import time

import numpy as np

from .follow_benchmark import run
from .study import source_hashes
from .workspace_follow import WorkspaceFollow


def boundary_probe(root):
    rows = []
    for seed in range(8200, 8216):
        rng = np.random.default_rng(seed)
        # Common 50 Hz signal: remain 5 mm inside the forward threshold for 20 s,
        # then deliberately extend for 2 s. Noise is controlled, not measured Quest noise.
        samples = np.r_[np.full(25, .50), .575+rng.normal(0, .006, 1000), np.full(100, .65), np.full(25, .50)]
        for policy in ('threshold', 'gated'):
            controller = WorkspaceFollow(policy)
            commands = []
            for x in samples:
                commands.extend([controller.update(x, eligible=True) for _ in range(2)])
            values = np.asarray(commands)
            boundary = values[50:2050]
            intentional = values[2050:2250]
            nz = np.flatnonzero(intentional > .001)
            rows.append({'seed': seed, 'policy': policy, 'noise_std_m': .006,
                         'unintended_command_s': float(np.count_nonzero(boundary)*.01),
                         'integrated_unintended_command_m': float(boundary.sum()*.01),
                         'command_onsets': int(np.count_nonzero(np.diff(np.r_[False, boundary>0].astype(int)) == 1)),
                         'intent_onset_delay_s': float(nz[0]*.01) if len(nz) else None,
                         'neutral_first_command_m_s': float(values[2250])})
            if seed == 8200:
                np.savez_compressed(root/f'boundary_{policy}.npz', x=np.repeat(samples, 2), command=values, dt=.01)
    (root/'boundary_results.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')


def suite(root, workers=2, first_seed=7300):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    here = Path(__file__).resolve().parent
    hashes = source_hashes()
    for name in ('follow_benchmark.py', 'follow_suite.py'):
        hashes['quest3/'+name] = hashlib.sha256((here/name).read_bytes()).hexdigest()
    snapshot = root/'source_snapshot'
    snapshot.mkdir()
    for relative in hashes:
        file = here.parent/relative
        target = snapshot/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(file.read_bytes())
    cases = [{'policy': p, 'height': h, 'seed': s, 'noise_mm': 6.}
             for h in (.60, .75) for s in (first_seed, first_seed+1) for p in ('off', 'gated')]
    (root/'protocol.json').write_text(json.dumps({
        'created_unix_s': time.time(), 'source_sha256': hashes, 'cases': cases,
        'data_type': 'synthetic fixed-step engineering validation, not human study',
        'comparison': 'matched physics and arm constraints; controller-specific scripted inputs pursue the same waypoints',
        'primary': ['task_success', 'elapsed_sim_s', 'navigation_max_tilt_deg', 'navigation_max_slip_mm'],
        'command_metric_warning': 'joystick duration is a scripted interface-use metric, not measured human workload',
        'boundary_probe': '16 independent noise seeds; 20s at 5mm inside threshold with 6mm Gaussian noise, then 2s deliberate extension'
    }, indent=2), encoding='utf-8')
    boundary_probe(root)
    results = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        jobs = {}
        for case in cases:
            folder = root/f'{case["policy"]}_{int(case["height"]*100)}_{case["seed"]}'
            jobs[pool.submit(run, folder, **case)] = case
        for future in as_completed(jobs):
            case = jobs[future]
            try:
                result = future.result()
            except Exception as exc:
                result = {**case, 'outcome': 'error', 'reason': repr(exc)}
            results.append(result)
            (root/'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
            print(f'COMPLETED {len(results)}/{len(cases)} {case} {result["outcome"]}', flush=True)
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--first-seed', type=int, default=7300)
    suite(**vars(parser.parse_args()))
