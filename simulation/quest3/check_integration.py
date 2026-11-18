"""Actual HTTP/WebSocket + MuJoCo test, using explicitly synthetic input."""
import asyncio,json,tempfile,time
from pathlib import Path
import numpy as np
from aiohttp import ClientSession,web
from .server import Gateway
from .test_protocol import sample

async def run():
    out=Path(__file__).resolve().parent/'outputs'/time.strftime('transport_%Y%m%d_%H%M%S');out.mkdir(parents=True,exist_ok=False)
    gateway=Gateway(out/'session');runner=web.AppRunner(gateway.app());await runner.setup()
    site=web.TCPSite(runner,'127.0.0.1',0);await site.start();port=site._server.sockets[0].getsockname()[1];base=f'http://127.0.0.1:{port}'
    seq=0;start=time.monotonic();messages=[];checks={}
    try:
        async with ClientSession(trust_env=False)as client:
            for path in ['/','/app.js','/input.js','/vendor/three.module.js','/vendor/three.core.js','/health']:
                async with client.get(base+path)as response:assert response.status==200,(path,response.status);await response.read()
            async with client.get(base+'/scene.json')as response:
                scene=await response.json();assert len(scene['geoms'])==len(scene['initial_state']['transforms'])
                for mesh in scene['meshes'].values():assert max(mesh['indices'])<len(mesh['vertices'])/3
                checks['scene_geometry']=gateway.geometry
            async with client.get(base+'/health',headers={'Origin':'http://untrusted.example'})as response:assert response.status==403
            async with client.get(base+'/protocol.py')as response:assert response.status==404
            checks['http_routes_origin_and_mesh_indices']='passed'
            ws=await client.ws_connect(base+'/ws')
            async def receive():
                async for msg in ws:
                    if msg.type.name=='TEXT':messages.append(json.loads(msg.data))
            listener=asyncio.create_task(receive())
            async def send_for(duration,**kwargs):
                nonlocal seq
                until=time.monotonic()+duration
                while time.monotonic()<until:
                    await ws.send_json(sample(seq,time.monotonic()-start,**kwargs));seq+=1;await asyncio.sleep(.02)
            await ws.send_json({'type':'claim','source':'synthetic_transport_test','device':'python test client; no headset'})
            await asyncio.sleep(.04)
            # Starting while clutch held must not enable movement.
            await send_for(.12,squeeze=1,stick=(0,-1));assert not gateway.engine.active
            await send_for(.08);await send_for(.12,squeeze=1);assert gateway.engine.active
            q0=gateway.engine.d.qpos.copy();h0=gateway.engine.d.site('left_ee').xpos.copy()
            await send_for(1.1,squeeze=1,shift=(0,.06,0))
            dh=gateway.engine.d.site('left_ee').xpos-h0
            assert dh[2]>.025,dh;assert np.max(abs(gateway.engine.d.qpos-q0))>.01
            checks['hand_motion_m']=dh.tolist()
            # Back away from the source table to exercise real wheel contact.
            base0=gateway.engine.d.body('base_footprint_link').xpos.copy()
            await send_for(1.15,squeeze=1,shift=(0,.06,0),stick=(0,1),trigger=1)
            db=gateway.engine.d.body('base_footprint_link').xpos-base0
            assert db[0]<-.04,db;checks['base_motion_m']=db.tolist()
            old_aperture=gateway.engine.aperture
            await send_for(.08);assert not gateway.engine.active;assert np.all(gateway.engine.d.ctrl[gateway.engine.servo.wheels]==0)
            # One previously queued control tick can complete before release arrives.
            assert gateway.engine.aperture<=old_aperture+1e-9
            held_aperture=gateway.engine.aperture;await send_for(.06)
            assert gateway.engine.aperture==held_aperture
            checks['release_holds_grip_and_stops_wheel_command']='passed'
            await send_for(.08,squeeze=1);assert gateway.engine.active
            assert gateway.engine.aperture==held_aperture
            checks['regrip_does_not_open_gripper']='passed'
            timeout_start=time.monotonic();await asyncio.sleep(.33)
            assert not gateway.engine.active and gateway.engine.status=='stale';assert np.all(gateway.engine.d.ctrl[gateway.engine.servo.wheels]==0)
            checks['timeout_check_after_ms']=round((time.monotonic()-timeout_start)*1000)
            await send_for(.1,squeeze=1);assert not gateway.engine.active
            await send_for(.08);await send_for(.08,squeeze=1);assert gateway.engine.active
            await ws.send_json({'type':'stop'});await asyncio.sleep(.05);assert gateway.engine.estop and not gateway.engine.active
            await ws.send_json({'type':'resume'});await asyncio.sleep(.04);assert gateway.engine.estop
            await send_for(.06);await ws.send_json({'type':'resume'});await asyncio.sleep(.03);await send_for(.08,squeeze=1);assert gateway.engine.active
            checks['timeout_requires_regrip_and_stop_requires_release']='passed'
            # Explicit tracking loss stops both hands and wheels; reacquisition alone cannot resume.
            lost=sample(seq,time.monotonic()-start,squeeze=1);seq+=1;lost['tracked']=False
            await ws.send_json(lost);await asyncio.sleep(.03);assert not gateway.engine.active
            await send_for(.06,squeeze=1);assert not gateway.engine.active
            await send_for(.06);await send_for(.06,squeeze=1);assert gateway.engine.active
            checks['tracking_loss_requires_regrip']='passed'
            # A second client cannot steal control.
            other=await client.ws_connect(base+'/ws');await other.receive_json()
            await other.send_json({'type':'claim','source':'synthetic_transport_test'})
            response=await other.receive_json()
            while response['type']=='state':response=await other.receive_json()
            assert response['type']=='error';await other.close();checks['single_controller']='passed'
            await ws.send_json({'type':'marker','label':'start','participant':'SYNTHETIC_TEST'})
            await ws.send_json({'type':'marker','label':'cancel','participant':'SYNTHETIC_TEST'})
            await asyncio.sleep(.05)
            # A stale/replayed frame produces a protocol stop, not continued motion.
            await ws.send_json(sample(0,0,squeeze=1));await asyncio.sleep(.05)
            assert gateway.engine.estop and gateway.engine.mail.rejected>=1;checks['reordered_packet_stops']='passed'
            previous_engine=gateway.engine
            await ws.send_json({'type':'reset'})
            deadline=time.monotonic()+5
            while gateway.engine is previous_engine and time.monotonic()<deadline:await asyncio.sleep(.02)
            assert gateway.engine is not previous_engine
            assert gateway.engine.recorder.meta['source']=='synthetic_transport_test'
            assert gateway.engine.recorder.root.parent==out
            assert (out/'session'/'session.json').exists()
            await send_for(.06,squeeze=1);assert not gateway.engine.active
            await send_for(.06);await send_for(.08,squeeze=1);assert gateway.engine.active
            checks['reset_closes_old_recording_preserves_source_and_requires_regrip']='passed'
            await ws.close();await listener;await asyncio.sleep(.04)
            assert gateway.owner is None and not gateway.engine.active;checks['disconnect_stop']='passed'
            checks['steps']=gateway.steps;checks['max_step_ms']=gateway.max_step_ms;checks['overruns']=gateway.overruns
            first_rows=previous_engine.recorder.root/'states_0000.npz'
            with np.load(first_rows)as first:
                checks['sim_to_wall_ratio']=(first['sim_time'][-1]-first['sim_time'][0])/(first['wall_elapsed'][-1]-first['wall_elapsed'][0])
            checks['received_state_frames']=sum(m.get('type')=='state'for m in messages)
    finally:await runner.cleanup()
    metadata=json.loads((out/'session'/'session.json').read_text(encoding='utf-8'))
    assert metadata['source']=='synthetic_transport_test' and metadata['hardware_verified'] is False
    states=np.load(out/'session'/'states_0000.npz');assert len(states['sim_time'])==metadata['control_frames'];assert np.all(np.isfinite(states['qpos']))
    events=[json.loads(line)for line in(out/'session'/'events.jsonl').read_text(encoding='utf-8').splitlines()]
    assert any(e['event']=='trial_marker'for e in events)
    checks.update(recording='passed',source=metadata['source'],hardware_verified=False,result='passed')
    (out/'report.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(checks,ensure_ascii=False,indent=2));print('Report:',out/'report.json')

if __name__=='__main__':asyncio.run(run())
