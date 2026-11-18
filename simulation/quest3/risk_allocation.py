"""Two-contact observation and a bounded two-variable convex motion allocator.

An empirical research controller, not a proof of safe contact. Sensing uses
ideal simulated forces and geometry; the optimizer does not inspect future states.
"""
from dataclasses import asdict, dataclass
import time

import mujoco
import numpy as np


@dataclass
class ContactRisk:
    grip: float
    payload: float
    grip_utilization: float
    hand_slip_m: float
    edge_margin_m: float
    predicted_edge_margin_m: float
    parcel_offset: list
    parcel_relative_velocity: list
    parcel_support_n: float


class RiskObserver:
    def __init__(self):
        self.previous_offset = None
        self.velocity = np.zeros(2)
        self.filtered = np.zeros(2)
        self.state = ContactRisk(0., 0., 0., 0., .05, .05, [0., 0.], [0., 0.], 0.)

    def update(self, model, data, assistance, dt=.01):
        normal = np.zeros(2)
        tangent = np.zeros(2)
        capacity = np.zeros(2)
        support = 0.
        for index, contact in enumerate(data.contact):
            names = [model.geom(contact.geom1).name or '', model.geom(contact.geom2).name or '']
            if not any(name.startswith('cargo_') for name in names):
                continue
            force = np.zeros(6)
            mujoco.mj_contactForce(model, data, index, force)
            for i, side in enumerate(('left', 'right')):
                if any(name.startswith(side+'_finger') for name in names):
                    normal[i] += max(0., force[0])
                    tangent[i] += np.linalg.norm(force[1:3])
                    capacity[i] += max(0., force[0])*contact.friction[0]
            if 'cargo_main' in names and 'parcel_geom' in names:
                support += max(0., force[0])
        utilization = float(np.max(tangent/np.maximum(capacity, .05)))
        cargo = data.body('cargo')
        rot = cargo.xmat.reshape(3, 3)
        offset = (rot.T@(data.body('parcel').xpos-cargo.xpos))[:2]
        if self.previous_offset is not None:
            self.velocity += (1-np.exp(-dt/.06))*((offset-self.previous_offset)/dt-self.velocity)
        self.previous_offset = offset.copy()
        # Project actual parcel footprint into tray coordinates. Edge clearance
        # measures the entire footprint rather than only its centre.
        rel_rot = rot.T@data.body('parcel').xmat.reshape(3, 3)
        extent = np.abs(rel_rot[:2])@model.geom('parcel_geom').size
        half = model.geom('cargo_main').size[:2]
        margin = float(np.min(half-extent-np.abs(offset)))
        predicted_margin = float(np.min(half-extent-np.abs(offset+.25*self.velocity)))
        grip_raw = max(np.clip((utilization-.65)/.35, 0., 1.),
                       np.clip((assistance.slip-.003)/.012, 0., 1.),
                       np.clip(assistance.slip_rate/.025, 0., 1.),
                       float(np.any(normal < 1.))) if assistance.grasped else 0.
        payload_raw = max(np.clip((.035-predicted_margin)/.035, 0., 1.),
                          np.clip(np.linalg.norm(self.velocity)/.08, 0., 1.)) if assistance.grasped else 0.
        self.filtered += (1-np.exp(-dt/.08))*(np.array([grip_raw, payload_raw])-self.filtered)
        self.state = ContactRisk(float(self.filtered[0]), float(self.filtered[1]), utilization,
                                 assistance.slip, margin, predicted_margin, offset.tolist(),
                                 self.velocity.tolist(), float(support))
        return self.state


def solve_allocation_qp(H, f, lower, upper, total_lower, total_upper):
    """Exact active-set enumeration in 2D (box plus sum interval).

    Tests compare against an independent constrained optimizer. The envelope
    relaxes ONLY the sum interval when it conflicts with actuator/arm bounds;
    that relaxation is returned and logged, never hidden as a safety guarantee.
    """
    lower, upper = np.asarray(lower), np.asarray(upper)
    if np.any(lower > upper):
        raise ValueError('Empty actuator/arm bounds')
    feasible_lo, feasible_hi = float(lower.sum()), float(upper.sum())
    lo = float(np.clip(total_lower, feasible_lo, feasible_hi))
    hi = float(np.clip(total_upper, feasible_lo, feasible_hi))
    if hi < lo:
        hi = lo
    A = np.array([[1., 0.], [-1., 0.], [0., 1.], [0., -1.], [1., 1.], [-1., -1.]])
    b = np.array([upper[0], -lower[0], upper[1], -lower[1], hi, -lo])
    inv = np.linalg.inv(H)
    optimum = -inv@f
    directions = A@inv
    den = np.einsum('ij,ij->i', A, directions)
    candidates = [optimum, *(optimum-directions*((A@optimum-b)/den)[:, None])]
    for i in range(6):
        for j in range(i+1, 6):
            system = A[[i, j]]
            if abs(np.linalg.det(system)) > 1e-10:
                candidates.append(np.linalg.solve(system, b[[i, j]]))
    candidates = np.asarray(candidates)
    candidates = candidates[np.all(candidates@A.T <= b+1e-9, axis=1)]
    if not len(candidates):
        raise RuntimeError('No feasible 2D allocation candidate')
    costs = .5*np.einsum('ni,ij,nj->n', candidates, H, candidates)+candidates@f
    solution = candidates[int(np.argmin(costs))]
    relaxation = max(0., total_lower-float(solution.sum()), float(solution.sum())-total_upper)
    return solution, relaxation


class MotionAllocator:
    POLICIES = ('fixed', 'grip_only', 'payload_only', 'dual', 'slow')

    def __init__(self, policy='dual'):
        if policy not in self.POLICIES:
            raise ValueError('Unknown risk policy')
        self.policy = policy
        self.offset = 0.
        self.base = 0.
        self.arm = 0.
        self.total = 0.
        self.metrics = {}
        self.solve_ms = []

    def reset(self):
        self.offset = self.base = self.arm = self.total = 0.

    def allocate(self, requested, state, dt=.01):
        start = time.perf_counter()
        rg = state.grip if self.policy in ('dual', 'grip_only') else 0.
        rp = state.payload if self.policy in ('dual', 'payload_only') else 0.
        if self.policy in ('fixed', 'slow'):
            wanted = requested*(.55 if self.policy == 'slow' else 1.)
            base = self.base+float(np.clip(wanted-self.base, -.2*dt, .2*dt))
            solution, relaxation = np.array([base, 0.]), 0.
        else:
            # Preserve object-space intent v_object = v_base + v_arm(relative).
            # Grip risk discourages relative arm motion; payload risk penalizes
            # abrupt base changes, while a shared acceleration envelope also
            # constrains their SUM so arm compensation cannot defeat deceleration.
            max_arm = .025*(1-.85*rg)
            max_base_acc = .20*(1-.75*rg)
            lower = [-.16, max(-max_arm, (-.045-self.offset)/dt)]
            upper = [.16, min(max_arm, (.045-self.offset)/dt)]
            lower[1] = max(lower[1], float(np.clip(self.arm-.08*dt,-max_arm,max_arm)))
            upper[1] = min(upper[1], float(np.clip(self.arm+.08*dt,-max_arm,max_arm)))
            lower[0] = max(lower[0], self.base-max_base_acc*dt)
            upper[0] = min(upper[0], self.base+max_base_acc*dt)
            horizon = .40
            weights = (45., .15+5.*rg, .5+12.*rp, .3, 15.)
            H = np.zeros((2, 2))
            f = np.zeros(2)
            terms = [(weights[0], [1., 1.], requested),
                     (weights[1], [0., 1.], 0.),
                     (weights[2], [1., 0.], self.base),
                     (weights[3], [0., 1.], self.arm),
                     (weights[4], [0., horizon], -self.offset)]
            for weight, vector, target in terms:
                vector = np.asarray(vector)
                H += 2*weight*np.outer(vector, vector)
                f -= 2*weight*target*vector
            accel = .20*(1-.8*rp)*(1-.3*rg)
            solution, relaxation = solve_allocation_qp(H, f, lower, upper,
                                                       self.total-accel*dt, self.total+accel*dt)
        self.base, self.arm = map(float, solution)
        self.offset = float(np.clip(self.offset+self.arm*dt, -.045, .045))
        self.total = self.base+self.arm
        cost_ms = (time.perf_counter()-start)*1000
        self.solve_ms.append(cost_ms)
        self.metrics = {'policy': self.policy, 'requested_m_s': float(requested),
                        'base_m_s': self.base, 'arm_relative_m_s': self.arm,
                        'object_command_m_s': self.total, 'arm_offset_m': self.offset,
                        'intent_error_m_s': self.total-requested, 'grip_risk_used': rg,
                        'payload_risk_used': rp, 'sum_bound_relaxation_m_s': float(relaxation),
                        'solver_ms': cost_ms}
        return self.base, self.arm

    def snapshot(self):
        return self.metrics.copy()
