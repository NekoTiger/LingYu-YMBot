"""Aggregate prospective formal trials with participants as the independent units."""
import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np

from .study import PROTOCOL


def analyze(root):
    records = [json.loads(path.read_text(encoding='utf-8')) for path in root.glob('*/trial_result.json')]
    formal = [r for r in records if r['phase'] == 'formal' and r['source'] == 'webxr_live'
              and r.get('sources_seen') == ['webxr_live']]
    ignored = len(records) - len(formal)
    protocols = {r.get('protocol_sha256') for r in formal}
    keys = Counter((r['participant'], r['index']) for r in formal)
    duplicate = [list(key) for key, count in keys.items() if count > 1]
    issues = []
    if len(protocols) > 1 or (formal and None in protocols):
        issues.append('正式试次的冻结协议不一致，请逐条核对。')
    if duplicate:
        issues.append('存在重复正式试次，已保留全部记录。请核对首次尝试及重复原因后再分析。')
    if issues:
        result = {'issues': issues, 'duplicate_trials': duplicate, 'formal_records': formal}
    else:
        participants = []
        for participant in PROTOCOL['participants']:
            rows = [r for r in formal if r['participant'] == participant]
            summary = {'participant': participant, 'completed': len(rows), 'expected': 8, 'modes': {}}
            for mode in ('baseline', 'assisted'):
                runs = [r for r in rows if r['mode'] == mode]
                if not runs:
                    continue
                successes = sum(r['outcome'] == 'success' for r in runs)
                elapsed = sum(r['elapsed_wall_s'] for r in runs)
                capped = [r['elapsed_wall_s'] if r['outcome'] == 'success' else r['time_limit_s'] for r in runs]
                summary['modes'][mode] = {'trials': len(runs), 'successes': successes,
                    'success_rate': successes/len(runs), 'mean_capped_time_s': float(np.mean(capped)),
                    'successes_per_600s_trial_time': successes*600/elapsed if elapsed else 0.,
                    'mean_clutch_calibrations': float(np.mean([r['clutch_calibrations'] for r in runs])),
                    'tracking_loss_wall_s': sum(r['tracking_loss_wall_s'] for r in runs)}
            participants.append(summary)
        complete = [p for p in participants if p['completed'] == 8 and all(p['modes'].get(m, {}).get('trials') == 4 for m in ('baseline', 'assisted'))]
        paired = [{'participant': p['participant'],
                   'success_rate_difference': p['modes']['assisted']['success_rate']-p['modes']['baseline']['success_rate'],
                   'capped_time_difference_s': p['modes']['assisted']['mean_capped_time_s']-p['modes']['baseline']['mean_capped_time_s']}
                  for p in complete]
        result = {'formal_trials': len(formal), 'expected_trials': 40, 'excluded_pilot_or_nonlive_records': ignored,
                  'independent_participants_complete': len(complete), 'participants': participants,
                  'paired_differences': paired, 'records': formal,
                  'interpretation': '5 planned independent participants, 8 repeated trials per participant; no automatic statistical significance claim'}
    out = root/'analysis'
    out.mkdir(parents=True, exist_ok=True)
    (out/'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# 真人对照实验汇总', '', f'已读取 {len(formal)} 次正式 WebXR 试次，计划 40 次。另有 {ignored} 次试跑或其他来源记录。', '']
    if issues:
        lines.extend(issues)
    else:
        lines += ['|操作者|标准模式成功/次数|辅助模式成功/次数|完成试次|', '|---|---:|---:|---:|']
        for p in result['participants']:
            cells = []
            for mode in ('baseline', 'assisted'):
                item = p['modes'].get(mode)
                cells.append(f"{item['successes']}/{item['trials']}" if item else '待采集')
            lines.append(f"|{p['participant']}|{cells[0]}|{cells[1]}|{p['completed']}/8|")
        lines += ['', '按操作者配对比较。失败试次在限时耗时指标中计为完整时限。',
                  '每 10 分钟效率使用试次计时窗口，含失败与超时，排除练习、休息和装载场景时间。',
                  '正式结果需核对录像、追踪中断和失败原因，再决定结论。']
    (out/'结果.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(out/'结果.md')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path, nargs='?', default=Path(__file__).resolve().parent/'study_sessions')
    analyze(**vars(parser.parse_args()))
