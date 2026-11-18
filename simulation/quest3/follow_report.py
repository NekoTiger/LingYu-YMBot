"""Render measured engineering results and saved-state video, no new simulation."""
import argparse
import csv
import json
from pathlib import Path

import imageio.v2 as imageio
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import mujoco
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def report(root, video=False):
    root = Path(root)
    out = root/'report'
    out.mkdir(exist_ok=True)
    rows = json.loads((root/'results.json').read_text(encoding='utf-8'))
    boundary = json.loads((root/'boundary_results.json').read_text(encoding='utf-8'))
    summaries = {}
    fields = ['elapsed_sim_s', 'joystick_command_sim_s', 'navigation_max_tilt_deg',
              'navigation_max_slip_mm', 'navigation_waist_range_deg']
    for policy in ('off', 'gated'):
        data = [r for r in rows if r.get('follow_policy', r.get('policy')) == policy]
        summaries[policy] = {'n': len(data), 'successes': sum(r['outcome']=='success' for r in data)}
        for field in fields:
            valid = [r[field] for r in data if r.get(field) is not None]
            summaries[policy][field] = {'mean': float(np.mean(valid)), 'min': min(valid), 'max': max(valid), 'n': len(valid)} if valid else None
    probe = {p: {f: float(np.mean([r[f] for r in boundary if r['policy']==p]))
                 for f in ('unintended_command_s','integrated_unintended_command_m','command_onsets','intent_onset_delay_s')}
             for p in ('threshold','gated')}
    summary = {'physical_tasks': summaries, 'boundary_command_probe': probe,
               'scope': 'scripted engineering validation; not human workload or real robot evidence'}
    (out/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    with (out/'trials.csv').open('w', newline='', encoding='utf-8-sig') as file:
        keys = ['follow_policy','target_height','seed','outcome','reason', *fields]
        writer = csv.DictWriter(file, fieldnames=keys, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    plt.rcParams.update({'font.sans-serif': ['Microsoft YaHei'], 'axes.unicode_minus': False,
                         'font.size': 11, 'axes.spines.top': False, 'axes.spines.right': False})
    colors = ['#718798', '#087f8c']
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.4))
    for ax, field, title in zip(axes, fields[:3], ['任务仿真耗时 / s','脚本摇杆指令时长 / s','搬运阶段最大托盘倾角 / °']):
        for i, p in enumerate(('off','gated')):
            values = [r[field] for r in rows if r.get('follow_policy')==p and field in r]
            ax.bar(i, np.mean(values), width=.55, color=colors[i], alpha=.85)
            ax.scatter(np.full(len(values), i)+np.linspace(-.08,.08,len(values)), values, color='#173349', zorder=5, s=22)
            ax.text(i, max(values)*1.07, f'{np.mean(values):.2f}', ha='center', weight='bold')
        ax.set_xticks([0,1],['同映射摇杆对照','工作空间跟随'])
        ax.set_title(title, pad=16)
        ax.set_ylim(0, max(r[field] for r in rows if field in r)*1.25)
        ax.grid(axis='y', alpha=.15)
    fig.suptitle('灵驭｜工作空间跟随：独立种子物理流程验证', fontsize=17, weight='bold', y=1.02)
    fig.text(.5, -.025, '两种台高 × 两个种子；每模式 4 次。点为单次结果；合成输入，不能解释为真人工作负担。', ha='center', fontsize=10)
    fig.tight_layout()
    fig.savefig(out/'任务对照.png', dpi=180, bbox_inches='tight')
    plt.close(fig)
    fig, axes = plt.subplots(2,1,figsize=(12,5),sharex=True)
    for p, color, label in (('threshold','#d68746','直接阈值（本机简化对照）'),('gated','#087f8c','滤波 + 确认 + 滞回')):
        with np.load(root/f'boundary_{p}.npz') as data:
            t = np.arange(len(data['x']))*.01
            if p == 'threshold':
                axes[0].plot(t,data['x'],color='#8795a0',linewidth=.7)
            axes[1].plot(t,data['command'],color=color,label=label,linewidth=1.)
    axes[0].axhline(.58,color='#d68746',ls='--',label='前进触发边界')
    axes[0].set_ylabel('输入中心坐标 / m')
    axes[0].legend(loc='upper left')
    axes[1].set_ylabel('前进速度请求 / m/s')
    axes[1].set_xlabel('控制时钟 / s')
    axes[1].legend(loc='upper left')
    axes[1].set_xlim(0,23)
    fig.suptitle('边界抖动检查｜相同输入，比较误触发与响应延迟',fontsize=16,weight='bold')
    fig.text(.5,-.015,'图示种子 8200；统计包含 16 个种子。6 mm 为人为设定的噪声，不是 Quest 3 实测值。',ha='center',fontsize=10)
    fig.tight_layout()
    fig.savefig(out/'边界抖动对照.png',dpi=180,bbox_inches='tight')
    plt.close(fig)
    a, b = summaries['off'], summaries['gated']
    def number(p, field):
        return f"{summaries[p][field]['mean']:.2f}" if summaries[p][field] else '未获得'
    text = f'''# 文献改进版验证结果

该版本依据 Let the Body Follow（2026，arXiv:2607.16095，式 5）的工作空间边界触发思路，针对本机差速底盘和共同持物任务独立实现。不是作者代码的完整复现。

## 实际实现

- 以离合标定时的真实双手中心为中点。前后超过 8 cm 才考虑生成前后速度；180 ms 确认、60 ms 滤波、1 cm 滞回，先回中再启用。
- 搬运时将前后手部修正限制在中点附近 ±1 cm，把较大伸手意图交给底盘；上下移动、共同偏航、夹爪仍由人控制。该任务映射适合共同持有刚性托盘，非任意双手操作。
- 搬运中短暂停车继续保持同一个腰部参考；收到超过 2 cm 的垂向目标变化、卸载或放置请求时才释放保持，避免每次停走重新寻找腰部姿态。
- 夹持、离台、倾角、滑移和放置阶段决定是否允许跟随；摇杆优先，松握键或输入失效停止指令。自动前后运动加入理想几何距离制动，转向及路线仍由人决定。
- 增加跟随状态、速度请求、底盘命令、原始手部中心及制动比例记录。

## 完整任务对照

| 指标 | 同映射摇杆对照 | 工作空间跟随 |
|---|---:|---:|
| 自动物理判据成功 | {a['successes']}/{a['n']} | {b['successes']}/{b['n']} |
| 平均任务仿真耗时 / s | {number('off','elapsed_sim_s')} | {number('gated','elapsed_sim_s')} |
| 平均脚本摇杆指令时长 / s | {number('off','joystick_command_sim_s')} | {number('gated','joystick_command_sim_s')} |
| 每次最大托盘倾角的均值 / ° | {number('off','navigation_max_tilt_deg')} | {number('gated','navigation_max_tilt_deg')} |
| 每次最大相对滑移的均值 / mm | {number('off','navigation_max_slip_mm')} | {number('gated','navigation_max_slip_mm')} |
| 每次腰部角度范围的均值 / ° | {number('off','navigation_waist_range_deg')} | {number('gated','navigation_waist_range_deg')} |

场景为 60/75 cm 两种目标台高、每场景两个种子；合成操作器沿相同路线规划输入，两模式的手部/摇杆命令并不相同。输入在导航阶段叠加 6 mm 单轴手部位置噪声。保存全部结果，失败没有从表中删除。

摇杆指令时间下降是辅助功能的接口使用证据，不能等同于真人负担下降。每模式只有四次，不能据此宣称普遍可靠性或优于原论文。任务时间变长、倾角或滑移增加都应与减少摇杆操作一起报告。

最终这组数据中，跟随模式的摇杆指令时长下降约 {100*(1-b['joystick_command_sim_s']['mean']/a['joystick_command_sim_s']['mean']):.1f}%；任务耗时均值相差不足 0.5 s，不作为显著提速结论。跟随模式最大托盘倾角较小，但最大滑移均值约增加 {b['navigation_max_slip_mm']['mean']-a['navigation_max_slip_mm']['mean']:.2f} mm、腰部范围均值约增加 {b['navigation_waist_range_deg']['mean']-a['navigation_waist_range_deg']['mean']:.2f}°，因此不是所有指标都改善。

![任务对照](任务对照.png)

## 边界噪声消融

16 个噪声种子；每次先在阈值内侧 5 mm 保持 20 s，叠加 6 mm 高斯位置噪声，再明确前伸 2 s。两方法接收相同信号和相同载荷有效标记；这是控制器信号测试，不是物理位移测量。

| 指标（16 次均值） | 直接阈值 | 带确认的跟随 |
|---|---:|---:|
| 20 s 边界段的前进请求时长 / s | {probe['threshold']['unintended_command_s']:.3f} | {probe['gated']['unintended_command_s']:.3f} |
| 前进请求启动次数 | {probe['threshold']['command_onsets']:.2f} | {probe['gated']['command_onsets']:.2f} |
| 明确前伸后的请求响应延迟 / s | {probe['threshold']['intent_onset_delay_s']:.3f} | {probe['gated']['intent_onset_delay_s']:.3f} |

该消融说明指定边界噪声下误触发减少，代价是确认延迟。它不意味着所有噪声下零误触发，也不是端到端 VR 延迟测量。

![边界对照](边界抖动对照.png)

## 版本与边界

早期开发记录保留在 `follow_dev_20261117a/b/c/d`：a 为固定中点导致超时，b 为脚本切换抖动导致超时，c 为标定与操作器修正后成功，d 为缩小搬运手部修正后的开发试跑。

第一轮 `follow_validation_20261117` 的种子 7200–7201 用于发现并改进额外托盘倾斜，第二轮 `follow_validation_r2_20261117` 的种子 7300–7301 用于发现并改进短暂停顿导致的腰部解锁；两轮均已成为开发数据。最终修正版使用种子 7400–7401，运行前源码哈希见本目录上级 `protocol.json`，对应源码保存在 `source_snapshot`。各轮结果不能合并宣传为独立验证，也不以跨种子版本差异计算算法提升。

真实 Quest 3 对新版的操作舒适度、主观负担、误触发和完整成功率仍待预实验。近障制动依赖仿真理想几何，只限制自动前后移动，不能代替视觉避障、全身碰撞保证或实体机器人验证。未声称复现 MABEL、V-DART 或 ExtremControl。
'''
    (out/'验证结果.md').write_text(text, encoding='utf-8')
    if video:
        successful = [r for r in rows if r.get('follow_policy')=='gated' and r['outcome']=='success']
        if not successful:
            raise RuntimeError('No successful task to render; see failures')
        # Deterministic choice, not the fastest/best-looking trial.
        chosen = sorted(successful, key=lambda r:(-r['target_height'],r['seed']))[0]
        render_video(Path(chosen['session']), out)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(out)


def render_video(root, out):
    chunks = []
    for file in sorted(root.glob('states_*.npz')):
        with np.load(file) as data:
            chunks.append({k:data[k].copy() for k in data.files})
    data = {k:np.concatenate([c[k] for c in chunks]) for k in chunks[0]}
    model = mujoco.MjModel.from_xml_path(str(root/'scene.xml'))
    state = mujoco.MjData(model)
    renderer = mujoco.Renderer(model, 720, 1280)
    camera = mujoco.MjvCamera()
    camera.lookat[:] = [-.25, .9, .70]
    camera.distance = 4.7
    camera.azimuth = 215
    camera.elevation = -27
    font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',26)
    small = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',19)
    result = json.loads((root/'benchmark_result.json').read_text(encoding='utf-8'))
    def frame(t):
        i = min(int(np.searchsorted(data['sim_time'],t)),len(data['sim_time'])-1)
        state.qpos[:] = data['qpos'][i]
        state.qvel[:] = data['qvel'][i]
        state.ctrl[:] = data['ctrl'][i]
        state.time = data['sim_time'][i]
        mujoco.mj_forward(model,state)
        renderer.update_scene(state,camera=camera)
        img = Image.fromarray(renderer.render())
        draw = ImageDraw.Draw(img)
        draw.rectangle((0,0,1280,93),fill='#112b3c')
        draw.text((24,12),'灵驭｜工作空间跟随与双臂搬运',font=font,fill='#edf7f9')
        draw.text((24,54),'已保存物理轨迹回放 · 合成操作输入 · 2 倍仿真时间播放',font=small,fill='#99ded9')
        draw.text((960,21),f'仿真 {state.time:5.1f} s',font=font,fill='white')
        draw.rectangle((0,644,1280,720),fill='#112b3c')
        v, w = data['base_command'][i]
        auto = data['follow_request'][i]
        label = ('手部意图 → 底盘前进' if auto>0 else '手部意图 → 底盘后退') if abs(auto)>.001 else ('摇杆转向 / 接管' if abs(w)>.01 else '抓取、抬升或放置')
        draw.text((24,657),label,font=font,fill='#99ded9')
        draw.text((24,693),f'前后速度 {v:+.3f} m/s    转向 {w:+.3f} rad/s    跟随请求 {auto:+.3f} m/s',font=small,fill='white')
        if t >= data['sim_time'][-1]-.5:
            draw.text((820,660),'承重 · 松爪 · 撤手：通过',font=font,fill='#99ded9')
        return np.asarray(img)
    try:
        for label, t in [('抬升',9.),('跟随',14.),('搬运',35.),('放置',data['sim_time'][-1])]:
            Image.fromarray(frame(t)).save(out/f'{label}.png')
        with imageio.get_writer(out/'文献改进版演示.mp4',fps=25,codec='libx264',quality=8,
                                macro_block_size=None,ffmpeg_params=['-pix_fmt','yuv420p','-movflags','+faststart']) as writer:
            for t in np.arange(0,data['sim_time'][-1]+.01,.08):
                writer.append_data(frame(t))
            for _ in range(30):
                writer.append_data(frame(data['sim_time'][-1]))
        (out/'video_provenance.json').write_text(json.dumps({'session':str(root),'seed':result['seed'],
             'selection':'lowest seed among successful 75cm trials, else highest available height',
             'source':'synthetic_transport_test','playback_speed':2,'fps':25,
             'physical_states_modified':False,'rendering':'saved qpos/qvel/ctrl, no resimulation'},indent=2),encoding='utf-8')
    finally:
        renderer.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('root',type=Path)
    parser.add_argument('--video',action='store_true')
    report(**vars(parser.parse_args()))
