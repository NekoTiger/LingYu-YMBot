"""Separate pilot, not a silent change to the existing formal study."""
from .study import source_hashes


def configuration(policy='gated', height=.75, seed=7100):
    if policy not in ('off', 'threshold', 'gated') or height not in (.60, .75):
        raise ValueError('Unsupported follow pilot condition')
    return {'participant': 'P00', 'phase': 'pilot', 'index': 1, 'repeat': 1,
            'mode': 'follow', 'follow_policy': policy, 'scene': 'F60' if height == .60 else 'F75',
            'target_height': height, 'seed': seed, 'time_limit_s': 240,
            'protocol_version': '20261117-workspace-follow-pilot3', 'source_sha256': source_hashes()}
