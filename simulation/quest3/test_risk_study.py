import json
import tempfile
import unittest
from pathlib import Path

from .risk_study import RISK_PROTOCOL, configuration, freeze, schedule


class RiskStudyTests(unittest.TestCase):
    def test_schedule_shape_and_counts(self):
        for participant in RISK_PROTOCOL['participants']:
            trials = schedule(participant)
            self.assertEqual([trial['index'] for trial in trials], list(range(1, 9)))
            counts = {}
            for trial in trials:
                counts[(trial['policy'], trial['scene'])] = counts.get((trial['policy'], trial['scene']), 0) + 1
            self.assertEqual(set(counts), {('fixed', 'normal'), ('dual', 'normal'), ('fixed', 'low'), ('dual', 'low')})
            self.assertEqual(set(counts.values()), {2})

    def test_seeds_pair_across_policies(self):
        for participant in RISK_PROTOCOL['participants']:
            trials = schedule(participant)
            for scene in ('normal', 'low'):
                for repeat in (1, 2):
                    seeds = {trial['seed'] for trial in trials
                             if trial['scene'] == scene and trial['repeat'] == repeat}
                    self.assertEqual(len(seeds), 1, msg=(participant, scene, repeat))

    def test_orders_rotate_and_mirror_across_participants(self):
        orders = {p: tuple((t['policy'], t['scene']) for t in schedule(p))
                  for p in RISK_PROTOCOL['participants']}
        # 4 种条件轮换只能覆盖 4 种顺序；5 名参与者中首尾两人顺序相同，
        # 与 8766 的口径一致，报告中说明实际安排即可。
        self.assertEqual(len(set(orders.values())), 4)
        for order in orders.values():
            self.assertEqual(order[:4], tuple(reversed(order[4:])))

    def test_configuration_rejects_bad_inputs(self):
        for participant, index, phase in [('P01', 1, 'pilot'), ('P00', 1, 'formal'),
                                          ('P01', 0, 'formal'), ('P01', 9, 'formal'),
                                          ('PX', 1, 'formal'), ('P01', '1', 'formal')]:
            with self.assertRaises(ValueError, msg=(participant, index, phase)):
                configuration(participant, index, phase)

    def test_configuration_requires_lock(self):
        with self.assertRaises(ValueError):
            configuration('P01', 1, 'formal',
                          lock_path=Path(tempfile.gettempdir()) / 'risk_lock_missing_7f3a1.json')

    def test_freeze_and_formal_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = freeze(Path(tmp) / 'risk_lock.json')
            config = configuration('P03', 4, 'formal', lock_path=lock)
            self.assertEqual(config['phase'], 'formal')
            self.assertEqual(config['participant'], 'P03')
            self.assertEqual(config['index'], 4)
            self.assertEqual(config['mode'], 'follow')
            self.assertIn(config['risk_policy'], RISK_PROTOCOL['policies'])
            self.assertIn(config['risk_scenario'], RISK_PROTOCOL['scene_models'].values())
            self.assertEqual(config['time_limit_s'], RISK_PROTOCOL['time_limit_s'])
            self.assertIn('protocol_sha256', config)
            trial = schedule('P03')[3]
            self.assertEqual(config['risk_policy'], trial['policy'])
            self.assertEqual(config['seed'], trial['seed'])

    def test_tampered_lock_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = freeze(Path(tmp) / 'risk_lock.json')
            data = json.loads(lock.read_text(encoding='utf-8'))
            data['protocol'] = dict(data['protocol'], time_limit_s=999)
            lock.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
            with self.assertRaises(ValueError):
                configuration('P01', 1, 'formal', lock_path=lock)


if __name__ == '__main__':
    unittest.main()
