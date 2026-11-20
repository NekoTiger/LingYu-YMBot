"""Read-only, participant-paired audit of the frozen live risk study.

Run from the project root: python -m simulation.quest3.analyze_risk_final
Raw recordings and the acquisition source/lock are never modified.
"""
import argparse
import base64
from collections import Counter, defaultdict
import hashlib
import html
import itertools
import json
from pathlib import Path
import re

import numpy as np
from scipy.stats import t
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
POLICIES = ('fixed', 'dual')
LABELS = {'fixed': '固定分配', 'dual': '双层联合', 'normal': '正常摩擦', 'combined': '低摩擦复合场景'}
REASONS = {'parcel_left_tray': '物件离开托盘', 'payload_dropped': '载荷掉落',
           'timeout': '超时', 'operator_abort': '操作者终止'}


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def dump(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def capped(r):
    return min(r['elapsed_wall_s'], r['time_limit_s']) if r['outcome'] == 'success' else r['time_limit_s']


def aggregate(rows):
    if not rows:
        return None
    k = sum(r['outcome'] == 'success' for r in rows)
    elapsed = sum(r['elapsed_wall_s'] for r in rows)
    return {'trials': len(rows), 'successes': k, 'success_rate': k / len(rows),
            'mean_capped_time_s': float(np.mean([capped(r) for r in rows])),
            'mean_elapsed_s': elapsed / len(rows), 'elapsed_total_s': elapsed,
            'successes_per_600s': k * 600 / elapsed,
            'mean_success_only_time_s': float(np.mean([r['elapsed_wall_s'] for r in rows if r['outcome'] == 'success'])) if k else None,
            'tracking_loss_s': sum(r['tracking_loss_wall_s'] for r in rows),
            'mean_clutch_calibrations': float(np.mean([r['clutch_calibrations'] for r in rows])),
            'failures': dict(Counter(r['reason'] for r in rows if r['outcome'] != 'success'))}


def paired_stats(differences):
    """Exploratory subject-level sign-flip, not a trial-level independence test."""
    d = np.asarray(differences, dtype=float)
    mean = float(d.mean())
    margin = float(t.ppf(.975, len(d) - 1) * d.std(ddof=1) / np.sqrt(len(d)))
    null = np.asarray([np.mean(d * signs) for signs in itertools.product((-1, 1), repeat=len(d))])
    p = float(np.mean(abs(null) >= abs(mean) - 1e-12))
    return {'n_participants': len(d), 'differences': d.tolist(), 'mean_difference': mean,
            't_interval_95': [mean - margin, mean + margin], 'sign_flip_two_sided_p': p}


def audit(root, lock):
    formal, excluded, issues, manifest = [], [], [], []
    expected_hash = digest(HERE / 'risk_lock.json')
    fields = ('participant', 'index', 'repeat', 'seed', 'risk_policy', 'risk_scenario',
              'target_height', 'time_limit_s', 'protocol_sha256', 'source_sha256')
    def remember(path):
        manifest.append({'path': path.relative_to(PROJECT).as_posix(), 'bytes': path.stat().st_size,
                         'sha256': digest(path)})
    remember(HERE / 'risk_lock.json')
    remember(HERE / 'risk_analysis_notes_20261120.json')
    model_hashes = defaultdict(set)
    for path in sorted(root.glob('*/trial_result.json')):
        r = read(path)
        remember(path)
        if r.get('phase') != 'formal':
            excluded.append({'session': path.parent.name, 'phase': r.get('phase'), 'source': r.get('source')})
            continue
        r = dict(r, session_id=path.parent.name, result_path=path.relative_to(PROJECT).as_posix())
        prefix = f"{r['participant']}/{r['index']} ({r['session_id']})"
        def check(ok, message):
            if not ok:
                issues.append(prefix + ': ' + message)
        check(r.get('source') == 'webxr_live' and r.get('sources_seen') == ['webxr_live'], '非纯 live 来源')
        check(r.get('protocol_sha256') == expected_hash, '协议哈希不符')
        check(r.get('source_sha256') == lock['source_sha256'], '采集源码哈希不符')
        schedule = {c['index']: c for c in lock['schedule'].get(r['participant'], [])}
        c = schedule.get(r['index'])
        check(c is not None, '未知编号或试次')
        if c:
            check(r['risk_policy'] == c['policy'] and r['risk_scenario'] == lock['protocol']['scene_models'][c['scene']]
                  and r['seed'] == c['seed'] and r['repeat'] == c['repeat'], '条件与冻结排程不符')
        check(r['time_limit_s'] == lock['protocol']['time_limit_s'] and r['target_height'] == lock['protocol']['target_height'], '时限或台高不符')
        check(r['elapsed_wall_s'] > 0 and r['elapsed_sim_s'] > 0, '无效耗时')
        check(r['outcome'] in ('success', 'failure'), '未知结果')
        check(r['clock_mode'] == 'live_server_monotonic', '非实时墙钟')
        config = read(path.parent / 'experiment_config.json')
        meta = read(path.parent / 'session.json')
        events = [json.loads(line) for line in (path.parent / 'events.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
        starts = [e for e in events if e['event'] == 'experiment_started']
        finishes = [e for e in events if e['event'] == 'experiment_finished']
        check(len(starts) == len(finishes) == 1, '开始/结束事件不唯一')
        check(all(config.get(k) == r.get(k) == meta['experiment'].get(k) for k in fields), '配置与结果不一致')
        if not starts or not finishes:
            continue
        check(finishes[0]['result'] == read(path), '结束事件与结果不一致')
        r['event_clock_difference_s'] = finishes[0]['wall_unix_s'] - starts[0]['wall_unix_s'] - r['elapsed_wall_s']
        # Events use time.time() at serialization, while scoring receives the control-loop
        # monotonic timestamp. A delayed callback is not evidence of a wrong trial clock.
        check(abs(r['event_clock_difference_s']) < 1., '事件墙钟与计时差异超过1秒，需复核')
        check(starts[0]['wall_unix_s'] >= lock['frozen_unix_s'], '在冻结前开始')
        r['start_unix_s'] = starts[0]['wall_unix_s']
        r['start_sim_s'] = starts[0]['sim_time']
        r['end_sim_s'] = r['start_sim_s'] + r['elapsed_sim_s']
        r['hardware_verified'] = meta.get('hardware_verified')
        r['device_claim_quest3'] = 'Quest 3' in meta.get('device_claim', '')
        r['recorded_packets'] = meta.get('received_packets')
        model_hashes[(r['risk_scenario'], r['seed'])].add(digest(path.parent / 'scene.xml'))
        check(meta.get('received_packets', 0) > 0, '无输入包')
        if r['outcome'] == 'success':
            o, scene = r['final_observation'], meta['scene']
            check(r['grasp_verified'] and r['lift_verified'] and r['max_lift_m'] >= .08, '成功但无抓取/抬升证据')
            check(o['destination_support_n'] > .65 * (scene['mass'] + .17) * 9.81
                  and sum(o['hand_contacts']) == 0 and min(p[2] for p in o['hand_positions']) > r['target_height'] + .12
                  and np.linalg.norm(np.array(o['cargo_position'])[:2] - np.array(scene['goal'])[:2]) < .04
                  and abs(o['cargo_position'][2] - scene['goal'][2]) < .012
                  and o['cargo_linear_speed'] < .02 and o['cargo_angular_speed'] < .1
                  and o['cargo_tilt_rad'] < .12 and o['parcel_retained'], '成功终态未满足物理判据')
            check(r['elapsed_wall_s'] <= r['time_limit_s'] + .1, '成功超过时限')
        for name in ('experiment_config.json', 'session.json', 'events.jsonl', 'raw_webxr.jsonl', 'scene.xml'):
            p = path.parent / name
            check(p.exists() and p.stat().st_size > 0, f'{name} 缺失或为空')
            if p.exists():
                remember(p)
        formal.append(r)
    # Detect started formal trials that never obtained a result.
    unfinished, prepared = [], []
    for path in sorted(root.glob('*/experiment_config.json')):
        if (path.parent / 'trial_result.json').exists() or read(path).get('phase') != 'formal':
            continue
        events = (path.parent / 'events.jsonl').read_text(encoding='utf-8') if (path.parent / 'events.jsonl').exists() else ''
        (unfinished if '"experiment_started"' in events else prepared).append(path.parent.name)
    issues += ['正式试次启动但无结果: ' + s for s in unfinished]
    drift = [k for k, h in lock['source_sha256'].items() if digest(HERE.parent / k) != h]
    issues += ['当前源码与冻结版本不一致: ' + k for k in drift]
    issues += [f'相同场景/种子的模型不一致: {key}' for key, values in model_hashes.items() if len(values) != 1]
    groups = defaultdict(list)
    for r in formal:
        groups[(r['participant'], r['index'])].append(r)
    missing = sorted({(p, c['index']) for p, ss in lock['schedule'].items() for c in ss} - groups.keys())
    issues += [f'缺失正式试次: {p}/{i}' for p, i in missing]
    for group in groups.values():
        group.sort(key=lambda r: (r['start_unix_s'], r['session_id']))
        for index, r in enumerate(group, 1):
            r['attempt'] = index
            r['primary'] = index == 1
    return formal, excluded, issues, manifest, prepared


def trace_audit(root, rows):
    """Read only the trial window, excluding long idle recordings after completion."""
    errors = []
    for index, r in enumerate(rows, 1):
        folder = root / r['session_id']
        times, walls, finite, used = [], [], True, []
        for path in sorted(folder.glob('states_*.npz')):
            with np.load(path, allow_pickle=False) as z:
                ts = z['sim_time']
                if ts[0] > r['end_sim_s'] + 1e-6:
                    break
                mask = (ts > r['start_sim_s'] + 1e-6) & (ts <= r['end_sim_s'] + 1e-6)
                if mask.any():
                    times.extend(ts[mask].tolist())
                    walls.extend(z['wall_elapsed'][mask].tolist())
                    finite &= bool(np.isfinite(z['qpos'][mask]).all() and np.isfinite(z['qvel'][mask]).all())
                    used.append({'file': path.name, 'sha256': digest(path)})
        expected = round(r['elapsed_sim_s'] / .01)
        # Recorder flush precedes the final state append; final frame may appear in the next chunk.
        ok = bool(times) and abs(len(times) - expected) <= 1 and finite and bool(np.allclose(np.diff(times), .01, atol=1e-6))
        if not ok:
            errors.append(r['session_id'] + ': 轨迹帧数/连续性/有限数核验失败')
        risk, allocations = [], []
        with (folder / 'risk_control.jsonl').open(encoding='utf-8') as f:
            for line in f:
                item = json.loads(line)
                if item['sim_time'] > r['end_sim_s'] + 1e-6:
                    break
                if item['sim_time'] > r['start_sim_s'] + 1e-6:
                    risk.append(item)
                    if item.get('allocation_active'):
                        allocations.append(item)
        r['trace_audit'] = {'frames': len(times), 'expected_frames': expected, 'continuous_and_finite': ok,
                            'files': used, 'risk_frames': len(risk), 'allocation_active_sim_s': len(allocations) * .01,
                            'allocation_active_fraction': len(allocations) / len(risk) if risk else None,
                            'max_wall_sample_gap_s': float(np.max(np.diff(walls))) if len(walls) > 1 else None,
                            'sim_to_wall_ratio': r['elapsed_sim_s'] / r['elapsed_wall_s']}
        if len(risk) != expected:
            errors.append(r['session_id'] + ': 风险日志帧数与试次窗口不符')
        if allocations:
            r['trace_audit'].update(mean_grip_risk=float(np.mean([a['grip'] for a in allocations])),
                                     mean_payload_risk=float(np.mean([a['payload'] for a in allocations])))
        print(f'TRACE {index}/{len(rows)} {r["participant"]}/{r["index"]}: {len(times)} frames', flush=True)
    return errors


def figures(out, rows, participants, conditions):
    plt.rcParams.update({'font.family': 'Microsoft YaHei', 'font.size': 12,
                         'axes.spines.top': False, 'axes.spines.right': False, 'axes.unicode_minus': False})
    colors = ['#58758C', '#159789']
    fig, ax = plt.subplots(1, 2, figsize=(12.8, 5.1), layout='constrained')
    for j, scene in enumerate(('normal', 'combined')):
        for i, policy in enumerate(POLICIES):
            a = conditions[f'{policy}/{scene}']
            x = j + (i - .5) * .32
            ax[0].bar(x, a['success_rate'] * 100, .28, color=colors[i], label=LABELS[policy] if j == 0 else None)
            ax[0].text(x, a['success_rate'] * 100 + 2, f"{a['successes']}/{a['trials']}", ha='center')
            ax[1].bar(x, a['mean_capped_time_s'], .28, color=colors[i])
            ax[1].text(x, a['mean_capped_time_s'] + 4, f"{a['mean_capped_time_s']:.1f}", ha='center')
    for a in ax:
        a.set_xticks([0, 1], ['正常摩擦', '低摩擦复合场景'])
        a.grid(axis='y', alpha=.16)
        a.set_axisbelow(True)
    ax[0].set_ylim(0, 119); ax[0].set_ylabel('首次成功率（%）'); ax[0].legend(loc='upper right', fontsize=10)
    ax[1].set_ylim(0, 250); ax[1].set_ylabel('平均限时耗时（秒；失败计 240 秒）')
    fig.suptitle('真人实验：正常场景全部成功，低摩擦场景仍有较多失败', fontsize=18)
    fig.supxlabel('5 位参与者 × 8 个首次试次；各场景每种方法 10 次。柱形为描述统计，不代表 40 个独立样本。', fontsize=10)
    for ext in ('png', 'svg'):
        fig.savefig(out / f'01_正式实验主结果.{ext}', dpi=180)
    plt.close(fig)
    fig, axs = plt.subplots(1, 2, figsize=(12.8, 5.2), layout='constrained')
    for n, p in enumerate(participants):
        for a, metric, scale in [(axs[0], 'success_rate', 100), (axs[1], 'mean_capped_time_s', 1)]:
            ys = [p['policies'][m][metric] * scale for m in POLICIES]
            a.plot([0, 1], ys, '-o', label=p['participant'], alpha=.85, linewidth=1.8)
    for a in axs:
        a.set_xticks([0, 1], ['固定分配', '双层联合']); a.set_xlim(-.18, 1.18); a.grid(axis='y', alpha=.2)
    axs[0].set_ylabel('每人首次成功率（%）'); axs[0].set_ylim(0, 105)
    axs[0].text(.50, 77, 'P03 / P05 重合', ha='center', fontsize=10, color='#66517B')
    axs[1].set_ylabel('每人平均限时耗时（秒）'); axs[1].legend(fontsize=10)
    fig.suptitle('按参与者配对：个体差异较大，方法优势尚未确立', fontsize=18)
    fig.supxlabel('每条线对应 1 位参与者；每种方法 4 个首次试次，失败计 240 秒。', fontsize=11)
    for ext in ('png', 'svg'):
        fig.savefig(out / f'02_参与者配对结果.{ext}', dpi=180)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(10, 4.3), layout='constrained')
    reasons = list(REASONS)
    x = np.arange(len(reasons))
    for i, policy in enumerate(POLICIES):
        counts = Counter(r['reason'] for r in rows if r['risk_policy'] == policy and r['outcome'] != 'success')
        vals = [counts[k] for k in reasons]
        bars = ax.bar(x + (i - .5) * .32, vals, .28, color=colors[i], label=LABELS[policy])
        ax.bar_label(bars)
    ax.set_xticks(x, [REASONS[k] for k in reasons]); ax.set_ylabel('首次失败次数'); ax.set_ylim(0, 7)
    ax.legend(); ax.set_title('13 次首次失败中，10 次被判为物件离开托盘', fontsize=17)
    for ext in ('png', 'svg'):
        fig.savefig(out / f'03_失败原因.{ext}', dpi=180)
    plt.close(fig)


def main(root=None, out=None):
    root = Path(root) if root else HERE / 'risk_sessions'
    out = Path(out) if out else PROJECT / '中期答辩材料' / '实验结果_20261120'
    out.mkdir(parents=True, exist_ok=True)
    lock = read(HERE / 'risk_lock.json')
    note = read(HERE / 'risk_analysis_notes_20261120.json')
    dump(out / '现场补充记录.json', note)
    rows, excluded, issues, manifest, prepared = audit(root, lock)
    primary = sorted([r for r in rows if r['primary']], key=lambda r: (r['participant'], r['index']))
    issues += trace_audit(root, primary)
    anomalies = [{'participant': r['participant'], 'index': r['index'], 'session_id': r['session_id'],
                  'elapsed_wall_s': r['elapsed_wall_s'], 'elapsed_sim_s': r['elapsed_sim_s'],
                  'max_wall_sample_gap_s': r['trace_audit']['max_wall_sample_gap_s'],
                  'cause': 'user confirms human pause/away from device; sampling-gap mechanism not independently diagnosed',
                  'clarification_source': '现场补充记录.json'}
                 for r in primary if r['trace_audit']['max_wall_sample_gap_s'] > 1.]
    dump(out / 'audit.json', {'issues': issues, 'timing_anomalies': anomalies, 'prepared_without_start': prepared, 'excluded': excluded,
                              'formal_attempts': len(rows), 'primary_trials': len(primary),
                              'scope': 'All formal result/config/session/event and input-file hashes; primary trial-window trajectory continuity and risk logs; terminal success predicates. No video review or independent full dynamics re-scoring.'})
    dump(out / 'source_manifest.json', manifest)
    dump(out / 'attempts.json', sorted(rows, key=lambda r: (r['participant'], r['index'], r['attempt'])))
    if issues:
        raise RuntimeError(f'{len(issues)} audit issues: see {out / "audit.json"}')
    participants = []
    for p in lock['protocol']['participants']:
        pr = [r for r in primary if r['participant'] == p]
        participants.append({'participant': p, 'policies': {m: aggregate([r for r in pr if r['risk_policy'] == m]) for m in POLICIES}})
    conditions = {f'{m}/{s}': aggregate([r for r in primary if r['risk_policy'] == m and r['risk_scenario'] == s])
                  for s in ('normal', 'combined') for m in POLICIES}
    overall = {m: aggregate([r for r in primary if r['risk_policy'] == m]) for m in POLICIES}
    comparisons = {metric: paired_stats([p['policies']['dual'][metric] - p['policies']['fixed'][metric] for p in participants])
                   for metric in ('success_rate', 'mean_capped_time_s', 'successes_per_600s')}
    scene_comparisons = {}
    for scene in ('normal', 'combined'):
        scene_comparisons[scene] = {}
        for metric in ('success_rate', 'mean_capped_time_s'):
            diffs = []
            for p in lock['protocol']['participants']:
                a = {m: aggregate([r for r in primary if r['participant'] == p and r['risk_scenario'] == scene and r['risk_policy'] == m]) for m in POLICIES}
                diffs.append(a['dual'][metric] - a['fixed'][metric])
            scene_comparisons[scene][metric] = paired_stats(diffs)
    # Sensitivity definitions do not promote retries to primary observations.
    groups = defaultdict(list)
    for r in rows:
        groups[(r['participant'], r['index'])].append(r)
    last = [max(g, key=lambda r: r['start_unix_s']) for g in groups.values()]
    sensitivity = {label: {m: aggregate([r for r in rr if r['risk_policy'] == m]) for m in POLICIES}
                   for label, rr in [('first_attempt', primary), ('all_attempts_descriptive', rows), ('last_attempt_selection_bias', last)]}
    complete_pairs = []
    for r in primary:
        if r['risk_policy'] != 'fixed':
            continue
        paired = [q for q in primary if q['participant'] == r['participant'] and q['risk_policy'] == 'dual'
                  and q['risk_scenario'] == r['risk_scenario'] and q['repeat'] == r['repeat']]
        if len(paired) == 1 and r['tracking_loss_wall_s'] == paired[0]['tracking_loss_wall_s'] == 0:
            complete_pairs += [r, paired[0]]
    sensitivity['pairs_without_tracking_loss_posthoc'] = {m: aggregate([r for r in complete_pairs if r['risk_policy'] == m]) for m in POLICIES}
    affected = next(r for r in primary if r['session_id'] == note['session_id'])
    uninterrupted = [r for r in primary if not (r['participant'] == affected['participant']
                     and r['risk_scenario'] == affected['risk_scenario'] and r['repeat'] == affected['repeat'])]
    sensitivity['without_human_interrupted_pair_posthoc'] = {m: aggregate([r for r in uninterrupted if r['risk_policy'] == m]) for m in POLICIES}
    result = {'analysis_date_local': '2026-11-20', 'timezone': 'Asia/Shanghai', 'independent_participants': 5,
              'formal_attempts': len(rows), 'primary_trials': len(primary), 'retries': len(rows) - len(primary),
              'retried_slots': sum(len(g) > 1 for g in groups.values()), 'excluded_pilot': len(excluded), 'timing_anomalies': anomalies,
              'overall': overall, 'conditions': conditions, 'participants': participants,
              'cohort_clarification': note['cohort_clarification'],
              'paired_comparisons': comparisons, 'scene_comparisons': scene_comparisons, 'sensitivity': sensitivity,
              'inference': 'Exploratory participant-level t intervals and exact sign flips; no multiplicity correction; fixed counterbalanced order is not random allocation. Small n and unequal retries limit causal claims.'}
    dump(out / 'summary.json', result)
    figures(out, primary, participants, conditions)
    write_report(out, result, rows, primary, groups, prepared)
    write_brief(out, result)
    render_report_html(out)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def write_report(out, result, rows, primary, groups, prepared):
    a, b = result['overall']['fixed'], result['overall']['dual']
    lines = ['# 灵驭：真人双层风险实验分析', '', '分析日期：2026-11-20（北京时间）。数据来源：冻结协议下的 Quest 3 WebXR 真人输入与 MuJoCo 仿真。', '',
             f"5 位参与者完成 40 个正式试次。固定分配首次成功 {a['successes']}/20（{a['success_rate']:.0%}），双层联合 {b['successes']}/20（{b['success_rate']:.0%}）；双层联合增加 1 次成功，但平均限时耗时从 {a['mean_capped_time_s']:.1f} 秒变为 {b['mean_capped_time_s']:.1f} 秒。当前数据未确立双层联合的整体优势。", '',
             '## 分析口径', '',
             f"- 共 {len(rows)} 次正式尝试，其中 40 次首次尝试、{len(rows)-40} 次额外重试；{result['retried_slots']} 个试次有重试。另有 {result['excluded_pilot']} 次试跑，全部排除出正式统计。",
             '- P01–P05均为项目团队成员，此前均未使用过VR；练习约10分钟。以上为负责人于2026-11-20采集后补充的信息，时长为约数，未提供逐人、分方法的计时，也未明确10分钟指合计还是每种方法。',
             '- 每人 2 方法 × 2 场景 × 2 重复；目标台高统一 0.75 m，时限 240 秒。正常/低摩擦分别使用 9000/9001 和 9010/9011 种子，同场景、同重复的方法之间配对。',
             '- 主分析按开始事件时间选择最早尝试；失败、超时、操作者终止及追踪中断均保留。此规则与已有汇总一致，但未在冻结协议中预注册，属于采集后确定的处理规则。',
             '- 限时耗时：成功取 min(真实墙钟耗时, 240)，失败一律计 240 秒。成功试次耗时单独报告，不能代替含失败的主指标。',
             '- 效率：每 600 秒计时窗口的成功次数；包含失败，排除练习、休息、场景加载。主分析只用首次尝试；含重试效率另外报告。',
             '- 独立统计单位是参与者（n=5）。40 个试次和 78 次尝试都不是独立样本量。',
             '- “低摩擦”是复合场景：夹持摩擦系数 1.1→0.55，承载面 0.8→0.16，物件偏置 0→3.5 cm，载荷倍率 1.0→1.15；场景差异不能归因于摩擦单因素。', '',
             '## 主结果', '', '|场景|方法|首次成功|成功率|平均限时耗时/s|成功试次平均耗时/s|每10分钟成功次数|', '|---|---|---:|---:|---:|---:|---:|']
    for s in ('normal', 'combined'):
        for m in POLICIES:
            r = result['conditions'][f'{m}/{s}']
            lines.append(f"|{LABELS[s]}|{LABELS[m]}|{r['successes']}/{r['trials']}|{r['success_rate']:.0%}|{r['mean_capped_time_s']:.2f}|{r['mean_success_only_time_s']:.2f}|{r['successes_per_600s']:.2f}|")
    lines += ['', f"合并场景：固定分配/双层联合的平均限时耗时为 {a['mean_capped_time_s']:.2f}/{b['mean_capped_time_s']:.2f} 秒，计时窗口汇总效率为 {a['successes_per_600s']:.2f}/{b['successes_per_600s']:.2f} 次/10分钟。效率是总成功数除以总时间，不等于先计算每人效率再平均。", '',
              '![主结果](01_正式实验主结果.png)', '', '## 每位参与者的配对结果', '',
              '|参与者|固定成功|双层成功|成功率差/百分点|固定限时耗时/s|双层限时耗时/s|耗时差/s|', '|---|---:|---:|---:|---:|---:|---:|']
    for p in result['participants']:
        f, d = p['policies']['fixed'], p['policies']['dual']
        lines.append(f"|{p['participant']}|{f['successes']}/4|{d['successes']}/4|{100*(d['success_rate']-f['success_rate']):+.0f}|{f['mean_capped_time_s']:.2f}|{d['mean_capped_time_s']:.2f}|{d['mean_capped_time_s']-f['mean_capped_time_s']:+.2f}|")
    lines += ['', '所有差值均为“双层联合 − 固定分配”。正的成功率差有利于双层；正的耗时差表示双层更慢。', '',
              '![配对结果](02_参与者配对结果.png)', '',
              '|探索指标|平均配对差|95% t区间|双侧符号翻转 p|', '|---|---:|---:|---:|']
    for metric, name, scale in [('success_rate', '成功率/百分点', 100), ('mean_capped_time_s', '限时耗时/s', 1), ('successes_per_600s', '每人效率/次每10分钟', 1)]:
        s = result['paired_comparisons'][metric]; lo, hi = s['t_interval_95']
        lines.append(f"|{name}|{s['mean_difference']*scale:+.2f}|[{lo*scale:.2f}, {hi*scale:.2f}]|{s['sign_flip_two_sided_p']:.4f}|")
    lines += ['', '区间按5位参与者的差值计算，依赖小样本正态近似；成功率区间未裁剪。符号翻转枚举2⁵种组合，依赖参与者差值在零假设下可交换符号的假设。冻结顺序为交错排程，并非随机分配；未做多重比较校正。这些数值只作探索，不能把不显著解释为等效，也不能用独立试次检验夸大证据。', '',
              '## 重试与敏感性分析', '', '|口径|固定成功|双层成功|固定限时耗时/s|双层限时耗时/s|固定效率|双层效率|', '|---|---:|---:|---:|---:|---:|---:|']
    names = {'first_attempt': '首次尝试（主分析）', 'all_attempts_descriptive': '全部尝试（描述）',
             'last_attempt_selection_bias': '每试次最后一次（选择偏差示例）', 'pairs_without_tracking_loss_posthoc': '配对双方均无追踪中断（事后敏感性）',
             'without_human_interrupted_pair_posthoc': '剔除人为暂停的整对试次（事后敏感性）'}
    for key, name in names.items():
        f, d = result['sensitivity'][key]['fixed'], result['sensitivity'][key]['dual']
        lines.append(f"|{name}|{f['successes']}/{f['trials']}|{d['successes']}/{d['trials']}|{f['mean_capped_time_s']:.2f}|{d['mean_capped_time_s']:.2f}|{f['successes_per_600s']:.2f}|{d['successes_per_600s']:.2f}|")
    lines += ['', '负责人补充说明：重试的主要原因是操作失误。这是对重试原因的总体回忆，未逐条对应38次额外重试；自动记录的失败类型仍原样保留，不能把每次失败都单独归因为操作者。操作失误属于本任务的人机交互表现，主分析仍保留首次失败。', '',
              '重试并非等量、随机安排；既有失败后重试，也有成功后重试。后续首次试次可能已经受到前面额外练习的影响。首次尝试规则避免直接挑选成功结果，但无法消除整个流程中的学习与顺序影响。全部尝试只用于描述成本，最后一次结果用于展示选择偏差，均不能替代主分析。', '',
              '|参与者/试次|方法/场景|按时间排序的结果（✓成功，×失败）|', '|---|---|---|']
    for (p, i), group in sorted(groups.items()):
        if len(group) > 1:
            group = sorted(group, key=lambda r: r['start_unix_s'])
            lines.append(f"|{p}/{i}|{LABELS[group[0]['risk_policy']]}/{LABELS[group[0]['risk_scenario']]}|{' → '.join('✓' if r['outcome']=='success' else '×' for r in group)}|")
    lines += ['', '## 失败、追踪与机制检查', '', '![失败原因](03_失败原因.png)', '',
              '首次失败共13次：物件离开托盘10次，超时、操作者终止、载荷掉落各1次。自动原因标签定位了失败类型；具体操作原因仍需结合录像，不把原因标签解释为控制算法的唯一因果责任。', '',
              '|参与者/试次|方法/场景|追踪中断/s|结果|', '|---|---|---:|---|']
    for r in primary:
        if r['tracking_loss_wall_s'] > 0:
            lines.append(f"|{r['participant']}/{r['index']}|{LABELS[r['risk_policy']]}/{LABELS[r['risk_scenario']]}|{r['tracking_loss_wall_s']:.2f}|{r['outcome']}|")
    lines += ['', '上述追踪中断均保留在主分析耗时与结果中；“双方无中断”仅是完整配对的事后敏感性分析。追踪状态指标不能覆盖服务进程停顿。', '',
              '### 计时异常', '',
              '|参与者/试次|墙钟耗时/s|仿真耗时/s|最大采样间隔/s|', '|---|---:|---:|---:|']
    for r in result['timing_anomalies']:
        lines.append(f"|{r['participant']}/{r['index']}|{r['elapsed_wall_s']:.2f}|{r['elapsed_sim_s']:.2f}|{r['max_wall_sample_gap_s']:.2f}|")
    lines += ['', 'P01/5出现约451秒采样停顿，超时判定延后到约597秒才写入。用户于2026-11-20确认当时“人为暂停或离开设备”（采集后补充，见现场补充记录.json）；采样停顿的底层机制未独立诊断。主分析保留首次失败，限时耗时计240秒，真实计时效率仍保留597秒。另在事后敏感性分析中剔除 P01/5 和相同场景、重复的双层 P01/6，共2次。不能把仿真143.99秒当成人的真实完成耗时，也不能把包含人为暂停的效率差完全归因于控制方法。', '',
              '按试次窗口读取风险分配日志，以下为启用分配的平均仿真时长，供核对方法确实运行。不同方法和失败截断改变了暴露时长，不据此宣称风险降低。', '',
              '|场景|方法|分配启用时长均值/s|', '|---|---|---:|']
    for s in ('normal', 'combined'):
        for m in POLICIES:
            rr = [r for r in primary if r['risk_policy'] == m and r['risk_scenario'] == s]
            lines.append(f"|{LABELS[s]}|{LABELS[m]}|{np.mean([r['trace_audit']['allocation_active_sim_s'] for r in rr]):.2f}|")
    lines += ['', '## 数据核验与结论边界', '',
              '- 78 次正式尝试的冻结哈希、方法、场景、重复、种子、台高、时限、配置/结果/事件对应关系已核对；当前采集源码与锁定源码一致。',
              '- 40 个首次试次按开始/结束仿真时间截取轨迹，核对状态帧连续性、有限数与记录长度；未把试次结束后长时间空转计入结果。首次试次的风险日志同样仅统计试次窗口。',
              '- 全部正式成功记录的终态支持力、撤手、目标位置、静止与物件留存条件已核对。连续1秒稳定来自冻结判定器记录；本轮未独立重放完整接触动力学，也未完成录像人工复核。',
              '- WebXR来源、输入文件、设备自报信息均留存；`hardware_verified=false` 是现有元数据状态，不能把浏览器声明当成独立硬件验收。真人操作对象仍为仿真机器人，风险状态来自理想仿真量。',
              '- 样本为5位无VR使用经验的团队成员，属于团队内便利样本，可提供小规模可行性和初步比较证据。团队身份可能影响对研究目的的熟悉程度与期望，不能当作独立招募的外部用户样本；也不能由“无VR经验”推断其无机器人或项目知识。',
              '- 参与者背景、约10分钟练习与重试主要因操作失误，均来自负责人采集后的补充说明，见现场补充记录.json。逐人/分方法练习时长、逐次重试原因及录像同意状态仍未取得明确记录。',
              f'- 另有 {len(prepared)} 个准备过但没有开始事件且无结果的正式配置目录，列在 audit.json；不计为试次。',
              '- 已生成源文件SHA-256清单与逐次结果，便于回查；清单覆盖结果/配置/会话/事件/输入/模型，首次窗口NPZ哈希见 attempts.json，不代表对全部空转文件做了完整封存。', '',
              '## 答辩建议表述', '',
              '> 我们邀请了5位此前未使用过VR的项目团队成员，经过约10分钟练习，完成40个正式试次。按首次尝试，固定分配成功率65%，双层联合70%；正常场景两者均全部成功，低摩擦复合场景分别为30%和40%。额外重试主要因操作失误，主分析保留了首次失败。双层联合的平均限时耗时略长，个体差异较大，因此现阶段不能宣称新方法整体优于基线。这项团队内小样本实验验证了完整的人机交互与记录流程，也发现物件离开托盘仍是主要失败类型。下一步将统一重试与练习规则，招募团队外参与者，并在更接近真实传感条件下验证风险分配。', '',
              '可主张：系统已运行、正式数据已采集、分析可追溯、方法局限已定位。尚不可主张：显著提升效率、已证明降低疲劳、真机闭环成功或算法普遍优越。腰部运动范围与离合次数可作辅助描述，不能代替疲劳量表或人体测量。', '',
              '## 复现与文件', '',
              '项目根目录运行 `.\\.venv\\Scripts\\python.exe -X utf8 -m simulation.quest3.analyze_risk_final`。分析脚本只读取原始采集数据，输出到本目录。', '',
              '- summary.json：条件汇总、每人配对、探索统计与敏感性分析。',
              '- attempts.json：78次完整正式结果、来源路径、首次标记及40次轨迹核验。',
              '- audit.json / source_manifest.json：审计结论与源文件哈希。',
              '- 01–03 的 PNG/SVG：答辩插图；PNG可直接使用，SVG便于缩放。']
    (out / '正式实验分析报告.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def write_brief(out, result):
    f, d = result['overall']['fixed'], result['overall']['dual']
    clean = result['sensitivity']['without_human_interrupted_pair_posthoc']
    text = f'''# 答辩结果页与讲稿

## 结果页正文（可放入现有PPT）

标题：真人对照实验完成，双层联合的整体优势尚未确立

- 5位无VR使用经验的团队成员，练习约10分钟；40个正式试次，按首次尝试分析。
- 固定分配成功13/20（65%），双层联合14/20（70%）。
- 平均限时耗时：{f['mean_capped_time_s']:.1f}秒 → {d['mean_capped_time_s']:.1f}秒，失败计240秒。
- 正常摩擦均10/10成功；低摩擦复合场景分别3/10、4/10。

插图：01_正式实验主结果.png。页脚：独立样本n=5；38次额外重试单列，未以重试替换失败。

## 约一分钟结果讲稿

我们邀请了5位此前未使用过VR的团队成员，经过约10分钟练习，每人完成8个正式试次。重试主要因操作失误，分析仍保留首次失败，并按240秒计入耗时。固定分配成功率是65%，双层联合是70%，只多了一次成功；平均限时耗时从145.4秒增加到150.9秒。正常场景两种方法都全部成功，困难集中在低摩擦复合场景。13次首次失败中，有10次是物件离开托盘。目前能够确认系统可以完成真人操作、记录和自动判定，但尚不能确认双层联合整体优于基线。后续将招募团队外参与者、统一练习和重试规则，并改进物件在抬升和搬运中的稳定性。

## 提问准备

**为什么没有显著提高，还算有进展？**

进展包括两接触界面的风险观测和运动分配实现、真实WebXR输入链路、可追溯的完整搬运实验，以及对失败边界的实测。当前比较结果不支持性能优势，我们如实报告，并把它用于确定下一轮修改与验证重点。

**为什么只算首次，重试不是都成功了吗？**

负责人反馈，重试主要由操作失误引起。操作失误也是人机交互表现的一部分，不能据此排除首次失败。78次正式尝试中有38次额外重试；若只取各试次最后一次，两方法都会变成20/20，会隐藏失败和额外练习。首次口径避免直接挑选成功，但仍受前面重试带来的学习影响。该处理是采集后确定的，后续实验应事先写入协议并统一执行。总体原因说明不代表已对每次重试完成单独归因。

**参与者都是团队成员，会不会影响结论？**

会限制结果的外推。5人此前都没有VR使用经验，但团队身份不等于对系统、任务或研究目的完全不了解。我们将其定位为团队内VR新手的小规模可行性与初步比较实验；后续需要招募团队外参与者，并统一练习条件。约10分钟练习来自负责人回忆，不能写成已严格计时的标准训练，也不能写成每种方法各10分钟。

**5个人够不够？**

足以提供小规模可行性与初步比较证据，但不足以证明普遍性能优势。独立单位是5位参与者，不是40个试次。成功率平均差为+5个百分点，探索性95%区间约[-29,+39]个百分点，仍很不确定。

**为何效率看起来提高，耗时却增加？**

限时耗时对所有失败计240秒；效率用真实计时窗口。P01/5有人为暂停，墙钟约597秒，拉长固定分配的分母。剔除该条件的整对试次后，固定/双层效率为{clean['fixed']['successes_per_600s']:.2f}/{clean['dual']['successes_per_600s']:.2f}次每10分钟。效率对暂停和统计口径敏感，不能单凭汇总效率宣称新方法更快。

**低摩擦是否只改了摩擦？**

不是。除了两处摩擦降低，还增加载荷15%、设置3.5厘米偏置。因此这是复合接触难度条件；同一场景中两种方法的物理条件一致，但不能把场景差异全部解释成摩擦的单因素作用。

**这是真机验证吗？**

是Quest 3真人输入操控MuJoCo机器人仿真。接触力、物体状态与几何信息来自仿真，尚未验证实体机器人上的传感误差、通讯与真实接触。

## 报告与PPT应同步的口径

将旧材料中的“真人实验待采集”更新为“5位参与者、40个正式试次采集完成，另有38次重试”。真人实验与此前合成输入仿真验证分开列示。不要将“70%对65%”改写成“效率提高5%”或“成功率显著提升”。这里是成功率高5个百分点，且证据尚不确定。

本文件提供结果页文字和讲稿；现有提交版PPT及汇报表未被本分析脚本改写。
'''
    (out / '答辩结果页与讲稿.md').write_text(text, encoding='utf-8')


def render_report_html(out):
    """Portable static report; escaped text and embedded local scientific figures."""
    def inline(text):
        value = html.escape(text)
        return re.sub(r'`([^`]+)`', r'<code>\1</code>', value)
    content, table, listing = [], False, False
    for line in (out / '正式实验分析报告.md').read_text(encoding='utf-8').splitlines():
        if not line.startswith('|') and table:
            content.append('</tbody></table></div>'); table = False
        if not line.startswith('- ') and listing:
            content.append('</ul>'); listing = False
        if not line:
            continue
        if line.startswith('|'):
            cells = line.strip('|').split('|')
            if all(re.fullmatch(r'[:\- ]+', c) for c in cells):
                continue
            if not table:
                content.append('<div class="table"><table><thead><tr>' + ''.join('<th>' + inline(c) + '</th>' for c in cells) + '</tr></thead><tbody>')
                table = True
            else:
                content.append('<tr>' + ''.join('<td>' + inline(c) + '</td>' for c in cells) + '</tr>')
        elif line.startswith('#'):
            level = len(line) - len(line.lstrip('#'))
            content.append(f'<h{level}>' + inline(line[level:].strip()) + f'</h{level}>')
        elif line.startswith('- '):
            if not listing:
                content.append('<ul>'); listing = True
            content.append('<li>' + inline(line[2:]) + '</li>')
        elif line.startswith('!['):
            alt, name = re.fullmatch(r'!\[(.*?)\]\((.*?)\)', line).groups()
            data = base64.b64encode((out / name).read_bytes()).decode('ascii')
            content.append(f'<img alt="{html.escape(alt)}" src="data:image/png;base64,{data}">')
        elif line.startswith('> '):
            content.append('<blockquote>' + inline(line[2:]) + '</blockquote>')
        else:
            content.append('<p>' + inline(line) + '</p>')
    if listing:
        content.append('</ul>')
    if table:
        content.append('</tbody></table></div>')
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>灵驭 · 正式实验分析</title><style>
body{font:16px/1.75 "Microsoft YaHei",sans-serif;color:#243643;background:#f4f7f8;margin:0}
main{max-width:1050px;margin:32px auto;padding:38px 48px;background:white;border-top:5px solid #159789}
h1{font-size:30px;line-height:1.4}h2{margin-top:42px;font-size:23px}h3{font-size:19px}img{width:100%;height:auto}
p,li{max-width:100ch}li{margin:8px 0}.table{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:14px;margin:16px 0}
th,td{padding:9px 10px;border-bottom:1px solid #dce4e7;text-align:left}th{background:#edf5f3;white-space:nowrap}
blockquote{border-left:4px solid #159789;margin:20px 0;padding:14px 22px;background:#eff8f5}code{background:#edf1f3;padding:2px 5px;overflow-wrap:anywhere}
@media(max-width:700px){main{margin:0;padding:22px 18px}h1{font-size:25px}}@media print{body{background:white}main{margin:0;padding:0;border:0}img,table{break-inside:avoid}h2,h3{break-after:avoid}}
</style><main>''' + '\n'.join(content) + '</main></html>'
    (out / '正式实验分析报告.html').write_text(page, encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path)
    parser.add_argument('--out', type=Path)
    main(**vars(parser.parse_args()))
