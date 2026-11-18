"""Device-neutral WebXR packets. Poses use meters and xyzw quaternions."""
from dataclasses import dataclass
import numpy as np
from scipy.spatial.transform import Rotation

def vector(value,n,label):
    a=np.asarray(value,dtype=float)
    if a.shape!=(n,) or not np.all(np.isfinite(a)):raise ValueError('invalid '+label)
    return a

@dataclass
class Pose:
    position:np.ndarray
    quaternion:np.ndarray
    @classmethod
    def parse(cls,p):
        pos=vector(p['position'],3,'position');q=vector(p['quaternion'],4,'quaternion')
        if np.max(np.abs(pos))>20 or abs(np.linalg.norm(q)-1)>.03:raise ValueError('pose outside supported tracking range')
        return cls(pos,q/np.linalg.norm(q))

@dataclass
class Packet:
    seq:int
    capture_s:float
    tracked:bool
    head:Pose|None
    hands:list
    squeeze:np.ndarray
    trigger:np.ndarray
    stick:np.ndarray
    estop:bool
    @classmethod
    def parse(cls,p):
        if p.get('type')!='pose' or p.get('frame')!='webxr_local_floor' or p.get('schema')!=1:raise ValueError('unsupported packet schema')
        seq=p['seq'];capture=float(p['capture_s'])
        if type(seq)is not int or seq<0 or not np.isfinite(capture)or capture<0:raise ValueError('invalid sequence/timestamp')
        tracked=p.get('tracked') is True
        if not tracked:return cls(seq,capture,False,None,[],np.zeros(2),np.zeros(2),np.zeros(2),bool(p.get('estop',False)))
        head=Pose.parse(p['head']);hands=[Pose.parse(p[s])for s in ['left','right']]
        squeeze=vector(p['squeeze'],2,'squeeze');trigger=vector(p['trigger'],2,'trigger');stick=vector(p['stick'],2,'stick')
        if np.any(squeeze<0)or np.any(squeeze>1)or np.any(trigger<0)or np.any(trigger>1)or np.any(np.abs(stick)>1.01):raise ValueError('invalid buttons/axes')
        return cls(seq,capture,True,head,hands,squeeze,trigger,np.clip(stick,-1,1),bool(p.get('estop',False)))

class Mailbox:
    def __init__(self):self.clear()
    def clear(self):self.packet=None;self.received=-float('inf');self.seq=-1;self.capture=-1.;self.rejected=0;self.clock_offset=None
    def push(self,raw,now):
        p=Packet.parse(raw)
        if p.seq<=self.seq or p.capture_s<=self.capture:raise ValueError('out-of-order packet')
        offset=now-p.capture_s
        if self.clock_offset is not None and offset-self.clock_offset>.25:raise ValueError('buffered packet older than 250 ms')
        self.clock_offset=offset if self.clock_offset is None else min(self.clock_offset,offset)
        self.packet=p;self.received=now;self.seq=p.seq;self.capture=p.capture_s
        return p

XR_TO_ROBOT=np.array([[0,0,-1],[-1,0,0],[0,1,0]],float)

class RelativeTrayMapper:
    """Head-heading calibration; task manifold keeps the rigid tray level."""
    def __init__(self,scale=.8):self.scale=scale
    def calibrate(self,p,robot_local):
        forward=Rotation.from_quat(p.head.quaternion).apply([0,0,-1])
        yaw=np.arctan2(-forward[0],-forward[2]) if np.linalg.norm(forward[[0,2]])>.1 else 0.
        self.mapping=XR_TO_ROBOT@Rotation.from_euler('y',-yaw).as_matrix()
        self.xr_anchor=np.array([h.position for h in p.hands]);self.robot_center=robot_local.mean(axis=0).copy()
        span=self.mapping@(self.xr_anchor[0]-self.xr_anchor[1]);self.initial_yaw=np.arctan2(-span[0],span[1])
        robot_span=robot_local[0]-robot_local[1];self.robot_yaw=float(np.arctan2(-robot_span[0],robot_span[1]))
    def map(self,p):
        positions=np.array([h.position for h in p.hands]);delta=(positions-self.xr_anchor)@self.mapping.T
        center=self.robot_center+self.scale*delta.mean(axis=0)
        self.raw_center = center.copy()
        center=np.clip(center,[.22,-.09,.60],[.55,.09,.93])
        span=self.mapping@(positions[0]-positions[1]);yaw=np.arctan2(-span[0],span[1])-self.initial_yaw
        yaw=float(np.clip(self.robot_yaw+np.clip((yaw+np.pi)%(2*np.pi)-np.pi,-.35,.35),-.35,.35))
        rot=Rotation.from_euler('z',yaw).as_matrix();offset=rot@np.array([0,.30,0])
        return np.array([center+offset,center-offset]),float(yaw)
