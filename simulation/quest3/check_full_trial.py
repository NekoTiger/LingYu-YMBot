"""Synthetic pose-stream regression through the new live controller and scorer."""
import argparse
import json
import time
from pathlib import Path

import numpy as np

from .engine import Engine
from .study import configuration
from .test_protocol import sample
from experiment import base_pose, wrap


def run(index=3):
    config = configuration('P01', index, 'pilot')
    root = Path(__file__).resolve().parent/'outputs'/(time.strftime('full_trial_%Y%m%d_%H%M%S')+f'_{index}')
    engine = Engine(root, mode=config['mode'], target_height=config['target_height'], seed=config['seed'], trial_config=config)
    engine.connect('synthetic_transport_test', 'closed-loop synthetic pose generator')
    engine.recorder.meta['clock_mode'] = 'synthetic_fixed_step; not a human performance measurement'
    clock = engine.started
    engine.trial.start(engine, clock)
    anchor = np.mean(engine.observation.hand_positions, axis=0)[2]
    carry_height = max(.86, config['target_height']+.14)
    shift = 0.
    trigger = 0.
    phase = 'calibrate'
    phase_start = 0.
    route = [(-.90, 0., 0., False, True), (-.90, 0., np.pi/2, True, False),
             (-.90, engine.info['distance'], np.pi/2, False, False),
             (-.90, engine.info['distance'], 0., True, False),
             (0., engine.info['distance'], 0., False, False), (0., engine.info['distance'], 0., True, False)]
    route_index = 0
    events = []
    def transition(name, tick):
        nonlocal phase, phase_start
        phase, phase_start = name, tick*.01
        events.append({'time': phase_start, 'phase': phase})
        print(f'{config["mode"]} {config["scene"]} {phase_start:.2f} {name}', flush=True)
    try:
        for tick in range(24000):
            t = tick*.01
            elapsed = t-phase_start
            stick = [0., 0.]
            if phase == 'calibrate' and elapsed > .4:
                transition('approach', tick)
            elif phase == 'approach':
                shift = (engine.info['grasp_z']-anchor)/.8
                if elapsed > 3.:
                    transition('close', tick)
            elif phase == 'close':
                trigger = 1.
                if elapsed > 2.5:
                    transition('lift', tick)
            elif phase == 'lift':
                shift = (carry_height-anchor)/.8
                if elapsed > 3.5:
                    transition('navigate', tick)
            elif phase == 'navigate':
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
                if done:
                    route_index += 1
                    if route_index == len(route):
                        transition('lower', tick)
                else:
                    stick = [-float(angular)/.4, -float(velocity)/.16]
            elif phase == 'lower':
                shift = (config['target_height']+.073-anchor)/.8
                if elapsed > 3.:
                    transition('release', tick)
            elif phase == 'release':
                trigger = 0.
                if elapsed > 3.:
                    transition('retreat', tick)
            elif phase == 'retreat':
                shift = (config['target_height']+.18-anchor)/.8
            if tick%2 == 0:
                engine.receive(sample(tick, t, squeeze=0 if t<.2 else 1, trigger=trigger,
                                      shift=(0, shift, 0), stick=stick), clock+t)
            engine.step(clock+t)
            if engine.trial.result:
                break
        result = engine.trial.result
        (root/'generator_events.json').write_text(json.dumps(events, indent=2), encoding='utf-8')
        print(json.dumps({k:result[k] for k in ('mode','scene','outcome','reason','max_lift_m','elapsed_sim_s')}, indent=2))
        print(root)
        assert result['outcome'] == 'success'
    finally:
        engine.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--index', type=int, default=3)
    run(**vars(parser.parse_args()))
