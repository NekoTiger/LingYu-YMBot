"""Regression checks for physical scoring, fair conditions and session lifecycle."""
import json
import asyncio
import tempfile
import time
import unittest
from pathlib import Path

import mujoco
import numpy as np

from .engine import Engine
from .study import PROTOCOL, configuration, schedule
from .test_protocol import sample
from .trial import Trial, observe
from .server import Gateway
from .analyze_study import analyze
from aiohttp import ClientSession, web


class StudyTests(unittest.TestCase):
    def test_analysis_pairs_participants_and_flags_duplicate_attempts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index, condition in enumerate(schedule('P01'), 1):
                folder = root/str(index)
                folder.mkdir()
                failed = condition['mode'] == 'baseline' and condition['repeat'] == 1
                row = {**condition, 'participant': 'P01', 'phase': 'formal', 'source': 'webxr_live',
                       'sources_seen': ['webxr_live'], 'protocol_sha256': 'unit_test_fixture',
                       'outcome': 'failure' if failed else 'success', 'elapsed_wall_s': 100.,
                       'time_limit_s': 240., 'clutch_calibrations': 1, 'tracking_loss_wall_s': 0.}
                (folder/'trial_result.json').write_text(json.dumps(row), encoding='utf-8')
            analyze(root)
            result = json.loads((root/'analysis/summary.json').read_text(encoding='utf-8'))
            self.assertEqual(result['independent_participants_complete'], 1)
            self.assertEqual(result['paired_differences'][0]['success_rate_difference'], .5)
            self.assertEqual(result['paired_differences'][0]['capped_time_difference_s'], -70.)
            extra = root/'duplicate'
            extra.mkdir()
            (extra/'trial_result.json').write_text(json.dumps(row), encoding='utf-8')
            analyze(root)
            result = json.loads((root/'analysis/summary.json').read_text(encoding='utf-8'))
            self.assertEqual(result['duplicate_trials'], [['P01', 8]])

    def test_counterbalanced_pairs_share_scene_and_seed(self):
        for participant in PROTOCOL['participants']:
            trials = [configuration(participant, i, 'pilot') for i in range(1, 9)]
            self.assertEqual(len({(t['mode'], t['scene'], t['repeat']) for t in trials}), 8)
            for scene in ('S1', 'S2'):
                for repeat in (1, 2):
                    pair = [t for t in trials if t['scene'] == scene and t['repeat'] == repeat]
                    self.assertEqual(pair[0]['seed'], pair[1]['seed'])
                    self.assertEqual(pair[0]['target_height'], pair[1]['target_height'])

    def test_live_modes_move_and_only_assisted_anchors_waist(self):
        with tempfile.TemporaryDirectory() as temporary:
            for mode in ('baseline', 'assisted'):
                engine = Engine(Path(temporary)/mode, mode=mode)
                engine.connect('synthetic_transport_test', 'test')
                start = engine.started
                try:
                    for tick in range(100):
                        packet = sample(tick, tick*.01, squeeze=0 if tick<10 else 1, stick=(0, 1))
                        engine.receive(packet, start+tick*.01)
                        engine.step(start+tick*.01)
                    self.assertTrue(engine.active)
                    self.assertEqual(engine.ik.anchored, mode == 'assisted')
                    self.assertLess(engine.d.body('base_footprint_link').xpos[0], -.02)
                finally:
                    engine.close()

    def test_ready_does_not_move_and_timeout_is_recorded(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = configuration('P01', 1, 'pilot')
            config['time_limit_s'] = .2
            engine = Engine(Path(temporary)/'run', trial_config=config)
            engine.connect('synthetic_transport_test', 'test')
            now = engine.started
            try:
                engine.receive(sample(0,0), now)
                engine.step(now)
                engine.receive(sample(1,.01,squeeze=1), now+.01)
                engine.step(now+.01)
                self.assertFalse(engine.active)
                engine.trial.start(engine, now+.02)
                engine.trial.update(engine, engine.observation, now+.23)
                result = json.loads((engine.recorder.root/'trial_result.json').read_text(encoding='utf-8'))
                self.assertEqual(result['reason'], 'timeout')
                self.assertEqual(result['source'], 'synthetic_transport_test')
            finally:
                engine.close()

    def test_scoring_saved_complete_physics_trajectory(self):
        folder = Path(__file__).resolve().parents[1]/'research/outputs/demo_dynamic'
        metadata = json.loads((folder/'summary.json').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as temporary:
            engine = Engine(Path(temporary)/'verification')
            engine.connect('synthetic_transport_test', 'saved physics verification')
            engine.m = mujoco.MjModel.from_xml_path(str(folder/'scene.xml'))
            engine.d = mujoco.MjData(engine.m)
            engine.info = metadata
            config = configuration('P01', 3, 'pilot')
            engine.trial = Trial(engine, config)
            engine.trial.start(engine, 0.)
            try:
                with np.load(folder/'trajectory.npz') as data:
                    positions, velocities, commands = data['qpos'], data['qvel'], data['ctrl']
                    for i in range(len(positions)):
                        engine.d.qpos[:] = positions[i]
                        engine.d.qvel[:] = velocities[i]
                        engine.d.ctrl[:] = commands[i]
                        engine.d.time = i*.01
                        mujoco.mj_forward(engine.m, engine.d)
                        engine.observation = observe(engine.m, engine.d)
                        engine.trial.update(engine, engine.observation, i*.01)
                        if engine.trial.result:
                            break
                self.assertIsNotNone(engine.trial.result)
                self.assertEqual(engine.trial.result['outcome'], 'success')
                self.assertGreater(engine.trial.result['final_observation']['destination_support_n'], 1.)
                # The same final placement alone cannot substitute for a complete task.
                engine.trial = Trial(engine, config)
                engine.trial.start(engine, 0.)
                for i in range(110):
                    engine.trial.update(engine, engine.observation, i*.01)
                self.assertIsNone(engine.trial.result)
                engine.trial.status = 'ready'
            finally:
                engine.close()


class StudyTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_prepare_start_abort_and_geometry_update(self):
        with tempfile.TemporaryDirectory() as temporary:
            gateway = Gateway(Path(temporary)/'initial')
            runner = web.AppRunner(gateway.app())
            await runner.setup()
            site = web.TCPSite(runner, '127.0.0.1', 0)
            await site.start()
            port = site._server.sockets[0].getsockname()[1]
            try:
                async with ClientSession(trust_env=False) as client:
                    ws = await client.ws_connect(f'http://127.0.0.1:{port}/ws')
                    async def message(kind):
                        async with asyncio.timeout(30):
                            while True:
                                value = await ws.receive_json()
                                if value['type'] == kind:
                                    return value
                    await message('hello')
                    await ws.send_json({'type': 'claim', 'source': 'synthetic_transport_test', 'device': 'test'})
                    await message('claimed')
                    sequence = 0
                    for index, height in ((1, .60), (3, .75)):
                        await ws.send_json({'type': 'study_prepare', 'participant': 'P00', 'index': index, 'phase': 'pilot'})
                        reset = await message('reset')
                        self.assertEqual(len(reset['geoms']), len(gateway.engine.visible))
                        self.assertEqual(gateway.engine.info['target_height'], height)
                        self.assertEqual(gateway.engine.trial.status, 'ready')
                        await ws.send_json(sample(sequence, time.monotonic()))
                        sequence += 1
                        await ws.send_json({'type': 'study_start'})
                        deadline = time.monotonic()+1
                        while gateway.engine.trial.status == 'ready' and time.monotonic()<deadline:
                            await asyncio.sleep(.01)
                        self.assertEqual(gateway.engine.trial.status, 'running')
                        await ws.send_json({'type': 'marker', 'label': 'success'})
                        await message('error')
                        self.assertEqual(gateway.engine.trial.status, 'running')
                        await ws.send_json({'type': 'study_abort'})
                        deadline = time.monotonic()+1
                        while gateway.engine.trial.result is None and time.monotonic()<deadline:
                            await asyncio.sleep(.01)
                        self.assertEqual(gateway.engine.trial.result['reason'], 'operator_abort')
                        self.assertTrue((gateway.engine.recorder.root/'trial_result.json').exists())
                    await ws.send_json({'type': 'follow_prepare', 'policy': 'off', 'height': .75})
                    await message('reset')
                    self.assertEqual(gateway.engine.mode, 'follow')
                    self.assertEqual(gateway.engine.follow.policy, 'off')
                    self.assertEqual(gateway.engine.trial.config['phase'], 'pilot')
                    await ws.send_json({'type':'risk_prepare','policy':'dual','scenario':'payload'})
                    await message('reset')
                    self.assertEqual(gateway.engine.allocator.policy,'dual')
                    self.assertEqual(gateway.engine.info['risk_settings']['surface_mu'],.16)
                    self.assertEqual(gateway.engine.trial.config['phase'],'pilot')
                    state=await message('state')
                    self.assertIn('risk_allocation',state)
                    self.assertGreater(state['risk_allocation']['edge_margin_m'],0.)
                    await ws.send_json({'type':'reset'})
                    await message('reset')
                    self.assertEqual(gateway.engine.allocator.policy,'dual')
                    self.assertEqual(gateway.engine.info['risk_scenario'],'payload')
                    await ws.close()
            finally:
                await runner.cleanup()


if __name__ == '__main__':
    unittest.main()
