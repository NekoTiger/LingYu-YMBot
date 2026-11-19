// Pure helpers shared by the headset page and Node protocol tests.
export function poseData(pose) {
  const {position:p,orientation:q}=pose.transform;
  return {position:[p.x,p.y,p.z],quaternion:[q.x,q.y,q.z,q.w]};
}
export function controls(gamepad) {
  if (!gamepad || gamepad.mapping!=='xr-standard') return null;
  const value=i=>Number(gamepad.buttons[i]?.value||0);
  return {trigger:value(0),squeeze:value(1),stick:[gamepad.axes[2]||0,gamepad.axes[3]||0],
    primary:value(4)>.5,secondary:value(5)>.5};
}
export function makePacket(seq,timeMs,head,left,right) {
  const valid=head&&left?.pose&&right?.pose&&left.controls&&right.controls&&!left.pose.emulatedPosition&&!right.pose.emulatedPosition;
  const packet={type:'pose',schema:1,frame:'webxr_local_floor',seq,capture_s:timeMs/1000,tracked:!!valid,
    estop:!!right?.controls?.secondary};
  if(valid)Object.assign(packet,{head:poseData(head),left:poseData(left.pose),right:poseData(right.pose),
    squeeze:[left.controls.squeeze,right.controls.squeeze],trigger:[left.controls.trigger,right.controls.trigger],
    stick:left.controls.stick,profiles:{left:left.profiles,right:right.profiles}});
  return packet;
}
// View placement. Poses use the same {position:[x,y,z], quaternion:[x,y,z,w]} layout as poseData.
// Robot frame (x forward, y left, z up) is rotated into WebXR (x right, y up, -z forward).
const AXES=[[0,-1,0],[0,0,1],[-1,0,0]];
function matMul(a,b){
  const out=[[0,0,0],[0,0,0],[0,0,0]];
  for(let i=0;i<3;i++)for(let k=0;k<3;k++){const aik=a[i][k];for(let j=0;j<3;j++)out[i][j]+=aik*b[k][j];}
  return out;
}
function rotY(rad){const c=Math.cos(rad),s=Math.sin(rad);return [[c,0,s],[0,1,0],[-s,0,c]];}
function matVec(m,v){const out=[0,0,0];for(let i=0;i<3;i++)for(let j=0;j<3;j++)out[i]+=m[i][j]*v[j];return out;}
function quatFromMat(m){
  const m11=m[0][0],m12=m[0][1],m13=m[0][2],m21=m[1][0],m22=m[1][1],m23=m[1][2],m31=m[2][0],m32=m[2][1],m33=m[2][2];
  const trace=m11+m22+m33;
  if(trace>0){const s=.5/Math.sqrt(trace+1);return [(m32-m23)*s,(m13-m31)*s,(m21-m12)*s,.25/s];}
  if(m11>m22&&m11>m33){const s=2*Math.sqrt(1+m11-m22-m33);return [.25*s,(m12+m21)/s,(m13+m31)/s,(m32-m23)/s];}
  if(m22>m33){const s=2*Math.sqrt(1+m22-m11-m33);return [(m12+m21)/s,.25*s,(m23+m32)/s,(m13-m31)/s];}
  const s=2*Math.sqrt(1+m33-m11-m22);return [(m13+m31)/s,(m23+m32)/s,.25*s,(m21-m12)/s];
}
function quatMat(q){
  const x=q[0],y=q[1],z=q[2],w=q[3];
  return [[1-2*(y*y+z*z),2*(x*y-w*z),2*(x*z+w*y)],[2*(x*y+w*z),1-2*(x*x+z*z),2*(y*z-w*x)],[2*(x*z-w*y),2*(y*z+w*x),1-2*(x*x+y*y)]];
}
function headYaw(head){
  const f=matVec(quatMat(head.quaternion),[0,0,-1]);
  return Math.atan2(-f[0],-f[2]);
}
export const VIEW_ORDER=['side','behind','front'];
export const VIEW_PRESETS={
  side:{name:'并肩视角',base:AXES,offset:[.55,0,-.15]},
  behind:{name:'身后视角',base:AXES,offset:[-.55,0,-2.2]},
  front:{name:'对面视角',base:matMul(rotY(Math.PI+.4),AXES),offset:[-.55,0,-2.2]},
};
export function nextViewPreset(preset){const i=VIEW_ORDER.indexOf(preset);return VIEW_ORDER[(i+1)%VIEW_ORDER.length];}
export function viewPlacement(head,presetName,yaw,dist){
  const preset=VIEW_PRESETS[presetName];
  if(!preset)throw new Error('unknown view preset '+presetName);
  const hy=headYaw(head);
  const orientation=matMul(rotY(yaw),matMul(rotY(hy),preset.base));
  const offset=matVec(matMul(rotY(yaw),rotY(hy)),[preset.offset[0],preset.offset[1],preset.offset[2]-dist]);
  return {position:[head.position[0]+offset[0],0,head.position[2]+offset[2]],quaternion:quatFromMat(orientation)};
}
// Robot-anchored placement: the head pose fixes the robot's room position once,
// and yaw only spins the scene about the robot's own vertical axis (turntable).
export function anchoredPlacement(anchor,presetName,yaw,dist){
  const preset=VIEW_PRESETS[presetName];
  if(!preset)throw new Error('unknown view preset '+presetName);
  const hy=headYaw(anchor);
  const orientation=matMul(rotY(yaw),matMul(rotY(hy),preset.base));
  const offset=matVec(rotY(hy),[preset.offset[0],preset.offset[1],preset.offset[2]-dist]);
  return {position:[anchor.position[0]+offset[0],0,anchor.position[2]+offset[2]],quaternion:quatFromMat(orientation)};
}
