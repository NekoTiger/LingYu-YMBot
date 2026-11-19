"""Counterbalanced formal plan and a local source/protocol freeze for the two-contact risk version."""
import argparse
import hashlib
import json
import time
from pathlib import Path

from .risk_protocol import VERSION, hashes as risk_source_hashes

HERE = Path(__file__).resolve().parent

# 正式采集：2 种方法（固定分配 / 双层联合）x 2 种接触场景（正常 / 低摩擦）x 2 次重复。
# "低摩擦"映射到同时降低夹持与承载摩擦的场景（combined），冻结前请与负责人核对。
RISK_PROTOCOL = {
    'version': VERSION,
    'time_limit_s': 240,
    'participants': ['P01', 'P02', 'P03', 'P04', 'P05'],
    'policies': {'fixed': '固定分配（基线）', 'dual': '双层联合（新方法）'},
    'scenes': {'normal': '正常摩擦', 'low': '低摩擦（夹持与承载同时受限）'},
    'scene_models': {'normal': 'normal', 'low': 'combined'},
    'target_height': .75,
    'common': '五组共用滑移夹持、载荷限速、工作空间跟随、腕部水平约束与阶段判定',
    'success': '双侧夹持、抬升至少 8 cm、目标台承重、松爪、双手撤离、物件留存并稳定 1 秒',
    'failures': ['obstacle_collision', 'payload_dropped', 'parcel_left_tray', 'timeout', 'operator_abort', 'reset_or_shutdown_during_trial'],
}

SEEDS = {'normal': 9000, 'low': 9001}


def schedule(participant):
    """每人 8 次，交错排列；同一场景同一重复在两方法间共享种子。"""
    number = int(participant[-2:])
    conditions = [('fixed', 'normal'), ('dual', 'normal'), ('dual', 'low'), ('fixed', 'low')]
    offset = max(0, number - 1) % len(conditions)
    first = conditions[offset:] + conditions[:offset]
    order = first + list(reversed(first))
    seen = {}
    trials = []
    for index, (policy, scene) in enumerate(order, 1):
        seen[(policy, scene)] = seen.get((policy, scene), 0) + 1
        repeat = seen[(policy, scene)]
        trials.append({'index': index, 'policy': policy, 'scene': scene, 'repeat': repeat,
                       'seed': SEEDS[scene] + 10 * (repeat - 1)})
    return trials


def freeze(lock_path=None):
    lock_path = Path(lock_path) if lock_path is not None else HERE / 'risk_lock.json'
    content = {'protocol': RISK_PROTOCOL, 'source_sha256': risk_source_hashes(), 'frozen_unix_s': time.time(),
               'schedule': {p: schedule(p) for p in RISK_PROTOCOL['participants']}}
    with lock_path.open('x', encoding='utf-8') as file:
        json.dump(content, file, ensure_ascii=False, indent=2)
    return lock_path


def configuration(participant, index, phase, lock_path=None):
    if phase != 'formal':
        raise ValueError('双层风险版正式采集只支持 formal 阶段；试跑请用风险试跑入口。')
    if participant not in RISK_PROTOCOL['participants'] or type(index) is not int or not 1 <= index <= 8:
        raise ValueError('请选择 P01-P05 和试次 1-8。')
    condition = schedule(participant)[index - 1]
    model_scene = RISK_PROTOCOL['scene_models'][condition['scene']]
    result = {**condition, 'participant': participant, 'phase': phase,
              'mode': 'follow', 'risk_policy': condition['policy'], 'risk_scenario': model_scene,
              'scene': 'R' + model_scene, 'target_height': RISK_PROTOCOL['target_height'],
              'seed': condition['seed'], 'time_limit_s': RISK_PROTOCOL['time_limit_s'],
              'protocol_version': RISK_PROTOCOL['version'], 'source_sha256': risk_source_hashes()}
    lock_path = Path(lock_path) if lock_path is not None else HERE / 'risk_lock.json'
    if not lock_path.exists():
        raise ValueError('先完成 P00 试跑，再运行 python -m simulation.quest3.risk_study --freeze 锁定正式方案。')
    locked = json.loads(lock_path.read_text(encoding='utf-8'))
    if locked['protocol'] != RISK_PROTOCOL or locked['source_sha256'] != result['source_sha256']:
        raise ValueError('方案或源码已变化，请先核对正式实验版本。')
    result['protocol_sha256'] = hashlib.sha256(lock_path.read_bytes()).hexdigest()
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--freeze', action='store_true')
    args = parser.parse_args()
    if args.freeze:
        print(freeze())
    else:
        print(json.dumps({p: schedule(p) for p in RISK_PROTOCOL['participants']}, ensure_ascii=False, indent=2))
