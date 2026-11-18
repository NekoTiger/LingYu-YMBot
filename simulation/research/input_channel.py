"""Synthetic 50 Hz tracking packets with latency, packet loss and hand noise.
No packets are represented as recordings of a human or a real VR device.
"""
from collections import deque
import numpy as np
from scipy.spatial.transform import Rotation
from control import rz

class InputChannel:
    def __init__(self,seed,noise=0.,latency=0.,dropout=0.,shared=False):
        self.rng=np.random.default_rng(seed+8000);self.noise=noise;self.latency=latency;self.dropout=dropout;self.shared=shared
        self.pending=deque();self.latest=None;self.next_time=0.;self.filtered=None;self.filter_mode=None;self.packet_log=[];self.gaps=0;self.compensate=True
    def update(self,t,target,rotation,base,carrying):
        if t+1e-8>=self.next_time:
            self.next_time+=.02
            noisy=target+self.rng.normal(0,self.noise,(2,3));angle=self.rng.normal(0,self.noise*1.5,3)
            rot=Rotation.from_rotvec(angle).as_matrix()@rotation
            dropped=self.rng.random()<self.dropout
            packet=(t,noisy,rot,base.copy(),carrying)
            self.packet_log.append((t,noisy.copy(),rot.copy(),base.copy(),dropped))
            if not dropped:self.pending.append(packet)
            else:self.gaps+=1
        while self.pending and self.pending[0][0]+self.latency<=t+1e-8:self.latest=self.pending.popleft()
        if self.latest is None:return target.copy(),rotation.copy(),0.
        sent,position,rot,oldbase,oldcarrying=self.latest;position=position.copy();rot=rot.copy()
        if self.shared and self.compensate and carrying and oldcarrying:
            # Reproject delayed operator intent using the current measured base,
            # so base translation/yaw does not become a delayed hand command.
            oldR=rz(oldbase[2]);newR=rz(base[2]);local=(oldR.T@(position-np.r_[oldbase[:2],0]).T).T
            position=(newR@local.T).T+np.r_[base[:2],0];rot=newR@oldR.T@rot
        if self.shared:
            # Project two noisy hand targets onto a rigid, level grasp manifold.
            center=position.mean(axis=0);desired_rotation=rotation
            if self.filter_mode!=carrying:self.filtered=None;self.filter_mode=carrying
            if carrying:
                currentR=rz(base[2]);localcenter=currentR.T@(center-np.r_[base[:2],0])
                if self.filtered is None:self.filtered=localcenter.copy()
                self.filtered+=.01/(.06+.01)*(localcenter-self.filtered)
                center=currentR@self.filtered+np.r_[base[:2],0]
            else:
                if self.filtered is None:self.filtered=center.copy()
                self.filtered+=.01/(.06+.01)*(center-self.filtered)
                center=self.filtered.copy()
            offset=desired_rotation@np.array([0,.30,0]);position=np.array([center+offset,center-offset]);rot=desired_rotation
        return position,rot,t-sent
