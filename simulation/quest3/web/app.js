import * as THREE from '/vendor/three.module.js';
import {controls,makePacket,anchoredPlacement,VIEW_PRESETS,nextViewPreset} from './input.js';

const $=id=>document.getElementById(id),errors=$('error');
const statuses={active:'操控中',waiting:'等待控制器',stale:'未收到新位姿',tracking_lost:'追踪丢失',clutch_released:'松手保持',stopped:'已停止',operator_stop:'已停止',protocol_error:'输入异常',ik_fault:'求解异常',disconnected:'控制器已断开'};
let ws,claimed=false,connected=false,xrSession=null,seq=0,lastSent=-Infinity,lastResume=false,latest=null,sceneReady=false;
let reconnectTimer=null,originListener=null,sceneData,meshes=[],lastHud=0,placeView=false,xrSupported=false;
let viewPreset='side',viewYaw=0,viewDist=0,lastLoop=0,lastY=false,viewDirty=false,viewAdjustReady=false,anchorHead=null;
let studyPlan=null,lastStart=false,shownMode=null;
const modeNames={baseline:'标准',assisted:'辅助',legacy:'自由练习',follow:'工作空间跟随'};
const riskNames={dual:'双层联合',fixed:'固定分配',grip_only:'仅抓持风险',payload_only:'仅承载风险',slow:'统一降速'};
const riskPolicyNames={fixed:'固定分配',dual:'双层联合'};
const riskSceneNames={normal:'正常摩擦',low:'低摩擦'};
const riskSceneModelNames={Rnormal:'正常摩擦',Rcombined:'低摩擦',Rgrip:'低夹持摩擦',Rpayload:'低承载摩擦'};
const followNames={inactive:'松手保持',off:'摇杆对照',manual:'摇杆接管',load_not_ready:'等待夹稳抬离',return_to_center:'双手回中以启用',ready:'前后伸手控制底盘',confirming:'确认伸手意图',forward:'跟随前进',backward:'跟随后退'};
const trialNames={ready:'已准备',running:'计时中',success:'成功',failure:'失败'};
const reasons={obstacle_collision:'接触障碍',payload_dropped:'物件掉落',parcel_left_tray:'物件脱离托盘',timeout:'达到时限',operator_abort:'操作者终止',reset_or_shutdown_during_trial:'中途重置或关闭'};
const scene=new THREE.Scene();scene.background=new THREE.Color('#101b25');
const camera=new THREE.PerspectiveCamera(55,innerWidth/innerHeight,.05,30);camera.position.set(2,2,1);camera.lookAt(-.35,.7,-2.6);scene.add(camera);
const renderer=new THREE.WebGLRenderer({antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio,1.5));renderer.setSize(innerWidth,innerHeight);
renderer.xr.enabled=true;renderer.xr.setReferenceSpaceType('local-floor');renderer.xr.setFramebufferScaleFactor(.85);
document.body.prepend(renderer.domElement);
scene.add(new THREE.HemisphereLight(0xddeeff,0x56606a,2.3));const light=new THREE.DirectionalLight(0xffefdd,2);light.position.set(1,4,2);scene.add(light);
const world=new THREE.Group();
// Robot (x forward, y left, z up) -> WebXR (x right, y up, -z forward).
const axesConversion=new THREE.Matrix4().set(0,-1,0,0, 0,0,1,0, -1,0,0,0, 0,0,0,1);
// Front-side overview keeps the tray visible instead of hidden behind the torso.
const conversion=new THREE.Matrix4().makeRotationY(Math.PI+.4).multiply(axesConversion);
world.quaternion.setFromRotationMatrix(conversion);world.scale.setScalar(.8);world.position.set(-.55,0,-2.2);scene.add(world);
const grid=new THREE.GridHelper(8,40,0x68808b,0x405560);grid.rotation.x=Math.PI/2;grid.position.z=.002;world.add(grid);
for(let i=0;i<2;i++){
  const grip=renderer.xr.getControllerGrip(i);
  grip.add(new THREE.Mesh(new THREE.SphereGeometry(.025,12,8),new THREE.MeshBasicMaterial({color:i===0?0x5ae1d0:0xffbf73})));
  scene.add(grip);
}
const hudCanvas=document.createElement('canvas');hudCanvas.width=1024;hudCanvas.height=192;
const hudCtx=hudCanvas.getContext('2d'),hudTex=new THREE.CanvasTexture(hudCanvas);
const hud=new THREE.Mesh(new THREE.PlaneGeometry(.76,.1425),new THREE.MeshBasicMaterial({map:hudTex,transparent:true,depthTest:false}));hud.position.set(0,-.33,-1);hud.renderOrder=999;hud.visible=false;camera.add(hud);

function send(data){if(ws?.readyState===WebSocket.OPEN)ws.send(JSON.stringify(data));}
function sendView(){if(ws?.readyState===WebSocket.OPEN&&claimed)send({type:'view',preset:viewPreset,yaw:+viewYaw.toFixed(3),dist:+viewDist.toFixed(3)});}
function error(message){errors.textContent=message;}
function clampAngle(a){while(a>Math.PI)a-=2*Math.PI;while(a<-Math.PI)a+=2*Math.PI;return a;}
let lastClientError=0;
function reportClientError(message,stack){
  const now=performance.now();
  if(now-lastClientError<1000)return;lastClientError=now;
  const text=String(message||'client error').slice(0,400),trace=String(stack||'').slice(0,2000);
  console.error(text,trace);
  if(ws?.readyState===WebSocket.OPEN)send({type:'client_error',message:text,stack:trace});
}
window.addEventListener('error',event=>reportClientError(event.message,event.error?.stack));
window.addEventListener('unhandledrejection',event=>reportClientError('Unhandled promise rejection',event.reason?.stack||String(event.reason)));
function applyPlacement(head){
  if(!anchorHead){
    const pos=head.transform.position,ori=head.transform.orientation;
    anchorHead={position:[pos.x,pos.y,pos.z],quaternion:[ori.x,ori.y,ori.z,ori.w]};
  }
  let placement=null;
  try{placement=anchoredPlacement(anchorHead,viewPreset,viewYaw,viewDist);}
  catch(exc){reportClientError('anchoredPlacement failed: '+exc.message,exc.stack);}
  if(!placement||![...placement.position,...placement.quaternion].every(Number.isFinite))return false;
  world.position.fromArray(placement.position);world.quaternion.fromArray(placement.quaternion);
  return true;
}
function fallbackPlacement(head){
  const h=head.transform,q=new THREE.Quaternion(h.orientation.x,h.orientation.y,h.orientation.z,h.orientation.w);
  const forward=new THREE.Vector3(0,0,-1).applyQuaternion(q),yaw=Math.atan2(-forward.x,-forward.z);
  const heading=new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0,1,0),yaw);
  world.quaternion.setFromRotationMatrix(conversion).premultiply(heading);
  world.position.set(-.55,0,-2.2).applyQuaternion(heading).add(new THREE.Vector3(h.position.x,0,h.position.z));
}
function enableEntry(){
  $('enter').disabled=!(sceneReady&&connected&&xrSupported&&!xrSession);
}
function connect(){
  clearTimeout(reconnectTimer);ws=new WebSocket(`ws://${location.host}/ws`);
  ws.onopen=()=>{connected=true;claimed=false;error('');enableEntry();if(xrSession)claim();};
  ws.onclose=()=>{connected=false;claimed=false;error('连接中断，机器人停止接收运动指令。重连后请先松开双握键。');enableEntry();reconnectTimer=setTimeout(connect,1500);};
  ws.onerror=()=>error('无法连接仿真服务，请检查电脑启动窗口。');
  ws.onmessage=event=>{
    const msg=JSON.parse(event.data);
    if(msg.type==='claimed'){claimed=true;seq=0;error('');}
    if(msg.type==='error')error(msg.message);
    if(msg.type==='reset'){
      latest=null;
      if(msg.geoms&&sceneReady){
        msg.geoms.forEach((g,i)=>{
          if(g.type!==7){meshes[i].geometry.dispose();meshes[i].geometry=geometry(g,{});}
        });
      }
      $('study-prepare').disabled=false;$('risk-study-prepare').disabled=false;error('场景已准备，请先松开双握键。');
    }
    if(msg.type==='marker')error(msg.active_trial?`试次 ${msg.active_trial} 已开始`:'试次记录完成');
    if(msg.type==='state'){
      latest=msg;
      const displayMode=msg.risk_allocation?'risk':msg.control_mode;
      if(shownMode!==displayMode){$('follow-config').open=displayMode==='follow';$('risk-config').open=displayMode==='risk';shownMode=displayMode;}
      const risk=msg.risk_allocation;
      $('risk-state').textContent=risk?`抓持风险 ${risk.grip.toFixed(2)} · 承载风险 ${risk.payload.toFixed(2)} · 边缘余量 ${(risk.edge_margin_m*1000).toFixed(1)} mm · 手臂补偿 ${((risk.arm_offset_m||0)*1000).toFixed(1)} mm`:'';
      if(sceneReady)msg.transforms.forEach((t,i)=>{meshes[i].position.fromArray(t);meshes[i].quaternion.fromArray(t,3);});
      $('status').textContent=(statuses[msg.status]||msg.status)+(msg.workspace_follow?' · '+followNames[msg.workspace_follow.state]:'');
      const elapsed=msg.wall_elapsed||0,ratio=elapsed>1?msg.sim_time/elapsed:1;
      $('diagnostics').textContent=`仿真 ${msg.sim_time.toFixed(1)} s / 实时比 ${ratio.toFixed(2)} / 数据年龄 ${msg.packet_age_ms??'—'} ms / 拒绝包 ${msg.rejected_packets} / 试次 ${msg.active_trial??'未开始'}`;
      const experiment=msg.experiment;
      $('study-start').disabled=!experiment||experiment.status!=='ready';
      $('study-abort').disabled=!experiment||experiment.status!=='running';
      if(experiment){
        const mode=msg.risk_allocation?riskNames[msg.risk_allocation.policy]:(msg.workspace_follow?.policy==='off'?'跟随关闭对照':modeNames[experiment.mode]);
        const sceneText=experiment.scene?riskSceneModelNames[experiment.scene]:'';
        $('study-status').textContent=`${experiment.participant} · 第 ${experiment.index} 次 · ${mode}${sceneText?' · '+sceneText:''} · ${trialNames[experiment.status]} · ${experiment.elapsed_s.toFixed(1)} / ${experiment.time_limit_s} s${experiment.reason?' · '+(reasons[experiment.reason]||'放置核验通过'):''}`;
      }
    }
  };
}
function claim(){send({type:'claim',source:'webxr_live',device:navigator.userAgent});}

function geometry(g,cache){
  const s=g.size;
  if(g.type===7)return cache[g.mesh];
  if(g.type===0)return new THREE.PlaneGeometry(12,12);
  if(g.type===2)return new THREE.SphereGeometry(s[0],16,10);
  if(g.type===3)return new THREE.CapsuleGeometry(s[0],2*s[1],6,12).rotateX(Math.PI/2);
  if(g.type===4)return new THREE.SphereGeometry(1,16,10).scale(...s);
  if(g.type===5)return new THREE.CylinderGeometry(s[0],s[0],2*s[1],20).rotateX(Math.PI/2);
  if(g.type===6)return new THREE.BoxGeometry(2*s[0],2*s[1],2*s[2]);
  throw new Error(`Unsupported MuJoCo geometry ${g.type}`);
}
function buildScene(data){
  const cache={};
  for(const [id,m]of Object.entries(data.meshes)){
    const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(m.vertices,3));g.setIndex(m.indices);g.computeVertexNormals();cache[id]=g;
  }
  for(const g of data.geoms){
    const color=new THREE.Color().setRGB(...g.rgba.slice(0,3),THREE.LinearSRGBColorSpace);
    const material=new THREE.MeshStandardMaterial({color,roughness:.8,metalness:.12,opacity:g.rgba[3],transparent:g.rgba[3]<1});
    const mesh=new THREE.Mesh(geometry(g,cache),material);mesh.name=g.name;world.add(mesh);meshes.push(mesh);
  }
  data.initial_state.transforms.forEach((t,i)=>{meshes[i].position.fromArray(t);meshes[i].quaternion.fromArray(t,3);});
  sceneReady=true;enableEntry();
}
function updateHud(time){
  if(time-lastHud<120)return;lastHud=time;
  hudCtx.clearRect(0,0,1024,192);hudCtx.fillStyle='#132331ee';hudCtx.fillRect(0,0,1024,192);
  hudCtx.fillStyle=latest?.active?'#8df0cb':'#ffda9c';hudCtx.font='bold 39px sans-serif';
  const experiment=latest?.experiment;
  const currentMode=latest?.risk_allocation?riskNames[latest.risk_allocation.policy]:(latest?.workspace_follow?.policy==='off'?'跟随关闭对照':modeNames[experiment?.mode]);
  const title=experiment?`${experiment.participant} 第${experiment.index}次 ${currentMode} ${trialNames[experiment.status]} ${experiment.elapsed_s.toFixed(0)}s`:`${statuses[latest?.status]||'等待连接'}   ${latest?.sim_time.toFixed(1)||'0'} s`;
  hudCtx.fillText(title,28,56);
  hudCtx.fillStyle='#edf4f6';hudCtx.font='26px sans-serif';
  const follow=latest?.workspace_follow;
  let controlLine='双握键：离合   扳机：夹爪   左摇杆：底盘';
  if(follow)controlLine=`${followNames[follow.state]||follow.state}   左摇杆接管 · 松握键停止`;
  else if(!latest?.active&&viewAdjustReady)controlLine=`右摇杆：绕机器人旋转   左Y：${VIEW_PRESETS[viewPreset].name}   双握键：离合`;
  hudCtx.fillText(controlLine,28,103);
  const prompt=latest?.release_blocked?'请先下放到桌面承重，再松开夹爪':(experiment?.status==='ready'?'松开双握键，按右 A 开始本次计时':(experiment?.reason?(reasons[experiment.reason]||'已完成放置与稳定性核验'):'右 B：停止   松开双握键后按左 X：恢复'));
  hudCtx.fillText(prompt,28,145);hudTex.needsUpdate=true;
}
async function enter(){
  try{
    if(!navigator.xr)throw new Error('当前浏览器没有 WebXR，请在 Quest 浏览器访问 localhost。');
    xrSession=await navigator.xr.requestSession('immersive-vr',{requiredFeatures:['local-floor']});
    xrSession.addEventListener('end',()=>{send({type:'release'});xrSession=null;claimed=false;hud.visible=false;
      viewPreset='side';viewYaw=0;viewDist=0;lastY=false;viewDirty=false;viewAdjustReady=false;anchorHead=null;
      camera.position.set(2,2,1);camera.lookAt(-.35,.7,-2.6);enableEntry();});
    xrSession.addEventListener('visibilitychange',()=>{if(xrSession.visibilityState!=='visible')send({type:'stop'});});
    await renderer.xr.setSession(xrSession);hud.visible=true;lastSent=-Infinity;lastResume=false;lastStart=false;placeView=true;
    const space=renderer.xr.getReferenceSpace();originListener=()=>{send({type:'stop'});placeView=true;anchorHead=null;error('追踪原点已变化，请松开双握键后恢复并重新标定。');};space.addEventListener('reset',originListener);
    claim();enableEntry();
  }catch(exc){error(`${exc.name||'Error'}: ${exc.message}`);if(xrSession)await xrSession.end();xrSession=null;enableEntry();}
}
$('enter').onclick=enter;$('stop').onclick=()=>send({type:'stop'});$('resume').onclick=()=>send({type:'resume'});
$('reset').onclick=()=>{if(confirm('结束本次记录并重置场景？请先松开双握键。'))send({type:'reset'});};
for(const button of document.querySelectorAll('[data-marker]'))button.onclick=()=>send({type:'marker',label:button.dataset.marker,participant:$('participant').value.trim()});
function fillStudyOrder(){
  if(!studyPlan)return;
  $('study-index').replaceChildren();
  for(const trial of studyPlan.schedule[$('study-participant').value]){
    const option=document.createElement('option');option.value=trial.index;
    const height=studyPlan.protocol.scenes[trial.scene].target_height*100;
    option.textContent=`${trial.index} · ${modeNames[trial.mode]} · ${height} cm · 第${trial.repeat}轮`;
    $('study-index').append(option);
  }
}
function fillRiskOrder(){
  if(!studyPlan||studyPlan.kind!=='risk')return;
  $('risk-index').replaceChildren();
  for(const trial of studyPlan.schedule[$('risk-participant').value]){
    const option=document.createElement('option');option.value=trial.index;
    option.textContent=`${trial.index} · ${riskPolicyNames[trial.policy]} · ${riskSceneNames[trial.scene]} · 第${trial.repeat}轮`;
    $('risk-index').append(option);
  }
}
$('study-participant').onchange=fillStudyOrder;
$('study-phase').onchange=()=>{
  const formal=$('study-phase').value==='formal';
  $('study-participant').options[0].disabled=formal;
  if(formal&&$('study-participant').value==='P00')$('study-participant').value='P01';
  fillStudyOrder();
};
$('study-prepare').onclick=()=>{
  error('');send({type:'study_prepare',participant:$('study-participant').value,index:Number($('study-index').value),phase:$('study-phase').value});
};
$('risk-participant').onchange=fillRiskOrder;
$('risk-study-prepare').onclick=()=>{
  error('');send({type:'risk_study_prepare',participant:$('risk-participant').value,index:Number($('risk-index').value),phase:'formal'});
};
$('study-start').onclick=()=>{error('');send({type:'study_start'});};
$('follow-prepare').onclick=()=>{error('');send({type:'follow_prepare',policy:$('follow-policy').value,height:Number($('follow-height').value)});};
$('risk-prepare').onclick=()=>{error('');send({type:'risk_prepare',policy:$('risk-policy').value,scenario:$('risk-scenario').value,height:.75});};
$('study-abort').onclick=()=>{if(confirm('结束本次试验并记录为失败？'))send({type:'study_abort'});};

renderer.setAnimationLoop((time,frame)=>{
  const dt=Math.min(Math.max((time-lastLoop)/1000,.001),.05);lastLoop=time;
  try{
    if(frame&&xrSession){
      const ref=renderer.xr.getReferenceSpace();const head=frame.getViewerPose(ref),hands={};
      for(const source of xrSession.inputSources){
        if(!['left','right'].includes(source.handedness)||!source.gripSpace)continue;
        hands[source.handedness]={pose:frame.getPose(source.gripSpace,ref),controls:controls(source.gamepad),profiles:source.profiles};
      }
      if(head&&placeView){if(!applyPlacement(head))fallbackPlacement(head);placeView=false;}
      if(head&&!placeView&&hands.left?.controls&&hands.right?.controls){
        const released=hands.left.controls.squeeze<.2&&hands.right.controls.squeeze<.2;
        viewAdjustReady=released;
        const stick=hands.right.controls.stick;
        const sx=Math.abs(stick[0])>.15?stick[0]:0,sy=Math.abs(stick[1])>.15?stick[1]:0;
        if(released&&(sx||sy)){
          viewYaw=clampAngle(viewYaw-sx*.9*dt);
          viewDist=Math.min(2,Math.max(-.6,viewDist-sy*.6*dt));
          if(!applyPlacement(head))fallbackPlacement(head);viewDirty=true;
        }else if(viewDirty){sendView();viewDirty=false;}
        const yButton=hands.left.controls.secondary;
        if(yButton&&!lastY){
          viewPreset=nextViewPreset(viewPreset);viewYaw=0;viewDist=0;
          anchorHead=null;
          if(!applyPlacement(head))fallbackPlacement(head);sendView();viewDirty=false;
        }
        lastY=yButton;
      }else viewAdjustReady=false;
      if(time-lastSent>=18&&ws.bufferedAmount<16384&&claimed){
        const packet=makePacket(seq++,time,head,hands.left,hands.right);
        if(xrSession.visibilityState!=='visible')packet.tracked=false;
        send(packet);lastSent=time;
        const resume=!!hands.left?.controls?.primary;
        if(resume&&!lastResume)send({type:'resume'});lastResume=resume;
        const start=!!hands.right?.controls?.primary;
        if(start&&!lastStart&&latest?.experiment?.status==='ready')send({type:'study_start'});
        lastStart=start;
      }
    }
    updateHud(time);renderer.render(scene,camera);
  }catch(exc){
    reportClientError((exc?.name||'Error')+': '+(exc?.message||exc),exc?.stack);
    try{renderer.render(scene,camera);}catch(renderExc){reportClientError('render failed: '+(renderExc?.message||renderExc),renderExc?.stack);}
  }
});
window.addEventListener('resize',()=>{camera.aspect=innerWidth/innerHeight;camera.updateProjectionMatrix();renderer.setSize(innerWidth,innerHeight);});
window.addEventListener('beforeunload',()=>send({type:'release'}));
try{
  sceneData=await(await fetch('/scene.json')).json();buildScene(sceneData);connect();
  xrSupported=!!navigator.xr&&await navigator.xr.isSessionSupported('immersive-vr');enableEntry();
  if(!xrSupported)error('电脑可观察三维仿真。进入 VR 需要 Quest 浏览器和 USB 端口转发。');
  const planResponse=await fetch('/study-plan');
  if(planResponse.ok){
    studyPlan=await planResponse.json();
    if(studyPlan.kind==='risk'){
      fillRiskOrder();
      $('risk-study-prepare').disabled=!studyPlan.locked;
      $('risk-study-status').textContent=studyPlan.locked?'协议已冻结，正式采集可用。':'未冻结：先完成 P00 试跑，再运行 python -m simulation.quest3.risk_study --freeze 锁定。';
      $('study-status').textContent='先准备试次，佩戴者松开双握键后开始计时。';
      $('legacy-study-config').style.display='none';
      $('follow-config').style.display='none';
    }else{
      fillStudyOrder();
      $('study-status').textContent='先准备场景，佩戴者松开双握键后开始计时。';
    }
  }
  else $('study-status').textContent='请重新启动电脑端仿真服务，载入实验版本。';
}catch(exc){error(`场景加载失败：${exc.message}`);}
