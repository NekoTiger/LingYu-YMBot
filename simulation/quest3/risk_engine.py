"""Two-interface research mode on the existing live WebXR/physics engine."""
from dataclasses import asdict
from functools import partial
import json

import numpy as np

from .engine import Engine
from .risk_model import risk_model
from .risk_allocation import MotionAllocator, RiskObserver


class RiskEngine(Engine):
    def __init__(self, record_root=None, policy='dual', scenario='normal', target_height=.75,
                 seed=9000, trial_config=None):
        self.allocator = MotionAllocator(policy)
        self.risk_observer = RiskObserver()
        super().__init__(record_root, mode='follow', target_height=target_height, seed=seed,
                         trial_config=trial_config, model_factory=partial(risk_model, scenario=scenario))
        self.recorder.meta.update(risk_policy=policy, risk_version='20261117-dual-contact-v1',
                                 risk_sensing='ideal simulated contact forces and relative object states; no real sensors')
        self.risk_file = (self.recorder.root/'risk_control.jsonl').open('w', encoding='utf-8')
        self.risk_rows = []
        self.previous_risk_velocity = 0.
        self.allocation_active = False
        self.parcel_loss_s = 0.

    def on_calibrate(self):
        self.allocator.reset()

    def shape_hand_goal(self, wanted):
        wanted = wanted.copy()
        wanted[:, 0] += self.allocator.offset
        return wanted

    def allocate_motion(self, desired, pose):
        obs = self.observation
        airborne = obs.source_support_n+obs.destination_support_n < .1*(self.info['mass']+.17)*9.81
        active = (self.assistance.grasped and airborne and self.assistance.placement_target is None
                  and self.aperture_goal <= .004)
        self.allocation_active = active
        if not active:
            self.allocator.base = self.twist[0]
            self.allocator.arm = 0.
            self.allocator.total = self.twist[0]
            return
        old_offset = self.allocator.offset
        vb, va = self.allocator.allocate(float(desired[0]), self.risk_observer.state)
        # A recentering optimizer may move the base even for zero net intent.
        # Recheck the selected base motion, so it cannot bypass the common
        # geometric brake. A brake override is observable in the log.
        safe_vb = self.proximity.limit(self.d, vb, pose[2], self.twist[0])
        self.allocator.base = safe_vb
        self.allocator.total = safe_vb+va
        self.allocator.metrics.update(base_m_s=safe_vb, object_command_m_s=safe_vb+va,
            intent_error_m_s=safe_vb+va-float(desired[0]), proximity_override_m_s=safe_vb-vb)
        self.twist[0] = safe_vb
        # The arm-buffer increment is applied once, in the current base frame.
        # Carry it into the filter state to avoid cancelling it next frame.
        increment = self.allocator.offset-old_offset
        self.local[:, 0] += increment
        self.filtered_goal[:, 0] += increment

    def after_observe(self, now):
        state = self.risk_observer.update(self.m, self.d, self.assistance)
        row = {'sim_time': float(self.d.time), 'active': self.active,
               'allocation_active': self.active and self.allocation_active,
               **asdict(state), **self.allocator.snapshot()}
        self.risk_rows.append(row)
        if len(self.risk_rows) >= 100:
            self.flush_risk()
        if self.trial and self.trial.status=='running' and self.trial.lifted:
            # A fallen parcel may land on the chassis instead of the floor.
            # Do not keep transporting an empty tray until the generic timeout.
            cargo=self.d.body('cargo')
            relative=cargo.xmat.reshape(3,3).T@(self.d.body('parcel').xpos-cargo.xpos)
            separated=(abs(relative[0])>.123 or abs(relative[1])>.39 or relative[2]<.015)
            lost=separated and state.parcel_support_n<.1
            self.parcel_loss_s=self.parcel_loss_s+.01 if lost else 0.
            if self.parcel_loss_s>=.2:
                self.trial.finish(self,'failure','parcel_left_tray',now)

    def flush_risk(self):
        for row in self.risk_rows:
            self.risk_file.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+'\n')
        self.risk_file.flush()
        self.risk_rows.clear()

    def snapshot(self):
        result = super().snapshot()
        result['risk_allocation'] = {**asdict(self.risk_observer.state), **self.allocator.snapshot(),
                                     'policy': self.allocator.policy,'scenario':self.info['risk_scenario']}
        return result

    def close(self):
        self.flush_risk()
        self.risk_file.close()
        if self.allocator.solve_ms:
            self.recorder.meta['allocation_runtime_ms'] = {
                'median': float(np.median(self.allocator.solve_ms)),
                'p95': float(np.percentile(self.allocator.solve_ms,95)),
                'max': float(max(self.allocator.solve_ms))}
        super().close()
