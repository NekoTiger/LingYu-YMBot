"""Scripted closed-loop task evaluation; never labels scripts as human trials."""
import argparse
import json
import time
from pathlib import Path

import numpy as np

from .engine import Engine
from .follow_study import configuration
from .test_protocol import sample
from experiment import base_pose, wrap


def run(root, policy='gated', height=.75, seed=7100, noise_mm=0., engine_factory=None, trial_config=None):
    root = Path(root)
    config = trial_config or configuration(policy, height, seed)
    engine = engine_factory(root, config) if engine_factory else Engine(root, mode='follow', target_height=height, seed=seed,
                    trial_config=config, follow_policy=policy)
    engine.connect('synthetic_transport_test', 'scripted waypoint operator; not a human participant')
    engine.recorder.meta['clock_mode'] = 'synthetic_fixed_step; not a human performance measurement'
    engine.recorder.meta['input_noise_mm'] = noise_mm
    clock = engine.started
    engine.trial.start(engine, clock)
    anchor_z = np.mean(engine.observation.hand_positions, axis=0)[2]
    anchor_x = np.mean(engine.observation.hand_positions, axis=0)[0]
    carry_height = max(.86, height+.14)
    shift_y, shift_z, trigger = 0., 0., 0.
    phase, phase_start = 'calibrate', 0.
    route = [(-.90, 0., 0., False, True), (-.90, 0., np.pi/2, True, False),
             (-.90, engine.info['distance'], np.pi/2, False, False),
             (-.90, engine.info['distance'], 0., True, False),
             (0., engine.info['distance'], 0., False, False), (0., engine.info['distance'], 0., True, False)]
    route_index = 0
    events, measurements = [], []
    neutral_until = 0.
    rng = np.random.default_rng(seed+90000)
    manual_s = 0.
    steering = False
    def transition(name, tick):
        nonlocal phase, phase_start
        phase, phase_start = name, tick*.01
        events.append({'time': phase_start, 'phase': phase})
        print(f'{policy} {height} {seed} {phase_start:.2f} {name}', flush=True)
    try:
        for tick in range(24002):
            t = tick*.01
            elapsed = t-phase_start
            stick = [0., 0.]
            shift_z = 0.
            if phase == 'calibrate' and elapsed > .4:
                transition('approach', tick)
            elif phase == 'approach':
                shift_y = (engine.info['grasp_z']-anchor_z)/.8
                if elapsed > 3.:
                    transition('close', tick)
            elif phase == 'close':
                trigger = 1.
                if elapsed > 2.5:
                    transition('lift', tick)
            elif phase == 'lift':
                shift_y = (carry_height-anchor_z)/.8
                if elapsed > 3.5:
                    transition('navigate', tick)
            elif phase == 'navigate' and t >= neutral_until:
                x, y, yaw, turn, reverse = route[route_index]
                pose = base_pose(engine.d)
                if turn:
                    error = wrap(yaw-pose[2])
                    done = abs(error) < .015 and abs(engine.d.qvel[5]) < .04
                    velocity = 0.
                    angular = np.clip(2.5*error, -.4, .4)
                    if not done and abs(angular) < .08:
                        angular = .08*np.sign(error)
                else:
                    delta = np.array([x, y])-pose[:2]
                    distance = np.linalg.norm(delta)
                    heading = np.arctan2(delta[1], delta[0])+(np.pi if reverse else 0.)
                    error = wrap(heading-pose[2])
                    done = distance < .012
                    velocity = (-1. if reverse else 1.)*min(.16, max(.045, 1.2*distance))*max(0., np.cos(error))
                    angular = np.clip(2.5*error, -.4, .4)
                    # Turn-to-align with hysteresis, rather than alternating one
                    # joystick packet and one hand-follow packet at a deadzone edge.
                    if steering and abs(error) < .02:
                        steering = False
                    elif abs(error) > .10:
                        steering = True
                    if steering:
                        velocity = 0.
                        if abs(angular) < .08:
                            angular = .08*np.sign(error)
                    else:
                        angular = 0.
                if done:
                    route_index += 1
                    neutral_until = t+.55
                    if route_index == len(route):
                        transition('lower', tick)
                elif policy == 'off' or turn or steering:
                    stick = [-float(angular)/.4, -float(velocity)/.16]
                elif engine.follow.armed:
                    edge = engine.follow.origin_x+(.08 if velocity > 0 else -.08)
                    raw_x = edge+np.sign(velocity)*max(.002, (abs(velocity)-.025)/2.)
                    shift_z = -(raw_x-anchor_x)/.8
            elif phase == 'lower':
                shift_y = (height+.073-anchor_z)/.8
                if elapsed > 3.:
                    transition('release', tick)
            elif phase == 'release':
                trigger = 0.
                if elapsed > 3.:
                    transition('retreat', tick)
            elif phase == 'retreat':
                shift_y = (height+.18-anchor_z)/.8
            if tick%2 == 0:
                noise = rng.normal(0, noise_mm/1000.) if phase == 'navigate' else 0.
                engine.receive(sample(tick, t, squeeze=0 if t<.2 else 1, trigger=trigger,
                                      shift=(0, shift_y, shift_z+noise), stick=stick), clock+t)
            engine.step(clock+t)
            if phase == 'navigate':
                manual_s += .01*bool(np.any(np.abs(stick)>.15))
                measurements.append([t, *base_pose(engine.d), engine.observation.cargo_tilt_rad,
                                     engine.assistance.slip, *engine.d.qpos[engine.ik.torso_qids],
                                     *engine.twist, engine.follow.speed, engine.proximity.scale])
            if engine.trial.result:
                break
        result = dict(engine.trial.result or {'outcome': 'incomplete', 'reason': 'loop_exhausted'})
        values = np.asarray(measurements)
        result.update(input_kind='scripted_waypoint_operator_not_human', input_noise_mm=noise_mm,
                      joystick_command_sim_s=manual_s,
                      navigation_max_tilt_deg=float(np.rad2deg(values[:, 4].max())) if len(values) else None,
                      navigation_max_slip_mm=float(values[:, 5].max()*1000) if len(values) else None,
                      navigation_waist_range_deg=float(np.rad2deg(np.ptp(values[:, 6:9], axis=0)).max()) if len(values) else None)
        (root/'generator_events.json').write_text(json.dumps(events, indent=2), encoding='utf-8')
        (root/'benchmark_result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        np.savez_compressed(root/'navigation.npz', values=values,
                            columns=['time','x','y','yaw','tilt','slip','waist1','waist2','waist3','v','w','follow_request','brake_scale'])
        print(json.dumps({k: result.get(k) for k in ('outcome','reason','elapsed_sim_s','joystick_command_sim_s','navigation_max_tilt_deg')}, ensure_ascii=False), flush=True)
        return result
    finally:
        engine.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--policy', choices=['off','threshold','gated'], default='gated')
    parser.add_argument('--height', type=float, default=.75)
    parser.add_argument('--seed', type=int, default=7100)
    parser.add_argument('--noise-mm', type=float, default=0.)
    args = parser.parse_args()
    run(**vars(args))
