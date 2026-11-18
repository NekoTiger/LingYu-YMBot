"""Inspect saved physics states; export a video in simulation time, without resimulation."""
import argparse,json
from pathlib import Path
import numpy as np,mujoco,imageio.v2 as imageio
from PIL import Image,ImageDraw,ImageFont

def review(folder,video=False):
    root=Path(folder);meta=json.loads((root/'session.json').read_text(encoding='utf-8'))
    chunks=[]
    for file in sorted(root.glob('states_*.npz')):
        with np.load(file)as data:chunks.append({k:data[k].copy()for k in data.files})
    if not chunks:raise ValueError('No completed state chunks; stop the server with Ctrl+C first.')
    data={k:np.concatenate([c[k]for c in chunks])for k in chunks[0]};times=data['sim_time']
    assert np.all(np.diff(times)>0)and np.all(np.isfinite(data['qpos']))
    model=mujoco.MjModel.from_xml_path(str(root/'scene.xml'));state=mujoco.MjData(model)
    out=root/'review';out.mkdir(exist_ok=True)
    summary={'source':meta['source'],'hardware_verified':meta['hardware_verified'],'frames':len(times),
        'simulated_duration_s':float(times[-1]-times[0]),'active_fraction':float(data['active'].mean()),
        'video_clock':'simulation time; raw wall_elapsed is retained separately','automatic_task_success':'not assessed'}
    (out/'review.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',24);small=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',18)
    renderer=mujoco.Renderer(model,720,1280);camera=mujoco.MjvCamera();camera.lookat[:]=[.05,.15,.85];camera.distance=3.4;camera.azimuth=220;camera.elevation=-20
    source='合成控制器输入 · 非真人实验' if meta['source']=='synthetic_transport_test' else '浏览器输入记录 · 设备验收另行核对'
    def frame(i):
        state.qpos[:]=data['qpos'][i];state.qvel[:]=data['qvel'][i];state.ctrl[:]=data['ctrl'][i];state.time=times[i];mujoco.mj_forward(model,state)
        renderer.update_scene(state,camera=camera);img=Image.fromarray(renderer.render());draw=ImageDraw.Draw(img)
        draw.rectangle((0,0,1280,84),fill='#132331');draw.text((20,12),'灵驭 · WebXR 输入接口物理回放',font=font,fill='#edf4f6')
        draw.text((20,49),source,font=small,fill='#8de6ce');draw.text((980,20),f'仿真时间 {times[i]:.2f} s',font=small,fill='white')
        return np.asarray(img)
    try:
        for ratio,label in[(.2,'early'),(.5,'middle'),(.95,'final')]:Image.fromarray(frame(int((len(times)-1)*ratio))).save(out/f'{label}.jpg')
        if video:
            with imageio.get_writer(out/'replay.mp4',fps=25,codec='libx264',quality=8,macro_block_size=None,ffmpeg_params=['-pix_fmt','yuv420p','-movflags','+faststart'])as writer:
                for t in np.arange(times[0],times[-1]+.0001,.04):writer.append_data(frame(min(int(np.searchsorted(times,t)),len(times)-1)))
    finally:renderer.close()
    print(json.dumps(summary,ensure_ascii=False,indent=2));print('Review:',out)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder',type=Path);parser.add_argument('--video',action='store_true');args=parser.parse_args();review(**vars(args))
