"""Separate, reproducible two-contact pilot protocol."""
import hashlib
from pathlib import Path
from .study import source_hashes
from .risk_allocation import MotionAllocator
from .risk_model import SCENARIOS

VERSION = '20261117-dual-contact-v1'
HERE = Path(__file__).resolve().parent

def hashes():
    result = source_hashes()
    for name in ('risk_allocation.py', 'risk_engine.py', 'risk_model.py', 'risk_protocol.py',
                 'risk_benchmark.py', 'risk_suite.py', 'follow_benchmark.py'):
        path = HERE/name
        if path.exists():
            result['quest3/'+name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result

def configuration(policy='dual', scenario='normal', height=.75, seed=9000):
    if policy not in MotionAllocator.POLICIES or scenario not in SCENARIOS or height not in (.60, .75):
        raise ValueError('Unsupported risk pilot condition')
    return dict(participant='P00', phase='pilot', index=1, repeat=1, mode='follow',
                risk_policy=policy, risk_scenario=scenario, scene='R'+scenario,
                target_height=height, seed=seed, time_limit_s=240,
                protocol_version=VERSION, source_sha256=hashes())
