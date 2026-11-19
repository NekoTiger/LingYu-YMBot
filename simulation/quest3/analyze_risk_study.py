"""Aggregate formal two-contact risk trials, participants as independent units."""
import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np

from .risk_study import RISK_PROTOCOL, schedule, SEEDS


def analyze(root):
    root = Path(root)
    records = [json.loads(path.read_text(encoding='utf-8')) for path in root.glob('*/trial_result.json')]
    formal = [r for r in records if r.get('phase') == 'formal' and r.get('source') == 'webxr_live'
              and r.get('sources_seen') == ['webxr_live']]
    ignored = len(records) - len(formal)
    lock_path = Path(__file__).resolve().parent / 'risk_lock.json'
    locked = json.loads(lock_path.read_text(encoding='utf-8'))
    locked_protocol_sha = hashlib.sha256(lock_path.read_bytes()).hexdigest()
    issues = []
    protocols = {r.get('protocol_sha256') for r in formal}
    if len(protocols) > 1 or protocols != {locked_protocol_sha}:
        issues.append('正式试次的冻结协议哈希不一致，请逐条核对。')
    for r in formal:
        if r.get('source_sha256') != locked['source_sha256']:
            issues.append(f"{r['participant']}/{r['index']} 的源码哈希与冻结版本不一致。")
            break
    expected = {(p, i) for p in RISK_PROTOCOL['participants'] for i in range(1, 9)}
    covered = {(r['participant'], r['index']) for r in formal}
    missing = sorted(expected - covered)
    if missing:
        issues.append('缺少正式试次：' + '、'.join(f'{p}/{i}' for p, i in missing))
    for r in formal:
        condition = schedule(r['participant'])[r['index'] - 1]
        model_scene = RISK_PROTOCOL['scene_models'][condition['scene']]
        expected_seed = SEEDS[condition['scene']] + 10 * (condition['repeat'] - 1)
        if r.get('risk_policy') != condition['policy'] or r.get('risk_scenario') != model_scene:
            issues.append(f"{r['participant']}/{r['index']} 的方法或场景与冻结排程不符。")
        if r.get('seed') != expected_seed:
            issues.append(f"{r['participant']}/{r['index']} 的种子与冻结排程不符。")
    seen = Counter((r['participant'], r['index']) for r in formal)
    retried = sorted((p, i) for (p, i), count in seen.items() if count > 1)
    attempts = []
    for key in sorted(expected):
        group = [r for r in formal if (r['participant'], r['index']) == key]
        order = sorted(group, key=lambda r: Path(r['session']).name)
        primary, repeats = order[0], order[1:]
        attempts.append({
            'participant': key[0], 'index': key[1],
            'policy': primary['risk_policy'], 'scene': primary['risk_scenario'],
            'seed': primary['seed'], 'attempt': 1, 'primary': True,
            'outcome': primary['outcome'], 'reason': primary['reason'],
            'elapsed_wall_s': primary['elapsed_wall_s'],
            'time_limit_s': primary['time_limit_s']})
        for attempt, record in enumerate(repeats, 2):
            attempts.append({
                'participant': key[0], 'index': key[1],
                'policy': record['risk_policy'], 'scene': record['risk_scenario'],
                'seed': record['seed'], 'attempt': attempt, 'primary': False,
                'outcome': record['outcome'], 'reason': record['reason'],
                'elapsed_wall_s': record['elapsed_wall_s'],
                'time_limit_s': record['time_limit_s']})

    def capped(row):
        return row['elapsed_wall_s'] if row['outcome'] == 'success' else row['time_limit_s']

    participants = []
    for participant in RISK_PROTOCOL['participants']:
        rows = [a for a in attempts if a['participant'] == participant]
        primaries = [a for a in rows if a['primary']]
        repeats = [a for a in rows if not a['primary']]
        conditions = {}
        for policy in ('fixed', 'dual'):
            for scene in ('normal', 'combined'):
                runs = [a for a in primaries if a['policy'] == policy and a['scene'] == scene]
                if not runs:
                    continue
                conditions[f'{policy}/{scene}'] = {
                    'trials': len(runs),
                    'successes': sum(a['outcome'] == 'success' for a in runs)}
        elapsed = sum(a['elapsed_wall_s'] for a in rows)
        primary_successes = sum(a['outcome'] == 'success' for a in primaries)
        all_successes = sum(a['outcome'] == 'success' for a in rows)
        participants.append({
            'participant': participant, 'completed': len(primaries), 'expected': 8,
            'primary_successes': primary_successes,
            'primary_rate': primary_successes / len(primaries),
            'attempts': len(rows), 'retries': len(repeats),
            'all_successes': all_successes,
            'mean_capped_time_s': float(np.mean([capped(a) for a in primaries])),
            'primary_successes_per_600s': primary_successes * 600 / elapsed if elapsed else 0.,
            'all_successes_per_600s': all_successes * 600 / elapsed if elapsed else 0.,
            'conditions': conditions})
    primary_rows = [a for a in attempts if a['primary']]
    result = {
        'formal_first_attempts': len(primary_rows), 'expected_trials': 40,
        'formal_attempts_total': len(attempts), 'retried_trials': len(retried),
        'excluded_pilot_or_nonlive_records': ignored, 'issues': issues,
        'locked_protocol_sha256': locked_protocol_sha,
        'participants': participants, 'retried_trials_list': retried, 'attempts': attempts}
    out = root / 'analysis'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    with (out / 'trials.csv').open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=['participant', 'index', 'attempt', 'primary', 'policy', 'scene',
                                                  'seed', 'outcome', 'reason', 'elapsed_wall_s', 'capped_s'])
        writer.writeheader()
        for row in sorted(attempts, key=lambda r: (r['participant'], r['index'], r['attempt'])):
            writer.writerow({key: row.get(key) for key in writer.fieldnames if key != 'capped_s'}
                            | {'capped_s': capped(row)})
    lines = ['# 双层风险正式采集汇总', '',
             f"已读取 {len(primary_rows)} 个首次正式试次，计划 40 个；含重试共 {len(attempts)} 次正式尝试。"
             f"另有 {ignored} 次试跑或其他来源记录。", '']
    if issues:
        lines += ['## 一致性核验问题'] + [f'- {issue}' for issue in issues] + ['']
    else:
        lines += ['## 一致性核验', '',
                  '- 全部正式试次的冻结协议哈希一致，且与 `risk_lock.json` 一致。',
                  '- 全部正式试次的方法、场景与种子符合冻结排程；源码哈希一致。', '']
    lines += ['## 每名被试（首次尝试口径）', '',
              '|被试|完成|固定/正常|固定/低摩擦|双层/正常|双层/低摩擦|首次成功|首次成功率|尝试数(含重试)|全部成功|平均限时耗时/s|', '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for p in participants:
        cells = []
        for key in ('fixed/normal', 'fixed/combined', 'dual/normal', 'dual/combined'):
            item = p['conditions'].get(key)
            cells.append(f"{item['successes']}/{item['trials']}" if item else '—')
        lines.append(f"|{p['participant']}|{p['completed']}/8|" + '|'.join(cells) +
                     f"|{p['primary_successes']}|{p['primary_rate']:.2%}|{p['attempts']}|{p['all_successes']}|"
                     f"{p['mean_capped_time_s']:.1f}|")
    lines += ['', '按首次尝试计成功与耗时；失败按完整时限计入平均限时耗时。', '']
    if retried:
        lines += ['## 重试明细', '', '|被试|试次|方法/场景|重试结果|', '|---|---|---|---|']
        for participant, index in retried:
            rows = [a for a in attempts if a['participant'] == participant and a['index'] == index]
            primary, repeats = rows[0], rows[1:]
            first = '成功' if primary['outcome'] == 'success' else '失败'
            later = '、'.join('成功' if a['outcome'] == 'success' else '失败' for a in repeats)
            lines.append(f"|{participant}|{index}|{primary['policy']}/{primary['scene']}|首次 {first}；重试 {later}|")
        lines += ['', '重试同样计时并自动判定，正式口径需团队统一决定后写入报告。', '']
    lines += ['', '效率口径：成功次数 / 每 600 秒计时试次（含失败与超时，排除练习、场景装载与休息）。',
              '本汇总不声明统计显著性；5 名被试无法完全均衡顺序，报告时说明实际安排。']
    (out / '结果.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return out / '结果.md'


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path, nargs='?', default=Path(__file__).resolve().parent / 'risk_sessions')
    print(analyze(**vars(parser.parse_args())))
