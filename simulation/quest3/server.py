"""Loopback-only Quest WebXR gateway. The simulation never accepts joint states."""
import argparse,asyncio,gzip,json,time,sys,uuid
from pathlib import Path
from aiohttp import web,WSMsgType
from .engine import Engine
from .scene import export_scene
from .study import PROTOCOL, configuration, schedule, source_hashes
from .follow_study import configuration as follow_configuration
from .risk_protocol import configuration as risk_configuration, VERSION as RISK_VERSION
from .risk_engine import RiskEngine

HERE=Path(__file__).resolve().parent
STATIC={'/':'index.html','/app.js':'app.js','/input.js':'input.js',
        '/vendor/three.module.js':'node_modules/three/build/three.module.js',
        '/vendor/three.core.js':'node_modules/three/build/three.core.js'}

class Gateway:
    def __init__(self,record_root=None,follow=False,risk=False):
        initial = risk_configuration() if risk else (follow_configuration() if follow else None)
        options = {'mode': 'follow', 'target_height': initial['target_height'], 'seed': initial['seed'], 'trial_config': initial} if initial else {}
        self.record_root=record_root;self.engine=RiskEngine(record_root,trial_config=initial) if risk else Engine(record_root, **options);self.clients=set();self.owner=None;self.owner_source=None;self.owner_device=None
        self.scene,self.geometry=export_scene(self.engine);self.running=True;self.steps=0;self.overruns=0;self.max_step_ms=0.;self.closed=False
        self.trial=None;self.next_trial=1
        self.loaded_source_hashes = source_hashes()
    def local_request(self,request):
        if request.host.split(':')[0] not in {'127.0.0.1','localhost','[::1]'}:raise web.HTTPForbidden(text='Use localhost')
        origin=request.headers.get('Origin')
        if origin and origin!=f'http://{request.host}':raise web.HTTPForbidden(text='Same-origin requests only')
    async def static(self,request):
        self.local_request(request)
        response=web.FileResponse(HERE/'web'/STATIC[request.path])
        response.headers.update({'Cache-Control':'no-store','X-Content-Type-Options':'nosniff',
            'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'unsafe-inline'; connect-src 'self' ws://localhost:* ws://127.0.0.1:*; img-src 'self' data:; object-src 'none'; base-uri 'none'"})
        return response
    async def scene_response(self,request):
        self.local_request(request)
        return web.Response(body=self.scene,content_type='application/json',headers={'Content-Encoding':'gzip','Cache-Control':'no-store'})
    async def health(self,request):
        self.local_request(request)
        return web.json_response({'ok':self.running,'controller_version':RISK_VERSION if isinstance(self.engine,RiskEngine) else '20261117-follow3','status':self.engine.status,'clients':len(self.clients),'controller_connected':self.owner is not None,
            'session':str(self.engine.recorder.root),'hardware_verified':False,'steps':self.steps,'overruns':self.overruns,'max_step_ms':round(self.max_step_ms,3),'geometry':self.geometry,
            'experiment': self.engine.trial.snapshot(time.monotonic()) if self.engine.trial else None})
    async def study_plan(self, request):
        self.local_request(request)
        return web.json_response({'protocol': PROTOCOL, 'schedule': {p: schedule(p) for p in ['P00', *PROTOCOL['participants']]},
                                  'locked': (HERE/'study_lock.json').exists()})
    async def replace_engine(self, config=None):
        packet = self.engine.mail.packet
        if self.engine.active or (packet is not None and any(packet.squeeze > .2)):
            raise ValueError('请先松开双侧握键，再准备场景。')
        reset_root = self.engine.recorder.root.parent / (time.strftime('%Y%m%d_%H%M%S') + '_reset_' + uuid.uuid4().hex[:6])
        if config is None and isinstance(self.engine, RiskEngine):
            config=risk_configuration(self.engine.allocator.policy,self.engine.info['risk_scenario'],self.engine.info['target_height'])
        options = {} if config is None else {'mode': config['mode'], 'target_height': config['target_height'],
                                             'seed': config['seed'], 'trial_config': config, 'follow_policy': config.get('follow_policy', 'gated')}
        new_engine = (RiskEngine(reset_root,config['risk_policy'],config['risk_scenario'],config['target_height'],config['seed'],config)
                      if config and 'risk_policy' in config else Engine(reset_root, **options))
        new_scene, new_geometry = export_scene(new_engine)
        descriptors = json.loads(gzip.decompress(new_scene))['geoms']
        self.engine.close()
        self.engine = new_engine
        self.scene, self.geometry = new_scene, new_geometry
        if self.owner is not None:
            self.engine.connect(self.owner_source, self.owner_device)
        self.engine.started = time.monotonic()
        self.engine.recorder.meta['physics_start_unix_s'] = time.time()
        for client in list(self.clients):
            if not client.closed:
                await client.send_json({'type': 'reset', 'session': str(self.engine.recorder.root), 'geoms': descriptors})
    async def ws(self,request):
        self.local_request(request)
        ws=web.WebSocketResponse(max_msg_size=16384,heartbeat=10);await ws.prepare(request);self.clients.add(ws)
        await ws.send_json({'type':'hello','schema':1,'hardware_verified':False,'session':str(self.engine.recorder.root)})
        try:
            async for msg in ws:
                if msg.type!=WSMsgType.TEXT:continue
                kind = None
                try:
                    raw=json.loads(msg.data)
                    if not isinstance(raw,dict):raise ValueError('Expected JSON object')
                    kind=raw.get('type')
                    if kind=='claim':
                        if self.owner is not None and self.owner is not ws:raise ValueError('Another controller owns this simulation')
                        if self.owner is ws:raise ValueError('Already controlling')
                        source=raw.get('source')
                        if source not in {'webxr_live','synthetic_transport_test'}:raise ValueError('Invalid source label')
                        self.owner=ws;self.owner_source=source;self.owner_device=str(raw.get('device','unknown'))[:200];self.engine.connect(source,self.owner_device)
                        await ws.send_json({'type':'claimed','source':source})
                    elif kind=='pose':
                        if self.owner is not ws:raise ValueError('Claim control before sending poses')
                        if not self.engine.receive(raw):raise ValueError('Pose rejected; release and regrip')
                    elif kind=='release':
                        if self.owner is ws:self.engine.disconnect();self.owner=None
                    elif kind=='stop':self.engine.stop('operator_stop')
                    elif kind=='resume':
                        if not self.engine.clear_stop():raise ValueError('Release both squeeze buttons first')
                    elif kind=='marker':
                        if self.engine.trial:
                            raise ValueError('实验结果由物理判据记录，请使用实验开始/终止按钮。')
                        label=raw.get('label');participant=str(raw.get('participant',''))[:40]
                        if label=='start':
                            if self.trial is not None:raise ValueError('End the current trial first')
                            self.trial=self.next_trial;self.next_trial+=1
                        elif label not in {'success','failure','cancel'} or self.trial is None:raise ValueError('No active trial / unsupported marker')
                        self.engine.recorder.event('trial_marker',trial=self.trial,label=label,participant=participant,sim_time=self.engine.d.time,
                            outcome_origin='operator_annotation_not_automatic_validation',source=self.engine.recorder.meta['source'])
                        if label!='start':self.trial=None
                        await ws.send_json({'type':'marker','active_trial':self.trial,'label':label})
                    elif kind=='reset':
                        p=self.engine.mail.packet
                        if p is not None and any(p.squeeze>.2):raise ValueError('Release both squeeze buttons before reset')
                        if self.trial is not None:self.engine.recorder.event('trial_marker',trial=self.trial,label='cancel',reason='scene_reset')
                        self.trial=None
                        await self.replace_engine()
                    elif kind == 'risk_prepare':
                        if self.engine.trial and self.engine.trial.status == 'running':
                            raise ValueError('先结束当前试次，再准备下一次。')
                        config=risk_configuration(raw.get('policy','dual'),raw.get('scenario','normal'),float(raw.get('height',.75)))
                        await self.replace_engine(config)
                    elif kind == 'follow_prepare':
                        if self.engine.trial and self.engine.trial.status == 'running':
                            raise ValueError('先结束当前试次，再准备下一次。')
                        config = follow_configuration(raw.get('policy'), float(raw.get('height', .75)))
                        await self.replace_engine(config)
                    elif kind == 'study_prepare':
                        if self.engine.trial and self.engine.trial.status == 'running':
                            raise ValueError('先结束当前试次，再准备下一次。')
                        config = configuration(raw.get('participant'), raw.get('index'), raw.get('phase'))
                        if config['phase'] == 'formal' and config['source_sha256'] != self.loaded_source_hashes:
                            raise ValueError('源码已更新，请重新启动实验服务后采集正式数据。')
                        await self.replace_engine(config)
                    elif kind == 'study_start':
                        if not self.engine.trial:
                            raise ValueError('请先准备试次。')
                        packet = self.engine.mail.packet
                        if self.owner is None or packet is None or not packet.tracked or time.monotonic() - self.engine.mail.received > .25:
                            raise ValueError('请佩戴头显，让两只控制器恢复追踪。')
                        if any(packet.squeeze > .2):
                            raise ValueError('请先松开双侧握键。')
                        self.engine.clear_stop()
                        self.engine.trial.start(self.engine)
                    elif kind == 'study_abort':
                        if self.engine.trial:
                            self.engine.trial.finish(self.engine, 'failure', 'operator_abort')
                    else:raise ValueError('Unknown message type')
                except (ValueError,KeyError,TypeError,OverflowError)as exc:
                    if self.owner is ws and kind == 'pose':self.engine.stop('protocol_error')
                    await ws.send_json({'type':'error','message':str(exc)})
        finally:
            self.clients.discard(ws)
            if self.owner is ws:self.engine.disconnect();self.owner=None
        return ws
    async def physics(self):
        next_tick=time.monotonic()
        try:
            while self.running:
                begin=time.monotonic();self.engine.step(begin);cost=time.monotonic()-begin
                self.steps+=1;self.max_step_ms=max(self.max_step_ms,cost*1000)
                if cost>.01:self.overruns+=1
                next_tick+=.01
                if time.monotonic()-next_tick>.05:next_tick=time.monotonic()
                await asyncio.sleep(max(0,next_tick-time.monotonic()))
        except asyncio.CancelledError:raise
        except Exception as exc:
            self.engine.stop('simulation_fault');self.engine.recorder.event('simulation_fault',error=repr(exc));self.running=False
            print('Simulation stopped:',repr(exc),flush=True)
    async def broadcast(self):
        while self.running:
            await asyncio.sleep(1/30)
            if not self.clients:continue
            state=self.engine.snapshot();state.update(active_trial=self.trial,overruns=self.overruns,wall_elapsed=time.monotonic()-self.engine.started)
            # A slow viewer must not block the safety watchdog / other viewers.
            results=await asyncio.gather(*(asyncio.wait_for(ws.send_json(state),.08)for ws in list(self.clients)if not ws.closed),return_exceptions=True)
            # Failed / congested sockets are handled by the next receive or heartbeat.
    async def lifecycle(self,app):
        # Windows' default wait resolution can be ~15.6 ms, slower than our 10 ms loop.
        # Pair the process request with timeEndPeriod on shutdown; no global settings.
        timer=None
        if sys.platform=='win32':
            import ctypes
            timer=ctypes.WinDLL('winmm')
            if timer.timeBeginPeriod(1)!=0:timer=None
        self.engine.started=time.monotonic();self.engine.recorder.meta['physics_start_unix_s']=time.time()
        self.tasks=[asyncio.create_task(self.physics()),asyncio.create_task(self.broadcast())]
        print('Quest gateway initialized (default http://localhost:8765)',flush=True)
        print('Session:',self.engine.recorder.root,flush=True)
        print('Hardware validation: pending',flush=True)
        try:yield
        finally:
            self.running=False
            for task in self.tasks:task.cancel()
            await asyncio.gather(*self.tasks,return_exceptions=True)
            try:
                for ws in list(self.clients):await ws.close()
                if not self.closed:self.engine.close();self.closed=True
            finally:
                if timer is not None:timer.timeEndPeriod(1)
    def app(self):
        app=web.Application(client_max_size=16384)
        for route in STATIC:app.router.add_get(route,self.static)
        app.router.add_get('/scene.json',self.scene_response);app.router.add_get('/health',self.health);app.router.add_get('/ws',self.ws)
        app.router.add_get('/study-plan', self.study_plan)
        app.cleanup_ctx.append(self.lifecycle)
        return app

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8765);parser.add_argument('--record-root',type=Path)
    parser.add_argument('--study', action='store_true')
    parser.add_argument('--follow', action='store_true')
    parser.add_argument('--risk', action='store_true')
    args=parser.parse_args()
    if (args.study or args.follow or args.risk) and args.record_root is None:
        args.record_root = HERE/('risk_sessions' if args.risk else ('follow_sessions' if args.follow else 'study_sessions'))/(time.strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6])
    web.run_app(Gateway(args.record_root, follow=args.follow,risk=args.risk).app(),host='127.0.0.1',port=args.port,print=None,access_log=None)
