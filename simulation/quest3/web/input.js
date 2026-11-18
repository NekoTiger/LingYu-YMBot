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
