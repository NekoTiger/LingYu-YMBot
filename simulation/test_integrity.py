"""Checks that matter for scientific integrity and the live input boundary."""
import unittest,json
import numpy as np
from scene import make_scene
from teleop import PosePacket,RelativeMapper,XR_TO_ROBOT
from control import Controller,rz
import mujoco

class IntegrityTests(unittest.TestCase):
    def test_no_hidden_attachment(self):
        m,d,_=make_scene('bimanual',0)
        self.assertEqual(m.neq,0);self.assertEqual(m.nmocap,0)
        self.assertEqual(m.joint('cargo_free').type[0],mujoco.mjtJoint.mjJNT_FREE)
        z=d.qpos[m.joint('cargo_free').qposadr[0]+2]
        for _ in range(200):mujoco.mj_step(m,d)
        self.assertTrue(np.isfinite(d.qpos).all())
        self.assertGreater(d.body('cargo').xpos[2],.72)

    def test_pair_randomization_identical(self):
        _,_,a=make_scene('single',11,.035);_,_,b=make_scene('single',11,.035)
        self.assertEqual(a,b)

    def test_xr_mapping_and_clutch(self):
        np.testing.assert_allclose(np.linalg.det(XR_TO_ROBOT),1)
        mapper=RelativeMapper(max_step=1)
        mapper.clutch(np.zeros((2,3)),np.zeros((2,3)))
        np.testing.assert_allclose(mapper.map(np.array([[0,0,-.1],[0,.1,0]])),[[.1,0,0],[0,0,.1]])
        mapper.clutch(np.ones((2,3)),np.zeros((2,3)))
        np.testing.assert_allclose(mapper.map(np.ones((2,3))),0)

    def test_reject_corrupt_packet(self):
        p={'frame':'world_meters','timestamp':0,'left':[0,0,1],'right':[0,0,1],'aperture':.02}
        self.assertEqual(PosePacket.from_dict(p).aperture,.02)
        p['left'][0]=float('nan')
        with self.assertRaises(ValueError):PosePacket.from_dict(p)

    def test_speed_limits(self):
        m,d,_=make_scene('bimanual',0);c=Controller(m,d)
        before=d.qpos.copy();after=c.step(d,np.array([[.38,.3,.82],[.38,-.3,.82]]),rz(0))
        self.assertLessEqual(np.max(np.abs(after[c.qids]-before[c.qids])),.010001)

if __name__=='__main__':unittest.main(verbosity=2)
