"""Shared physical observations and prospective pick/carry/place trial scoring."""
import json
import time
from dataclasses import asdict, dataclass

import mujoco
import numpy as np


@dataclass
class Observation:
    hand_contacts: list
    hand_forces: list
    source_support_n: float
    destination_support_n: float
    obstacle_contacts: int
    cargo_position: list
    cargo_tilt_rad: float
    cargo_linear_speed: float
    cargo_angular_speed: float
    parcel_retained: bool
    parcel_height: float
    hand_positions: list


def observe(model, data):
    counts = [0, 0]
    forces = [0., 0.]
    support = {'source_top': 0., 'destination_top': 0.}
    forbidden = 0
    for index, contact in enumerate(data.contact):
        names = [model.geom(contact.geom1).name or '', model.geom(contact.geom2).name or '']
        if any(name.startswith('aisle_obstacle') for name in names):
            if any(name.startswith(('base_collision', 'left_arm', 'right_arm', 'cargo_', 'left_finger', 'right_finger', 'left_palm', 'right_palm')) for name in names):
                forbidden += 1
        if not any(name.startswith('cargo_') for name in names):
            continue
        force = np.zeros(6)
        mujoco.mj_contactForce(model, data, index, force)
        for side_index, side in enumerate(('left', 'right')):
            if any(name.startswith(side + '_finger') for name in names):
                counts[side_index] += 1
                forces[side_index] += max(0., float(force[0]))
        if 'cargo_main' in names:
            world_force = contact.frame.reshape(3, 3).T @ force[:3]
            cargo_id = model.geom('cargo_main').id
            if contact.geom1 == cargo_id:
                world_force = -world_force
            for table in support:
                if table in names:
                    support[table] += max(0., float(world_force[2]))
    cargo = data.body('cargo')
    rotation = cargo.xmat.reshape(3, 3)
    offset = rotation.T @ (data.body('parcel').xpos - cargo.xpos)
    velocity_address = int(model.joint('cargo_free').dofadr[0])
    return Observation(
        counts, forces, support['source_top'], support['destination_top'], forbidden,
        cargo.xpos.tolist(), float(np.arccos(np.clip(rotation[2, 2], -1, 1))),
        float(np.linalg.norm(data.qvel[velocity_address:velocity_address + 3])),
        float(np.linalg.norm(data.qvel[velocity_address + 3:velocity_address + 6])),
        bool(abs(offset[0]) < .09 and abs(offset[1]) < .34 and .03 < offset[2] < .12),
        float(data.body('parcel').xpos[2]),
        [data.site(side + '_ee').xpos.tolist() for side in ('left', 'right')])


class Trial:
    def __init__(self, engine, config):
        self.config = dict(config)
        self.status = 'ready'
        self.started_wall = None
        self.started_sim = None
        self.result = None
        self.grasp_hold = 0.
        self.stable_hold = 0.
        self.grasped = False
        self.lifted = False
        self.max_lift = 0.
        self.max_tilt = 0.
        self.waist_samples = []
        self.tracking_loss_seconds = 0.
        self.control_seconds = 0.
        self.start_calibrations = 0
        self.last_clock = None
        engine.recorder.meta['experiment'] = self.config

    def start(self, engine, now=None):
        if self.status != 'ready':
            raise ValueError('This trial has already started. Prepare the next trial.')
        if engine.recorder.meta['source'] != 'webxr_live' and self.config['phase'] == 'formal':
            raise ValueError('Formal trials require the live WebXR controller connection.')
        self.started_wall = time.monotonic() if now is None else now
        self.last_clock = self.started_wall
        self.started_sim = float(engine.d.time)
        self.start_calibrations = engine.calibrations
        self.status = 'running'
        engine.recorder.event('experiment_started', config=self.config, sim_time=engine.d.time)

    def update(self, engine, observation, now):
        if self.status != 'running':
            return
        wall_step = max(0., now - self.last_clock)
        self.last_clock = now
        cargo = np.asarray(observation.cargo_position)
        self.max_lift = max(self.max_lift, float(cargo[2] - engine.info['source_height'] - .020))
        self.max_tilt = max(self.max_tilt, observation.cargo_tilt_rad)
        contact_ok = all(n >= 2 for n in observation.hand_contacts) and all(f > 3 for f in observation.hand_forces)
        self.grasp_hold = self.grasp_hold + .01 if contact_ok else 0.
        self.grasped |= self.grasp_hold >= .2
        self.lifted |= self.grasped and self.max_lift >= .08
        if engine.status in ('tracking_lost', 'stale'):
            self.tracking_loss_seconds += wall_step
        if engine.active:
            self.control_seconds += wall_step
        if self.lifted and np.linalg.norm(engine.twist) > .01:
            ids = [int(engine.m.joint('Body_Joint' + str(j)).qposadr[0]) for j in (1, 2, 3)]
            self.waist_samples.append(engine.d.qpos[ids].copy())
        if observation.obstacle_contacts:
            self.finish(engine, 'failure', 'obstacle_collision', now)
            return
        if cargo[2] < engine.info['source_height'] - .15 or observation.parcel_height < .1:
            self.finish(engine, 'failure', 'payload_dropped', now)
            return
        goal = np.asarray(engine.info['goal'])
        supported = observation.destination_support_n > .65 * (engine.info['mass'] + .17) * 9.81
        withdrawn = min(p[2] for p in observation.hand_positions) > engine.info['target_height'] + .12
        stable = (self.grasped and self.lifted and supported and sum(observation.hand_contacts) == 0
                  and withdrawn and np.linalg.norm(cargo[:2] - goal[:2]) < .04 and abs(cargo[2] - goal[2]) < .012
                  and observation.cargo_linear_speed < .02 and observation.cargo_angular_speed < .1
                  and observation.cargo_tilt_rad < .12 and observation.parcel_retained)
        self.stable_hold = self.stable_hold + .01 if stable else 0.
        if self.stable_hold >= 1.:
            self.finish(engine, 'success', 'destination_support_release_retreat_stable', now)
        elif now - self.started_wall >= self.config['time_limit_s']:
            self.finish(engine, 'failure', 'timeout', now)

    def finish(self, engine, outcome, reason, now=None):
        if self.status != 'running':
            return
        now = time.monotonic() if now is None else now
        self.status = outcome
        waist_range = None
        if self.waist_samples:
            waist_range = float(np.rad2deg(np.ptp(self.waist_samples, axis=0)).max())
        self.result = {
            **self.config, 'outcome': outcome, 'reason': reason,
            'source': engine.recorder.meta['source'], 'sources_seen': engine.recorder.meta.get('sources_seen', []),
            'clock_mode': engine.recorder.meta.get('clock_mode', 'unspecified'),
            'elapsed_wall_s': now - self.started_wall, 'elapsed_sim_s': float(engine.d.time - self.started_sim),
            'grasp_verified': self.grasped, 'lift_verified': self.lifted, 'max_lift_m': self.max_lift,
            'max_tilt_deg': float(np.rad2deg(self.max_tilt)), 'waist_range_during_drive_deg': waist_range,
            'clutch_calibrations': engine.calibrations - self.start_calibrations,
            'tracking_loss_wall_s': self.tracking_loss_seconds, 'control_enabled_wall_s': self.control_seconds,
            'workspace_follow': engine.follow.snapshot(),
            'final_observation': asdict(engine.observation), 'session': str(engine.recorder.root),
            'result_authority': 'automatic_physical_criteria' if outcome == 'success' else 'failure_or_operator_abort'}
        engine.recorder.event('experiment_finished', result=self.result)
        engine.recorder.flush()
        (engine.recorder.root / 'trial_result.json').write_text(json.dumps(self.result, ensure_ascii=False, indent=2), encoding='utf-8')
        engine.stop('trial_' + outcome)

    def snapshot(self, now):
        elapsed = 0. if self.started_wall is None else now - self.started_wall
        if self.result:
            elapsed = self.result['elapsed_wall_s']
        brief = {key: self.config[key] for key in ('participant', 'phase', 'index', 'mode', 'scene', 'repeat', 'time_limit_s')}
        return {**brief, 'status': self.status, 'elapsed_s': round(elapsed, 1),
                'grasped': self.grasped, 'lifted': self.lifted, 'reason': self.result['reason'] if self.result else None}
