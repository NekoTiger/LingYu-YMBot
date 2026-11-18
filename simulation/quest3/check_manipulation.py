"""Synthetic WebXR intent -> contact pickup, short wheel motion, source return.

This is an interface regression check, never a human trial / unseen-task score.
"""
import argparse,json,time
from pathlib import Path
import numpy as np
import mujoco
from .engine import Engine
from .test_protocol import sample
from experiment import contacts,base_pose

def run(mode='legacy'):
    out=Path(__file__).resolve().parent/'outputs'/(time.strftime('manipulation_%Y%m%d_%H%M%S')+'_'+mode);out.mkdir(parents=True,exist_ok=False)
    e=Engine(out/'session',mode=mode);e.connect('synthetic_transport_test','offline synthetic regression; no headset')
    e.recorder.meta['clock_mode']='synthetic_control_clock_for_offline_regression; wall_elapsed is not measured wall time'
    start=e.started;tick=0;rows=[]
    def advance(seconds,shift=0.,trigger=0.,squeeze=1.,base_goal=None):
        nonlocal tick
        for _ in range(round(seconds/.01)):
            clock=start+tick*.01
            if tick%2==0:
                stick=0. if base_goal is None else float(np.clip(-(base_goal-base_pose(e.d)[0])*15,-1,1))
                e.receive(sample(tick,tick*.01,squeeze,trigger,(0,shift,0),(0,stick)),clock)
            e.step(clock);tick+=1
            count,force,bad=contacts(e.m,e.d)
            rows.append([e.d.time,*e.d.body('cargo').xpos,*base_pose(e.d),*count,*force,bad,e.aperture])
    try:
        advance(.2,squeeze=0);advance(.2)
        original=e.d.body('cargo').xpos.copy();base0=base_pose(e.d)[0];anchor=np.mean([e.d.site(s+'_ee').xpos[2]for s in ['left','right']])
        down=(e.info['grasp_z']-anchor)/.8;up=(.88-anchor)/.8
        advance(2.6,down);advance(2.4,down,1)
        count,force,_=contacts(e.m,e.d);grasp_ok=bool(np.all(count>=2)and np.all(force>3))
        advance(3.2,up,1)
        lift=float(e.d.body('cargo').xpos[2]-original[2]);lift_ok=lift>.09
        advance(2.4,up,1,base_goal=base0-.08);travel=abs(float(base_pose(e.d)[0]-base0))
        advance(2.4,up,1,base_goal=base0);advance(.5,up,1)
        advance(3.,down,1);advance(2.,down,0);advance(2.5,up,0);advance(.6,up,0,squeeze=0)
        cargo=e.d.body('cargo').xpos.copy();offset=e.d.body('cargo').xmat.reshape(3,3).T@(e.d.body('parcel').xpos-cargo)
        supported=any({'source_top','cargo_main'}<=set([e.m.geom(c.geom1).name,e.m.geom(c.geom2).name])for c in e.d.contact)
        count,force,_=contacts(e.m,e.d)
        retained=bool(abs(offset[0])<.09 and abs(offset[1])<.34 and .03<offset[2]<.12)
        np.savetxt(out/'measurements.csv',rows,delimiter=',',header='sim_time,cargo_x,cargo_y,cargo_z,base_x,base_y,base_yaw,left_contacts,right_contacts,left_force,right_force,obstacle_contacts,aperture',comments='')
        checks={'source':'synthetic_transport_test','hardware_verified':False,'control_mode':mode,'task':'pickup, 8 cm reverse, return, place on source table',
            'grasp_contacts_verified':grasp_ok,'lift_m':lift,'lift_verified':lift_ok,'base_travel_m':travel,
            'final_source_support':bool(supported),'final_hand_contacts':int(sum(count)),'parcel_retained':retained,
            'final_cargo_position':cargo.tolist(),'simulated_seconds':e.d.time,'calibrations':e.calibrations}
        checks['passed']=bool(grasp_ok and lift_ok and travel>.05 and supported and sum(count)==0 and retained)
        (out/'report.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(checks,ensure_ascii=False,indent=2));print('Output:',out)
        assert checks['passed'],'Inspect physical check report; never label this a human demonstration.'
    finally:e.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=['legacy','baseline','assisted'],default='legacy');run(**vars(parser.parse_args()))
