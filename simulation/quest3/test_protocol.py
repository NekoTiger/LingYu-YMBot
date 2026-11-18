import copy,unittest
import numpy as np
from scipy.spatial.transform import Rotation
from .protocol import Packet,Mailbox,RelativeTrayMapper,XR_TO_ROBOT

def sample(seq=0,capture=0.,squeeze=0.,trigger=0.,shift=(0,0,0),stick=(0,0)):
    def pose(p):return {'position':(np.array(p)+shift).tolist(),'quaternion':[0,0,0,1]}
    return {'type':'pose','schema':1,'frame':'webxr_local_floor','seq':seq,'capture_s':capture,'tracked':True,
            'head':pose([0,1.6,0]),'left':pose([-.3,1.1,-.4]),'right':pose([.3,1.1,-.4]),
            'squeeze':[squeeze,squeeze],'trigger':[trigger,trigger],'stick':list(stick),'estop':False}

class ProtocolTests(unittest.TestCase):
    def test_reject_nonfinite_pose_and_invalid_controls(self):
        for change in ['nan','quat','buttons','seq']:
            p=sample()
            if change=='nan':p['left']['position'][0]=float('nan')
            if change=='quat':p['right']['quaternion']=[0,0,0,0]
            if change=='buttons':p['squeeze']=[2,0]
            if change=='seq':p['seq']=True
            with self.assertRaises(ValueError):Packet.parse(p)
    def test_packet_reordering_and_buffer_delay(self):
        box=Mailbox();box.push(sample(0,10),100)
        with self.assertRaises(ValueError):box.push(sample(0,11),101)
        with self.assertRaises(ValueError):box.push(sample(1,10.01),100.4)
        box.push(sample(2,10.5),100.5);self.assertEqual(box.seq,2)
    def test_tracking_loss_is_valid_stop_signal(self):
        p=sample();p['tracked']=False;del p['left'];parsed=Packet.parse(p)
        self.assertFalse(parsed.tracked);self.assertEqual(parsed.hands,[])
    def test_axis_mapping_and_rigid_span(self):
        mapper=RelativeTrayMapper();robot=np.array([[.4,.3,.8],[.4,-.3,.8]])
        mapper.calibrate(Packet.parse(sample()),robot)
        for shift,delta in [([0,0,-.1],[.08,0,0]),([-.05,0,0],[0,.04,0]),([0,.1,0],[0,0,.08])]:
            got,yaw=mapper.map(Packet.parse(sample(shift=shift)))
            np.testing.assert_allclose(got,robot+delta,atol=1e-9);self.assertAlmostEqual(np.linalg.norm(got[0]-got[1]),.6)
    def test_head_heading_and_regrip_preserve_robot_yaw(self):
        p=sample();rotation=Rotation.from_euler('y',.8)
        for key in ['head','left','right']:
            p[key]['position']=rotation.apply(p[key]['position']).tolist();p[key]['quaternion']=rotation.as_quat().tolist()
        robot=np.array([[.4,0,.8],[.4,0,.8]])+Rotation.from_euler('z',.2).apply([[0,.3,0],[0,-.3,0]])
        mapper=RelativeTrayMapper();mapper.calibrate(Packet.parse(p),robot)
        target,yaw=mapper.map(Packet.parse(p));np.testing.assert_allclose(target,robot,atol=1e-9);self.assertAlmostEqual(yaw,.2)
        # Walk forward relative to the calibrated head direction.
        shifted=copy.deepcopy(p)
        for key in ['left','right']:shifted[key]['position']=(np.array(shifted[key]['position'])+rotation.apply([0,0,-.05])).tolist()
        target,_=mapper.map(Packet.parse(shifted));np.testing.assert_allclose(target,robot+[.04,0,0],atol=1e-9)
    def test_workspace_clamp(self):
        mapper=RelativeTrayMapper();mapper.calibrate(Packet.parse(sample()),np.array([[.4,.3,.8],[.4,-.3,.8]]))
        got,_=mapper.map(Packet.parse(sample(shift=[-2,2,-2])));np.testing.assert_allclose(got.mean(axis=0),[.55,.09,.93])

if __name__=='__main__':unittest.main()
