"""Task-specific adaptation of Lin et al. (2026), arXiv:2607.16095, Eq. 5.

Original implementation, not the authors' code: differential drive, common
bimanual centre, neutral rearming, dwell/hysteresis and contact eligibility.
The hand extension is a rate command, NOT an autonomous navigation goal.
"""
from dataclasses import asdict, dataclass

import mujoco
import numpy as np


@dataclass(frozen=True)
class FollowParameters:
    lower: float = .42
    upper: float = .58
    hysteresis: float = .010
    dwell_s: float = .18
    neutral_s: float = .15
    filter_s: float = .06
    gain: float = 2.
    min_speed: float = .025
    max_speed: float = .16
    arm_lower: float = .49
    arm_upper: float = .51


class WorkspaceFollow:
    def __init__(self, policy='gated', parameters=None):
        if policy not in ('off', 'threshold', 'gated'):
            raise ValueError('Unknown workspace follow policy')
        self.policy = policy
        self.parameters = parameters or FollowParameters()
        self.origin_x = .50
        self.transitions = 0
        self.auto_seconds = 0.
        self.manual_seconds = 0.
        self.reset()

    def reset(self, reason='inactive'):
        self.armed = False
        self.neutral_time = 0.
        self.candidate = 0
        self.dwell = 0.
        self.direction = 0
        self.filtered_x = None
        self.speed = 0.
        self.state = reason

    def calibrate(self, center_x):
        self.origin_x = float(center_x)
        self.reset()

    def update(self, raw_x, *, eligible, manual=False, dt=.01):
        p = self.parameters
        raw_x = raw_x-self.origin_x+.50
        if manual:
            self.manual_seconds += dt
        if not eligible or manual or self.policy == 'off':
            self.reset('manual' if manual else ('off' if self.policy == 'off' else 'load_not_ready'))
            return 0.
        if not np.isfinite(raw_x):
            self.reset('invalid')
            return 0.
        self.filtered_x = float(raw_x) if self.filtered_x is None else (
            self.filtered_x + (1-np.exp(-dt/p.filter_s))*(raw_x-self.filtered_x))
        x = raw_x if self.policy == 'threshold' else self.filtered_x
        # Returning the actual hands to neutral cancels immediately, without filter tail.
        neutral = p.lower+p.hysteresis <= raw_x <= p.upper-p.hysteresis
        if not self.armed:
            self.neutral_time = self.neutral_time+dt if neutral else 0.
            self.armed = self.neutral_time >= p.neutral_s
            self.state = 'ready' if self.armed else 'return_to_center'
            self.speed = 0.
            return 0.
        candidate = 1 if x > p.upper else (-1 if x < p.lower else 0)
        old = self.direction
        if self.policy == 'threshold':
            self.direction = candidate
        else:
            if neutral or (self.direction == 1 and raw_x < p.upper-p.hysteresis) or (
                    self.direction == -1 and raw_x > p.lower+p.hysteresis):
                self.direction = 0
                self.candidate = 0
                self.dwell = 0.
            if self.direction == 0:
                self.dwell = self.dwell+dt if candidate and candidate == self.candidate else 0.
                self.candidate = candidate
                if candidate and self.dwell >= p.dwell_s:
                    self.direction = candidate
        self.transitions += int(old != self.direction)
        if self.direction:
            edge = p.upper if self.direction > 0 else p.lower
            self.speed = self.direction*min(p.max_speed, p.min_speed+p.gain*max(0., self.direction*(x-edge)))
            self.auto_seconds += dt
            self.state = 'forward' if self.direction > 0 else 'backward'
        else:
            self.speed = 0.
            self.state = 'confirming' if self.candidate else 'ready'
        return self.speed

    def snapshot(self):
        return {'policy': self.policy, 'state': self.state, 'requested_speed_m_s': self.speed,
                'neutral_center_x_m': self.origin_x,
                'transitions': self.transitions, 'automatic_command_sim_s': self.auto_seconds,
                'manual_command_sim_s': self.manual_seconds}

    def metadata(self):
        return {'policy': self.policy, 'parameters': asdict(self.parameters),
                'basis': 'arXiv:2607.16095 Eq.5; task-specific implementation, not full reproduction',
                'sensing': 'ideal simulated contact and geometry; no real obstacle perception'}


class ProximityBrake:
    """Ideal-geometry directional braking for automatic fore/aft motion only.

    Distance is queried from the current physical state. A conservative braking
    allowance is used; this is neither path planning nor a collision guarantee.
    """
    def __init__(self, model):
        self.model = model
        self.obstacles = [i for i in range(model.ngeom) if (model.geom(i).name or '').startswith(
            ('aisle_obstacle', 'source_top', 'destination_top'))]
        self.moving = [i for i in range(model.ngeom) if model.geom_contype[i] and
                       (model.geom(i).name or '').startswith(('base_collision', 'left_arm', 'right_arm',
                       'cargo_', 'left_finger', 'right_finger', 'left_palm', 'right_palm'))]
        self.scale = 1.

    def limit(self, data, velocity, heading, current_speed=0.):
        self.scale = 1.
        if abs(velocity) < 1e-9:
            return 0.
        direction = np.array([np.cos(heading), np.sin(heading), 0.])*np.sign(velocity)
        for obstacle in self.obstacles:
            for moving in self.moving:
                points = np.zeros(6)
                distance = mujoco.mj_geomDistance(self.model, data, moving, obstacle, .40, points)
                if distance >= .40:
                    continue
                delta = points[3:]-points[:3]
                closing = float(direction@delta/max(np.linalg.norm(delta), 1e-8))
                if closing <= .05:
                    continue
                # 40 mm margin plus 100 ms lag allowance and 0.12 m/s^2 braking.
                available = distance-.04-.10*abs(current_speed)*closing
                allowed = np.sqrt(2*.12*max(0., available))/closing
                self.scale = min(self.scale, float(np.clip(allowed/abs(velocity), 0., 1.)))
        return float(velocity*self.scale)
