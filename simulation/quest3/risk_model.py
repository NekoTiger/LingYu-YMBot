"""Independent grip and tray-surface contacts for two-interface experiments."""
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

from .engine import make_model


SCENARIOS = {
    'normal': {'grip_mu': 1.1, 'surface_mu': .8, 'parcel_offset': [0., 0.], 'load_scale': 1.},
    'grip': {'grip_mu': .55, 'surface_mu': .8, 'parcel_offset': [0., 0.], 'load_scale': 1.15},
    'payload': {'grip_mu': 1.1, 'surface_mu': .16, 'parcel_offset': [.035, 0.], 'load_scale': 1.},
    'combined': {'grip_mu': .55, 'surface_mu': .16, 'parcel_offset': [.035, 0.], 'load_scale': 1.15},
}


def risk_model(scene, seed, obstacle, target_height, *, scenario='normal'):
    settings = SCENARIOS[scenario]
    _, _, info, xml = make_model(scene, seed, obstacle, target_height, load_scale=settings['load_scale'])
    tree = ET.fromstring(xml)
    for geom in tree.iter('geom'):
        name = geom.get('name', '')
        if name.endswith('_pad') or name.endswith('_handle'):
            geom.set('friction', f'{settings["grip_mu"]} .02 .002')
            geom.set('priority', '1')
        if name == 'cargo_main':
            # Both surfaces must change: MuJoCo's equal-priority rule uses max(mu).
            geom.set('friction', f'{settings["surface_mu"]} .01 .001')
            geom.set('priority', '1')
        if name == 'parcel_geom':
            geom.set('friction', f'{settings["surface_mu"]} .01 .001')
            geom.set('priority', '1')
    parcel = next(body for body in tree.iter('body') if body.get('name') == 'parcel')
    pos = np.fromstring(parcel.get('pos'), sep=' ')
    pos[:2] += settings['parcel_offset']
    parcel.set('pos', ' '.join(map(str, pos)))
    xml = ET.tostring(tree, encoding='unicode')
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    info.update(risk_scenario=scenario, risk_settings=settings.copy())
    return model, data, info, xml
