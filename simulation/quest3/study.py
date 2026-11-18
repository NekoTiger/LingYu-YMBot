"""Counterbalanced plan and a local source/protocol freeze for formal collection."""
import argparse
import hashlib
import json
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROTOCOL = {
    'version': '20261116-pilot1',
    'time_limit_s': 240,
    'participants': ['P01', 'P02', 'P03', 'P04', 'P05'],
    'scenes': {'S1': {'target_height': .60, 'seed': 6101}, 'S2': {'target_height': .75, 'seed': 6102}},
    'modes': {'baseline': '双臂耦合与常规限速', 'assisted': '增加腰部稳定、载荷限速、滑移夹持与承重后释放'},
    'common': 'same body-frame mapping, rigid tray constraint, 60 ms filter, motion/force limits, watchdog and scene',
    'primary_outcomes': ['complete_task_success', 'capped_trial_wall_seconds'],
    'efficiency_definition': 'successes per 600 s of timed trials, including failures/timeouts; excludes practice, scene loading and breaks',
    'success': 'bilateral contact grasp, >=8cm lift, destination support, released and withdrawn hands, parcel retained, stable for 1 simulated second',
    'failures': ['obstacle_collision', 'payload_dropped', 'timeout', 'operator_abort', 'reset_or_shutdown_during_trial'],
}


def schedule(participant):
    number = int(participant[-2:])
    conditions = [('baseline', 'S1'), ('assisted', 'S1'), ('assisted', 'S2'), ('baseline', 'S2')]
    offset = max(0, number - 1) % len(conditions)
    first = conditions[offset:] + conditions[:offset]
    order = first + list(reversed(first))
    seen = {}
    trials = []
    for index, (mode, scene) in enumerate(order, 1):
        pair = (mode, scene)
        seen[pair] = seen.get(pair, 0) + 1
        trials.append({'index': index, 'mode': mode, 'scene': scene, 'repeat': seen[pair]})
    return trials


def source_hashes():
    files = [HERE / name for name in ('engine.py', 'protocol.py', 'trial.py', 'carry_assist.py', 'workspace_follow.py', 'follow_study.py', 'study.py', 'server.py',
                                      'web/app.js', 'web/input.js', 'web/index.html', 'web/package-lock.json')]
    files += [HERE.parent / name for name in ('control.py', 'v2/model.py', 'v2/stable_control.py', 'build_model.py')]
    return {str(path.relative_to(HERE.parent)): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}


def freeze():
    path = HERE / 'study_lock.json'
    content = {'protocol': PROTOCOL, 'source_sha256': source_hashes(), 'frozen_unix_s': time.time(),
               'schedule': {p: schedule(p) for p in PROTOCOL['participants']}}
    with path.open('x', encoding='utf-8') as file:
        json.dump(content, file, ensure_ascii=False, indent=2)
    return path


def configuration(participant, index, phase):
    if phase not in ('pilot', 'formal'):
        raise ValueError('Choose pilot or formal collection.')
    allowed = PROTOCOL['participants'] + (['P00'] if phase == 'pilot' else [])
    if participant not in allowed or type(index) is not int or not 1 <= index <= 8:
        raise ValueError('Choose P01-P05 and trial 1-8.')
    condition = schedule(participant)[index - 1]
    scene = PROTOCOL['scenes'][condition['scene']]
    result = {**condition, **scene, 'participant': participant, 'phase': phase,
              'seed': scene['seed'] + 10 * (condition['repeat'] - 1), 'time_limit_s': PROTOCOL['time_limit_s'],
              'protocol_version': PROTOCOL['version'], 'source_sha256': source_hashes()}
    if phase == 'formal':
        path = HERE / 'study_lock.json'
        if not path.exists():
            raise ValueError('先完成试跑，再运行 python -m simulation.quest3.study --freeze 锁定正式方案。')
        locked = json.loads(path.read_text(encoding='utf-8'))
        if locked['protocol'] != PROTOCOL or locked['source_sha256'] != result['source_sha256']:
            raise ValueError('方案或源码已变化，请先核对正式实验版本。')
        result['protocol_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--freeze', action='store_true')
    args = parser.parse_args()
    if args.freeze:
        print(freeze())
    else:
        print(json.dumps({p: schedule(p) for p in PROTOCOL['participants']}, ensure_ascii=False, indent=2))
