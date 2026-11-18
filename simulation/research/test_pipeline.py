"""Independent invariants for the tracking and shared-control interfaces."""
import unittest,numpy as np,mujoco
from world import make_model
from input_channel import InputChannel
from control import rz

class PipelineTests(unittest.TestCase):
    def test_latency_reprojects_current_base(self):
        ch=InputChannel(1,0,.08,0,shared=True);q=np.array([[.4,.3,.85],[.4,-.3,.85]])
        for k in range(21):
            t=k*.01;base=np.array([t*.2,0,t*.4]);rot=rz(base[2]);goal=(rot@q.T).T+np.r_[base[:2],0]
            answer,R,age=ch.update(t,goal,rot,base,True)
        np.testing.assert_allclose(answer,goal,atol=1e-10);self.assertGreaterEqual(age,.08-1e-10)
    def test_rigid_grasp_rejects_independent_hand_jitter(self):
        ch=InputChannel(4,.012,0,.1,shared=True);q=np.array([[.4,.3,.85],[.4,-.3,.85]])
        for k in range(100):
            target,R,age=ch.update(k*.01,q,np.eye(3),np.zeros(3),True)
            self.assertAlmostEqual(np.linalg.norm(target[0]-target[1]),.6,places=10)
            self.assertAlmostEqual(target[0,2],target[1,2],places=10)
        self.assertGreater(ch.gaps,0)
    def test_gravity_free_cargo_and_contact_drive(self):
        m,d,_,_=make_model(dynamic=True)
        self.assertEqual(m.neq,0);self.assertEqual(m.nmocap,0)
        self.assertEqual(m.joint('chassis_free').type[0],mujoco.mjtJoint.mjJNT_FREE)
        self.assertEqual(m.joint('cargo_free').type[0],mujoco.mjtJoint.mjJNT_FREE)
        self.assertEqual(m.joint('cart_slide').type[0],mujoco.mjtJoint.mjJNT_SLIDE)
        np.testing.assert_array_equal(m.body_gravcomp,0)
        self.assertFalse(any(m.actuator(i).name.startswith('base_')for i in range(m.nu)))

if __name__=='__main__':unittest.main()
