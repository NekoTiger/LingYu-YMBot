"""Numerical, contact-parameter and control-lifecycle regression checks."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
import mujoco
import numpy as np
from scipy.optimize import minimize
from .risk_allocation import ContactRisk, MotionAllocator, solve_allocation_qp
from .risk_model import risk_model
from .risk_engine import RiskEngine
from .test_protocol import sample

STATE=ContactRisk(0.,0.,0.,0.,.05,.05,[0.,0.],[0.,0.],1.)

class AllocationTests(unittest.TestCase):
    def test_qp_matches_independent_optimizer(self):
        rng=np.random.default_rng(152)
        for _ in range(80):
            M=rng.normal(size=(2,2)); H=M.T@M+np.eye(2)*.2; f=rng.normal(size=2)
            lower=rng.uniform(-.2,0,2); upper=rng.uniform(.01,.3,2)
            centre=(lower+upper)/2; lo=centre.sum()-.02; hi=centre.sum()+.02
            actual,relax=solve_allocation_qp(H,f,lower,upper,lo,hi)
            ref=minimize(lambda x:.5*x@H@x+f@x,centre,jac=lambda x:H@x+f,
                bounds=list(zip(lower,upper)),constraints=[{'type':'ineq','fun':lambda x:x.sum()-lo},
                {'type':'ineq','fun':lambda x:hi-x.sum()}],method='SLSQP',options={'ftol':1e-12,'maxiter':100})
            self.assertTrue(ref.success,ref.message)
            np.testing.assert_allclose(actual,ref.x,atol=2e-6)
            self.assertLess(relax,1e-8)

    def test_infeasible_sum_is_explicit(self):
        x,relax=solve_allocation_qp(np.eye(2),np.zeros(2),[0,0],[.1,.1],.5,.6)
        np.testing.assert_allclose(x,[.1,.1]);self.assertAlmostEqual(relax,.3)
        _,relax=solve_allocation_qp(np.eye(2),np.zeros(2),[0,0],[.1,.1],-1,1)
        self.assertEqual(relax,0.)

    def test_both_risks_have_distinct_control_effects(self):
        traces={}
        for key,state in [('none',STATE),('grip',replace(STATE,grip=1.)),('payload',replace(STATE,payload=1.))]:
            allocator=MotionAllocator('dual');rows=[]
            for _ in range(40):
                allocator.allocate(.16,state);rows.append(allocator.snapshot())
            traces[key]=rows
        # A tighter arm bound need not imply smaller realized arm motion: a
        # slower base can need MORE compensation within that bound.
        self.assertLessEqual(max(abs(r['arm_relative_m_s']) for r in traces['grip']),.00375+1e-9)
        self.assertLess(traces['grip'][-1]['base_m_s'],traces['none'][-1]['base_m_s'])
        self.assertLess(traces['payload'][-1]['object_command_m_s'],traces['none'][-1]['object_command_m_s'])

    def test_ablations_ignore_only_the_removed_risk(self):
        for policy,a,b in [('grip_only',replace(STATE,grip=.6),replace(STATE,grip=.6,payload=1.)),
                           ('payload_only',replace(STATE,payload=.6),replace(STATE,payload=.6,grip=1.))]:
            first,second=MotionAllocator(policy),MotionAllocator(policy)
            for _ in range(100):
                np.testing.assert_allclose(first.allocate(.12,a),second.allocate(.12,b),atol=1e-12)

    def test_sum_acceleration_and_workspace(self):
        alloc=MotionAllocator('dual');state=replace(STATE,grip=.4,payload=.8)
        previous=0.
        for tick in range(500):
            alloc.allocate(.16 if tick<250 else -.16,state)
            self.assertLessEqual(abs(alloc.offset),.045+1e-9)
            allowed=.20*(1-.8*.8)*(1-.3*.4)*.01+alloc.metrics['sum_bound_relaxation_m_s']+1e-8
            self.assertLessEqual(abs(alloc.total-previous),allowed)
            previous=alloc.total

    def test_saturated_workspace_buffer_stays_feasible(self):
        for sign in (1., -1.):
            alloc=MotionAllocator('dual')
            state=replace(STATE,grip=1.)
            alloc.offset=.045*sign
            alloc.arm=.00375*sign
            for _ in range(60):
                alloc.allocate(.16*sign,state)
                self.assertLessEqual(abs(alloc.offset),.045+1e-9)
                self.assertLessEqual(abs(alloc.arm),.00375+1e-9)
            self.assertGreaterEqual(alloc.base*sign,0.)

    def test_contact_interfaces_independently_configured(self):
        for scenario,grip,surface in [('grip',.55,.8),('payload',1.1,.16)]:
            m,d,_,_=risk_model(True,9000,True,.75,scenario=scenario)
            for geom in ('cargo_left_handle','cargo_right_handle','left_finger1_pad','right_finger1_pad'):
                # Finger names are taken from the model below, not assumed by index.
                if geom.startswith('cargo'):
                    self.assertAlmostEqual(m.geom(geom).friction[0],grip)
            pads=[i for i in range(m.ngeom) if (m.geom(i).name or '').endswith('_pad')]
            self.assertGreaterEqual(len(pads),4)
            self.assertTrue(all(abs(m.geom_friction[i,0]-grip)<1e-9 for i in pads))
            for _ in range(100):mujoco.mj_step(m,d)
            contacts=[c for c in d.contact if set([m.geom(c.geom1).name,m.geom(c.geom2).name])=={'parcel_geom','cargo_main'}]
            self.assertGreater(len(contacts),0)
            self.assertTrue(all(abs(c.friction[0]-surface)<1e-9 for c in contacts))

    def test_stop_and_reclutch_do_not_preserve_motion(self):
        with tempfile.TemporaryDirectory() as folder:
            engine=RiskEngine(Path(folder)/'trial')
            try:
                clock=engine.started
                engine.receive(sample(0,0,squeeze=0),clock);engine.step(clock)
                engine.receive(sample(1,.01,squeeze=1),clock+.01);engine.step(clock+.01)
                engine.allocator.base=.1;engine.allocator.arm=.02;engine.allocator.offset=.01
                engine.stop();engine.step(clock+.02)
                np.testing.assert_array_equal(engine.twist,[0,0])
                self.assertFalse(engine.active)
                engine.receive(sample(2,.03,squeeze=0),clock+.03);self.assertTrue(engine.clear_stop());engine.step(clock+.03)
                engine.receive(sample(3,.04,squeeze=1),clock+.04);engine.step(clock+.04)
                self.assertEqual(engine.allocator.offset,0.)
                engine.step(clock+1.)
                np.testing.assert_array_equal(engine.twist,[0,0]);self.assertFalse(engine.active)
            finally:engine.close()

if __name__=='__main__':unittest.main()
