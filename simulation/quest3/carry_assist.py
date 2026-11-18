"""Load feedback for the prospective human comparison. Both modes share mapping."""
import numpy as np


class CarryAssist:
    def __init__(self):
        self.grasped = False
        self.grasp_gap = .054
        self.grasp_hold = 0.
        self.support_hold = 0.
        self.previous_slip = 0.
        self.slip_rate = 0.
        self.slip = 0.
        self.speed_scale = 1.
        self.release_blocked = False
        self.placement_target = None
        self.placement_drop = 0.

    def reset_placement(self):
        self.placement_target = None
        self.placement_drop = 0.

    def placement_goal(self, wanted, observation, info, requested, aperture):
        if requested <= .004 or (aperture > .035 and sum(observation.hand_contacts) == 0):
            self.reset_placement()
            return wanted
        cargo = observation.cargo_position
        near_table = False
        for center_y, height in ((0., info['source_height']), (info['distance'], info['target_height'])):
            near_table |= (abs(cargo[0] - .50) < .15 and abs(cargo[1] - center_y) < .12
                           and -.01 < cargo[2] - .020 - height < .035)
        if self.grasped and near_table and self.placement_target is None:
            self.placement_target = wanted.copy()
        if self.placement_target is None:
            return wanted
        if self.support_hold < .2:
            self.placement_drop = min(.04, self.placement_drop + .008 * .01)
        target = self.placement_target.copy()
        target[:, 2] -= self.placement_drop
        return target

    def update(self, observation, mass, target_world, aperture):
        hands = np.asarray(observation.hand_positions)
        gap = float(hands[:, 2].mean() - observation.cargo_position[2])
        contact_ok = all(n >= 2 for n in observation.hand_contacts) and all(f > 3 for f in observation.hand_forces)
        self.grasp_hold = self.grasp_hold + .01 if contact_ok else 0.
        if not self.grasped and self.grasp_hold >= .2:
            self.grasped = True
            self.grasp_gap = gap
        if sum(observation.hand_contacts) == 0 and aperture > .035:
            self.grasped = False
        support = observation.source_support_n + observation.destination_support_n
        self.support_hold = self.support_hold + .01 if support > .65 * mass * 9.81 else 0.
        self.slip = max(0., gap - self.grasp_gap) if self.grasped else 0.
        self.slip_rate = .9 * self.slip_rate + .1 * (self.slip - self.previous_slip) / .01
        self.previous_slip = self.slip
        error = float(np.linalg.norm(hands - target_world, axis=1).max())
        self.speed_scale = float(np.clip(min((.05 - error) / .035, (.20 - observation.cargo_tilt_rad) / .14,
                                             (.03 - self.slip_rate) / .025), .25, 1.)) if self.grasped else 1.

    def aperture_target(self, requested, current):
        self.release_blocked = self.grasped and requested > .004 and self.support_hold < .2
        if self.release_blocked:
            return min(current, 0.)
        if self.grasped and requested <= .004:
            return requested - float(np.clip(2. * (self.slip - .001), 0., .020))
        return requested
