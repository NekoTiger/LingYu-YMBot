"""Auditable figures and video from saved results; never alter physical traces."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import imageio.v2 as imageio
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import mujoco
import numpy as np
from PIL import Image,ImageDraw,ImageFont

POLICIES=['fixed','grip_only','payload_only','dual','slow']
NAMES=['固定分配','仅抓持风险','仅承载风险','双层联合','统一降速']
SCENES=['normal','grip','payload','combined']
SCENE_NAMES=['正常','低夹持摩擦','低承载摩擦／偏心','两层受限']
COLORS=['#8b9ba9','#486c9a','#d59b47','#087f8c','#a18eac']
FIELDS=['elapsed_sim_s','navigation_max_slip_mm','min_edge_margin_mm','navigation_max_tilt_deg',
        'navigation_waist_range_deg','intent_rmse_m_s','allocation_p95_ms','max_sum_relaxation_m_s']

def mean(data,key):
    values=[r[key] for r in data if r.get(key) is not None]
    return float(np.mean(values)) if values else None

def report(root,delivery=None,video=False):
    root=Path(root);out=Path(delivery) if delivery else root/'report';out.mkdir(exist_ok=True,parents=True)
    rows=json.loads((root/'results.json').read_text(encoding='utf-8'))
    protocol=json.loads((root/'protocol.json').read_text(encoding='utf-8'))
    expected=len(protocol['policies'])*len(protocol['scenarios'])*len(protocol['seeds'])
    if len(rows)!=expected:raise ValueError(f'Run is incomplete: {len(rows)}/{expected}')
    summary={}
    for p in POLICIES:
        data=[r for r in rows if r['risk_policy']==p]
        summary[p]={'n':len(data),'successes':sum(r['outcome']=='success' for r in data),
                    **{f:mean(data,f) for f in FIELDS}}
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    with (out/'trials.csv').open('w',encoding='utf-8-sig',newline='') as file:
        writer=csv.DictWriter(file,fieldnames=['risk_scenario','risk_policy','seed','outcome','reason',*FIELDS],extrasaction='ignore')
        writer.writeheader();writer.writerows(sorted(rows,key=lambda r:(r['risk_scenario'],r['seed'],r['risk_policy'])))
    plt.rcParams.update({'font.sans-serif':['Microsoft YaHei'],'axes.unicode_minus':False,
        'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(2,2,figsize=(13,8))
    for ax,field,title in zip(axes.flat,FIELDS[:4],['完整试次仿真耗时 / s','搬运最大夹持滑移 / mm','悬空阶段最小边缘余量 / mm','搬运最大托盘倾角 / °']):
        for i,p in enumerate(POLICIES):
            data=[r for r in rows if r['risk_policy']==p and r.get(field) is not None]
            values=[r[field] for r in data]
            if not values:continue
            ax.bar(i,np.mean(values),color=COLORS[i],width=.6,alpha=.85)
            for dx,r in zip(np.linspace(-.12,.12,len(data)),data):
                ax.scatter(i+dx,r[field],s=24,color='#20364a' if r['outcome']=='success' else '#c13e35',marker='o' if r['outcome']=='success' else 'x',zorder=5)
            offset=max(r[field] for r in rows if r.get(field) is not None)*.04
            ax.text(i,np.mean(values)+offset,f'{np.mean(values):.2f}',ha='center',fontsize=9)
        ax.set_xticks(range(5),NAMES,rotation=12);ax.set_title(title,pad=14);ax.grid(axis='y',alpha=.15);ax.margins(y=.2)
    fig.suptitle('灵驭｜双层接触风险分配：五组物理任务对照',fontsize=17,weight='bold')
    fig.text(.5,.008,'4 种接触条件 × 2 个新种子；每组 8 次。柱为均值，点为单次试验，红叉为失败；合成输入。',ha='center',fontsize=10)
    fig.tight_layout(rect=(0,.035,1,.95));fig.savefig(out/'五组任务对照.png',dpi=180);plt.close(fig)
    table=[]
    for s in SCENES:
        line=[]
        for p in POLICIES:
            data=[r for r in rows if r['risk_scenario']==s and r['risk_policy']==p]
            line.append(sum(r['outcome']=='success' for r in data)/len(data))
        table.append(line)
    fig,ax=plt.subplots(figsize=(10,3.4));ax.imshow(table,cmap='YlGnBu',vmin=0,vmax=1,aspect='auto')
    for i,s in enumerate(SCENES):
        for j,p in enumerate(POLICIES):
            data=[r for r in rows if r['risk_scenario']==s and r['risk_policy']==p]
            ax.text(j,i,f"{sum(r['outcome']=='success' for r in data)}/{len(data)}",ha='center',va='center',color='white' if table[i][j]>.6 else '#20364a',fontsize=14,weight='bold')
    ax.set_xticks(range(5),NAMES);ax.set_yticks(range(4),SCENE_NAMES);ax.set_title('完整任务成功数 / 试次数（保留全部失败）',pad=15)
    fig.tight_layout();fig.savefig(out/'分场景成功情况.png',dpi=180);plt.close(fig)
    # Predeclared scenario and lowest validation seed; no ranking by outcome or speed.
    chosen=next(r for r in rows if r['risk_policy']=='dual' and r['risk_scenario']=='combined' and r['seed']==min(protocol['seeds']))
    session=Path(chosen['session']);trace=[json.loads(l) for l in (session/'risk_control.jsonl').read_text(encoding='utf-8').splitlines()]
    t=np.array([r['sim_time'] for r in trace]);mask=np.array([r['allocation_active'] for r in trace])
    fig,axes=plt.subplots(3,1,figsize=(12,8),sharex=True)
    for field,color,label in [('grip','#486c9a','抓持风险'),('payload','#d59b47','承载风险')]:
        axes[0].plot(t,[r[field] for r in trace],color=color,label=label,lw=1.3)
    axes[0].set_ylabel('风险指标 / 0–1');axes[0].legend(ncol=2);axes[0].set_ylim(-.03,1.05)
    for field,color,label in [('requested_m_s','#81929d','分配前请求'),('base_m_s','#087f8c','底盘指令'),('arm_relative_m_s','#d59b47','手臂相对指令')]:
        axes[1].plot(t,np.where(mask,[r.get(field,0) for r in trace],np.nan),color=color,label=label,lw=1.)
    axes[1].set_ylabel('速度指令 / m/s');axes[1].legend(ncol=3)
    axes[2].plot(t,np.array([r['edge_margin_m'] for r in trace])*1000,color='#087f8c',label='实际边缘余量')
    axes[2].plot(t,np.where(mask,[r.get('arm_offset_m',0)*1000 for r in trace],np.nan),color='#d59b47',label='手臂补偿位移')
    axes[2].axhline(0,color='#c13e35',lw=.8,ls='--');axes[2].set_ylabel('距离 / mm');axes[2].set_xlabel('仿真时间 / s');axes[2].legend(ncol=2)
    for ax in axes:
        ax.grid(alpha=.12)
        ax.fill_between(t,0,1,where=~mask,color='#82929d',alpha=.12,transform=ax.get_xaxis_transform(),label='分配未启用')
    axes[0].legend(ncol=3)
    fig.suptitle(f"双层风险如何参与动作分配｜两层受限，种子 {chosen['seed']}，{'成功' if chosen['outcome']=='success' else '失败'}",fontsize=16,weight='bold')
    fig.tight_layout(rect=(0,0,1,.96));fig.savefig(out/'风险与分配轨迹.png',dpi=180);plt.close(fig)
    lines=['# 双层接触风险分配：实现与验证结果','',
        f"版本 `{protocol['version']}`；{len(rows)} 次独立种子工程验证。所有操作输入为合成闭环航点规则，不是真人实验。",'',
        '已实现：双接触界面的连续风险观测、每 10 ms 的二维凸优化分配、手臂缓冲与共同速度变化约束、五组消融切换、Quest 3 预实验入口，以及物件脱离托盘后的失败判定。', '',
        '| 方法 | 成功/总数 | 耗时/s | 最大滑移/mm | 最小边缘余量/mm | 最大倾角/° |',
        '|---|---:|---:|---:|---:|---:|']
    for p,name in zip(POLICIES,NAMES):
        a=summary[p];lines.append(f"| {name} | {a['successes']}/{a['n']} | {a['elapsed_sim_s']:.2f} | {a['navigation_max_slip_mm']:.2f} | {a['min_edge_margin_mm']:.2f} | {a['navigation_max_tilt_deg']:.2f} |")
    lines+=['','除成功数外为试次指标的均值；包括失败试次，失败后的轨迹不继续累计。失败与成功的轨迹长度不同，不能用较短失败轨迹的较小极值说明更稳定。', '',
        '## 这组数据支持什么','',
        '它验证了控制器能运行、不同风险参与了分配，以及五种方法在明确接触条件下的完整任务表现。它不自动证明双层方法优于简单规则，更不能替代近期论文复现或真人负担实验。', '',
        f"双层联合相对固定分配的平均耗时变化为 {summary['dual']['elapsed_sim_s']-summary['fixed']['elapsed_sim_s']:+.2f} s，最大夹持滑移均值变化 {summary['dual']['navigation_max_slip_mm']-summary['fixed']['navigation_max_slip_mm']:+.2f} mm，最小边缘余量均值变化 {summary['dual']['min_edge_margin_mm']-summary['fixed']['min_edge_margin_mm']:+.2f} mm，最大倾角均值变化 {summary['dual']['navigation_max_tilt_deg']-summary['fixed']['navigation_max_tilt_deg']:+.2f}°。正负方向需按指标分别理解，不能统一写成性能提升。", '',
        '风险参与分配、任务成功、相对其他方法有优势，是三个不同层次的结论。特别要比较仅抓持／仅承载与统一降速：若联合方法没有占优，应保留这一结果。每场景仅两个种子，本报告不作统计显著性或普遍可靠性声明。', '',
        '## 协议与可复核性','',
        f"验证种子：{protocol['seeds']}。参数、源码 SHA-256 和实际实验列表见 protocol.json / results.json / trials.csv。冻结源码位于 `{(root/'source_snapshot').resolve()}`；各试次目录含场景 XML、原始输入、100 Hz 状态、风险日志与自动任务结果。", '',
        '五组共用已有夹持、阶段、滤波与载荷保护。统一降速仅将前后速度请求乘以 0.55；它没有对转向和手臂垂向运动统一减速。意图误差相对进入分配器前、已经过公共保护的请求计算，非对完整人体原始动作的误差。', '',
        '夹持摩擦正常/降低分别为 1.10/0.55；承载摩擦正常/降低分别为 0.80/0.16。降低夹持摩擦时托盘质量倍率为 1.15；降低承载摩擦时物件前后偏心为 35 mm。输入噪声为人为设置的 6 mm，不是设备实测。', '',
        '## 已发现的边界与开发失败','',
        '`risk_dev1`：夹持摩擦 0.28、质量倍率 1.35 时两组都出现过大夹持滑移，跟随保护禁止移动并超时；完整结果保留。较大手臂补偿还增加托盘倾角，因此后续加入手臂变化率限制并缩小速度上限。', '',
        '`risk_dev2`：承载摩擦 0.08 时物件在抬升阶段已滑离，前后分配无法补救垂向提起造成的不稳。后续增加物件脱离检测，正式本轮评估限定在能够完成抬升的接触范围。不能把这次场景收窄说成解决了极低摩擦承载。', '',
        '`risk_dev3`：最终场景参数开发试跑，固定与双层共 4 次完整任务。它与前两轮都不计入独立验证；所有开发结果保留在 outputs 下。', '',
        '其他边界：只分配共同前后自由度；理想接触力和物体状态不等于已有真实感知。线性短时边缘预测不保证避免掉落。优化不可行时会记录共同变化率约束的放宽，几何制动覆盖也独立记录。双层版本的 Quest 3 真人预实验尚未完成，实体机器人尚未验证。', '',
        '## 演示来源','',
        f"风险轨迹与视频固定选择两层受限场景、最小验证种子 {chosen['seed']} 的双层组（结果：{chosen['outcome']}）。视频只回放保存的物理状态，以 2 倍仿真速度播放，未修改物体轨迹。", '',
        '方法公式、操作步骤、记录位置及文献边界另见“双层风险版使用与方法.md”。']
    failures=[r for r in rows if r['outcome']!='success']
    if failures:
        lines+=['','## 本轮失败列表','']+[f"- {r['risk_scenario']} / {r['risk_policy']} / {r['seed']}：{r['reason']}" for r in failures]
    if (root/'evidence_checks.json').exists():
        checks=json.loads((root/'evidence_checks.json').read_text(encoding='utf-8'))
        runtime=checks['isolated_allocator_replay_ms']
        lines+=['','## 实现核查','',
            '26 项单元及传输回归检查通过；二维优化器与独立 SLSQP 求解结果对照。40 次运行的源码哈希与冻结记录一致，四种场景实际夹持／承载接触摩擦已从保存的物理状态复核。',
            f"分配器单独回放 {runtime['n']} 次，耗时中位数 {runtime['median']:.3f} ms、P95 {runtime['p95']:.3f} ms。这不包含物理、IK、网络或渲染，不是端到端 VR 延迟。",
            '网页模式切换、停止与试次流程通过传输测试；本轮本地浏览器预览工具不可用，未声称完成头显内视觉验收。']
    if (out/'补充探索与失败边界.md').exists():
        lines+=['','## 追加探索与结论边界','',
            '另有 20 次固定输入短测试，详见 [补充探索与失败边界](补充探索与失败边界.md)。前偏心组未充分激发承载风险；后偏心组全部在换向前的抬升阶段滑离。它们没有被并入 40 次完整任务，也没有被隐藏。',
            '当前证据支持“实现了可运行、可消融的前后风险分配原型”，尚不支持“联合方法整体优于固定规则”。后续应优先解决抬升阶段的姿态与垂向控制。']
    (out/'验证结果.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    for name in ('protocol.json','results.json','unit_tests.txt','environment.json','evidence_checks.json'):
        if (root/name).exists():shutil.copy2(root/name,out/name)
    shutil.copy2(Path(__file__).with_name('双层风险版使用与方法.md'),out/'双层风险版使用与方法.md')
    if video:render_video(session,out)
    (out/'先看这里.md').write_text('''# 双层风险版交付

先看“验证结果.md”与“五组任务对照.png”，再播放“双层风险版演示.mp4”。“风险与分配轨迹.png”展示两个接触界面如何影响底盘和手臂指令；“补充探索与失败边界.md”保留额外短测试与抬升失稳。

根目录双击“启动Quest3双层风险版.cmd”，电脑／头显浏览器打开 http://localhost:8768。先用正常场景、P00 预实验试跑，操作见“双层风险版使用与方法.md”。

这是已经实现并做自动物理对照的研究原型。是否有充分创新性与性能优势，需结合消融结果、完整查新和真人实验；不能将自动脚本结果写成真人结果，也不能保证国创等第。
''',encoding='utf-8')
    checks={p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*') if p.is_file() and p.name!='SHA256.json'}
    (out/'SHA256.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2));print(out)

def render_video(root,out,preview_only=False):
    parts=[]
    for file in sorted(root.glob('states_*.npz')):
        with np.load(file) as a:parts.append({k:a[k].copy() for k in a.files})
    data={k:np.concatenate([a[k] for a in parts]) for k in parts[0]}
    risks=[json.loads(l) for l in (root/'risk_control.jsonl').read_text(encoding='utf-8').splitlines()]
    result=json.loads((root/'benchmark_result.json').read_text(encoding='utf-8'))
    events=json.loads((root/'generator_events.json').read_text(encoding='utf-8'))
    labels={'calibrate':'标定','approach':'接近把手','close':'双侧夹持','lift':'抬升','navigate':'绕障搬运','lower':'下放承重','release':'松开夹爪','retreat':'撤回双手'}
    model=mujoco.MjModel.from_xml_path(str(root/'scene.xml'));state=mujoco.MjData(model)
    renderer=mujoco.Renderer(model,720,960);camera=mujoco.MjvCamera()
    camera.lookat[:]=[-.25,.9,.70];camera.distance=4.5;camera.azimuth=215;camera.elevation=-27
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',26);small=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',20)
    def frame(t):
        i=min(np.searchsorted(data['sim_time'],t),len(risks)-1,len(data['sim_time'])-1);r=risks[i]
        state.qpos[:]=data['qpos'][i];state.qvel[:]=data['qvel'][i];state.ctrl[:]=data['ctrl'][i];state.time=data['sim_time'][i]
        mujoco.mj_forward(model,state);renderer.update_scene(state,camera=camera)
        canvas=Image.new('RGB',(1280,720),'#112b3c');canvas.paste(Image.fromarray(renderer.render()),(0,0));draw=ImageDraw.Draw(canvas)
        draw.rectangle((0,0,1280,88),fill='#112b3c');draw.text((24,13),'灵驭｜双层接触风险驱动的双臂—底盘分配',font=font,fill='white')
        draw.text((24,54),'保存的物理轨迹 · 合成输入 · 两层接触受限 · 2 倍仿真速度',font=small,fill='#99ded9')
        draw.text((982,115),f'仿真 {state.time:.1f} s',font=font,fill='white')
        for y,key,label,color in [(181,'grip','夹爪—托盘','#70a4d6'),(279,'payload','托盘—物件','#efb75d')]:
            draw.text((982,y),label,font=small,fill='white');draw.text((1184,y),f"{r[key]:.2f}",font=small,fill=color)
            draw.rounded_rectangle((982,y+36,1255,y+49),radius=5,fill='#344c5d')
            if r[key]>.005:draw.rounded_rectangle((982,y+36,982+273*r[key],y+49),radius=5,fill=color)
        draw.text((982,369),'指令分配 / m/s',font=small,fill='#99ded9')
        active=r['allocation_active']
        for y,key,label in [(412,'requested_m_s','分配前请求'),(452,'base_m_s','底盘'),(492,'arm_relative_m_s','手臂相对运动')]:
            draw.text((982,y),label,font=small,fill='white');draw.text((1173,y),f"{r.get(key,0):+.3f}" if active else '—',font=small,fill='#99ded9')
        draw.text((982,557),'物件边缘余量',font=small,fill='white');draw.text((982,590),f"{r['edge_margin_m']*1000:.1f} mm",font=font,fill='#efb75d')
        phase='calibrate'
        for event in events:
            if event['time']<=t:phase=event['phase']
        draw.rectangle((0,650,960,720),fill='#112b3c');draw.text((24,667),labels[phase],font=font,fill='#99ded9')
        if t>=data['sim_time'][-1]-.2:draw.text((420,670),'物理判据：'+('完整任务成功' if result['outcome']=='success' else result['reason']),font=small,fill='white')
        return np.asarray(canvas)
    try:
        for label,t in [('抬升',8.),('分配',14.),('搬运',35.),('放置',data['sim_time'][-1])]:Image.fromarray(frame(t)).save(out/f'{label}.png')
        if preview_only:return
        with imageio.get_writer(out/'双层风险版演示.mp4',fps=25,codec='libx264',quality=8,macro_block_size=None,ffmpeg_params=['-pix_fmt','yuv420p','-movflags','+faststart']) as writer:
            for t in np.arange(0,data['sim_time'][-1]+.01,.08):writer.append_data(frame(t))
            for _ in range(25):writer.append_data(frame(data['sim_time'][-1]))
        provenance={'session':str(root.resolve()),'seed':result['seed'],'scenario':result['risk_scenario'],
            'selection':'combined scenario, dual policy, minimum validation seed; no success filtering',
            'source':'synthetic_transport_test','outcome':result['outcome'],'playback_speed':2,'fps':25,'physical_states_modified':False}
        (out/'video_provenance.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2),encoding='utf-8')
    finally:renderer.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root');parser.add_argument('--delivery');parser.add_argument('--video',action='store_true')
    report(**vars(parser.parse_args()))
