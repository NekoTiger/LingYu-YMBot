import unittest
import tempfile
from pathlib import Path

import numpy as np
import mujoco

from .workspace_follow import WorkspaceFollow, ProximityBrake
from .engine import Engine
from .test_protocol import sample
from .trial import observe


class FollowTests(unittest.TestCase):
    def ready(self, follower):
        for _ in range(25):
            follower.update(.50, eligible=True)

    def test_no_start_at_boundary_until_neutral_then_dwell(self):
        follower = WorkspaceFollow()
        for _ in range(100):
            self.assertEqual(follower.update(.66, eligible=True), 0.)
        self.ready(follower)
        for _ in range(10):
            self.assertEqual(follower.update(.66, eligible=True), 0.)
        for _ in range(50):
            speed = follower.update(.66, eligible=True)
        self.assertGreater(speed, 0.)
        self.assertLessEqual(speed, .16)
        self.assertEqual(follower.update(.50, eligible=True), 0.)

    def test_manual_and_contact_loss_cancel_and_require_neutral(self):
        for block in ('manual', 'load'):
            follower = WorkspaceFollow()
            self.ready(follower)
            for _ in range(80):
                speed = follower.update(.30, eligible=True)
            self.assertLess(speed, 0.)
            self.assertEqual(follower.update(.30, eligible=block!='load', manual=block=='manual'), 0.)
            for _ in range(30):
                self.assertEqual(follower.update(.30, eligible=True), 0.)

    def test_short_excursions_do_not_start_gated_following(self):
        follower = WorkspaceFollow()
        self.ready(follower)
        for _ in range(20):
            for x in [.61]*6+[.50]*12:
                self.assertEqual(follower.update(x, eligible=True), 0.)

    def test_neutral_is_calibrated_to_actual_robot_hands(self):
        follower = WorkspaceFollow()
        follower.calibrate(.39)
        for _ in range(25):
            self.assertEqual(follower.update(.39, eligible=True), 0.)
        self.assertTrue(follower.armed)
        for _ in range(80):
            speed = follower.update(.52, eligible=True)
        self.assertGreater(speed, 0.)

    def test_engine_unloaded_hand_extension_never_drives_base(self):
        with tempfile.TemporaryDirectory() as folder:
            engine = Engine(Path(folder)/'run', mode='follow')
            start = engine.started
            try:
                for i in range(160):
                    packet = sample(i, i*.01, squeeze=0 if i<10 else 1,
                                    shift=(0, 0, -.22 if i>40 else 0))
                    engine.receive(packet, start+i*.01)
                    engine.step(start+i*.01)
                self.assertTrue(engine.active)
                np.testing.assert_equal(engine.twist, [0., 0.])
                self.assertEqual(engine.follow.state, 'load_not_ready')
                self.assertLess(abs(engine.d.qpos[0]), .01)
            finally:
                engine.close()

    def test_proximity_brake_reduces_approach_but_allows_retreat(self):
        model = mujoco.MjModel.from_xml_string('''<mujoco><worldbody>
          <body pos="0.60 0 0.5"><freejoint/><geom name="base_collision" type="sphere" size="0.1" mass="1"/></body>
          <geom name="aisle_obstacle" type="box" pos="1 0 0.5" size="0.2 0.2 0.2"/>
        </worldbody></mujoco>''')
        data = mujoco.MjData(model)
        mujoco.mj_forward(model, data)
        brake = ProximityBrake(model)
        self.assertLess(brake.limit(data, .16, 0., .16), .16)
        self.assertEqual(brake.limit(data, -.16, 0., .16), -.16)
        data.qpos[0] = .68
        mujoco.mj_forward(model, data)
        self.assertEqual(brake.limit(data, .16, 0., .16), 0.)

    def test_loaded_pause_keeps_waist_reference_and_tracking_loss_stops(self):
        # Test fixture is a previously recorded physical carry state, never an
        # intervention in benchmark runs or rendered demonstrations.
        fixture = Path(__file__).resolve().parent/'outputs/follow_validation_r2_20261117/gated_75_7300/states_0000.npz'
        with tempfile.TemporaryDirectory() as folder:
            engine = Engine(Path(folder)/'run', mode='follow', seed=7300, target_height=.75)
            try:
                with np.load(fixture) as data:
                    index = int(np.searchsorted(data['sim_time'], 14.))
                    engine.d.qpos[:] = data['qpos'][index]
                    engine.d.qvel[:] = data['qvel'][index]
                    engine.d.ctrl[:] = data['ctrl'][index]
                mujoco.mj_forward(engine.m, engine.d)
                engine.servo.qtarget = engine.d.qpos.copy()
                engine.aperture = engine.aperture_goal = 0.
                engine.observation = observe(engine.m, engine.d)
                engine.target_world = np.asarray(engine.observation.hand_positions)
                for _ in range(25):
                    engine.assistance.update(engine.observation, engine.info['mass']+.17, engine.target_world, 0.)
                self.assertTrue(engine.assistance.grasped)
                start = engine.started
                for tick in range(120):
                    engine.receive(sample(tick, tick*.01, squeeze=0 if tick<2 else 1,
                                          trigger=1., stick=(0,-.3) if 10<=tick<50 else (0,0)), start+tick*.01)
                    engine.step(start+tick*.01)
                    if tick == 40:
                        anchor = engine.ik.anchor.copy()
                self.assertTrue(engine.ik.anchored)
                np.testing.assert_allclose(engine.ik.anchor, anchor, atol=1e-9)
                np.testing.assert_equal(engine.twist, [0.,0.])
                packet = sample(120,1.20,squeeze=1.)
                packet['tracked'] = False
                engine.receive(packet,start+1.20)
                engine.step(start+1.20)
                self.assertFalse(engine.active)
                np.testing.assert_equal(engine.d.ctrl[engine.servo.wheels], [0.,0.])
                engine.receive(sample(121,1.21,squeeze=1.),start+1.21)
                engine.step(start+1.21)
                self.assertFalse(engine.active)
            finally:
                engine.close()


if __name__ == '__main__':
    unittest.main()
