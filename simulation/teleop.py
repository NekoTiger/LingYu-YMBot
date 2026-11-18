"""Device-neutral pose packets and WebXR-to-MuJoCo relative mapping.

This is a tested input adapter, not a claim of connected VR hardware.
Right-handed WebXR (X right, Y up, -Z forward) -> robot (X forward,Y left,Z up).
"""
from dataclasses import dataclass
import json
from pathlib import Path
import numpy as np

XR_TO_ROBOT=np.array([[0,0,-1],[-1,0,0],[0,1,0]],dtype=float)

@dataclass
class PosePacket:
    timestamp: float
    left: np.ndarray
    right: np.ndarray
    rotation: np.ndarray
    aperture: float
    base: np.ndarray | None = None

    @classmethod
    def from_dict(cls,packet):
        if packet.get('frame')!='world_meters':
            raise ValueError('frame must be world_meters after calibration')
        left=np.asarray(packet['left'],float);right=np.asarray(packet['right'],float)
        rotation=np.asarray(packet.get('rotation',np.eye(3)),float)
        vals=np.r_[left.ravel(),right.ravel(),rotation.ravel(),packet['timestamp'],packet['aperture']]
        if left.shape!=(3,) or right.shape!=(3,) or rotation.shape!=(3,3) or not np.all(np.isfinite(vals)):
            raise ValueError('invalid pose shape or nonfinite pose')
        if not np.allclose(rotation.T@rotation,np.eye(3),atol=1e-5) or np.linalg.det(rotation)<.999:
            raise ValueError('rotation must be SO(3)')
        if not 0<=float(packet['aperture'])<=.045:
            raise ValueError('aperture outside [0,0.045] meters')
        base=np.asarray(packet['base'],float) if 'base' in packet else None
        if base is not None and (base.shape!=(3,) or not np.all(np.isfinite(base))):
            raise ValueError('base must contain finite x/y/yaw')
        return cls(float(packet['timestamp']),left,right,rotation,float(packet['aperture']),base)

class RelativeMapper:
    def __init__(self,scale=1.,max_step=.02):
        self.scale=scale;self.max_step=max_step;self.anchor=None;self.robot_anchor=None;self.last=None

    def clutch(self,xr_hands,robot_hands):
        self.anchor=np.asarray(xr_hands,float).copy();self.robot_anchor=np.asarray(robot_hands,float).copy();self.last=self.robot_anchor.copy()

    def map(self,xr_hands):
        if self.anchor is None: raise RuntimeError('clutch calibration required')
        target=self.robot_anchor+self.scale*((np.asarray(xr_hands)-self.anchor)@XR_TO_ROBOT.T)
        delta=target-self.last
        norms=np.linalg.norm(delta,axis=1,keepdims=True)
        target=self.last+delta*np.minimum(1,self.max_step/np.maximum(norms,1e-9))
        self.last=target.copy()
        return target

def load_packets(path):
    packets=[PosePacket.from_dict(json.loads(line)) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]
    if not packets: raise ValueError('empty packet stream')
    if any(b.timestamp<=a.timestamp for a,b in zip(packets,packets[1:])):
        raise ValueError('timestamps must strictly increase')
    return packets

def export_npz(path,out):
    data=np.load(path);lines=[]
    from control import rz
    for t,row in zip(data['time'],data['hand_targets']):
        packet={'timestamp':float(t),'frame':'world_meters','left':row[:3].tolist(),'right':row[3:6].tolist(),'rotation':rz(row[8]).tolist(),'aperture':float(row[9]),'base':row[6:9].tolist(),'source':'synthetic_reference'}
        lines.append(json.dumps(packet))
    Path(out).write_text('\n'.join(lines)+'\n',encoding='utf-8')

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('trajectory');p.add_argument('output');a=p.parse_args();export_npz(a.trajectory,a.output)
