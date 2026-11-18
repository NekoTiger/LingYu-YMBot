"""Recompute tables, uncertainty intervals and figures from trial summaries."""
from pathlib import Path
import json,math,csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from build_model import HERE

def wilson(k,n):
    z=1.96;p=k/n;c=(p+z*z/(2*n))/(1+z*z/n);h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/(1+z*z/n)
    return c-h,c+h

def analyze():
    root=HERE/'outputs/benchmark';rows=json.loads((root/'results.json').read_text(encoding='utf-8'))
    protocol=json.loads((root/'protocol.json').read_text(encoding='utf-8'))
    if len(rows)!=protocol['trials']:raise RuntimeError('Benchmark not complete')
    if any('error' in r for r in rows):raise RuntimeError('Benchmark contains runtime errors')
    dest=HERE/'outputs/analysis';dest.mkdir(exist_ok=True)
    groups=[]
    for task in ['single','bimanual']:
        for amp in protocol['disturbance_m']:
            for method in ['independent','coordinated']:
                rr=[r for r in rows if r['task']==task and r['disturbance']==amp and r['mode']==method]
                k=sum(r['success'] for r in rr);ci=wilson(k,len(rr))
                good=[r['placement_error_m']*1000 for r in rr if r['success']]
                groups.append(dict(task=task,amplitude_mm=amp*1000,method=method,n=len(rr),successes=k,success_rate=k/len(rr),ci95_low=ci[0],ci95_high=ci[1],mean_rmse_mm=float(np.mean([r['ee_rmse_m'] for r in rr])*1000),placement_success_mm=float(np.mean(good)) if good else None,mean_transport_tilt_deg=float(np.mean([r['transport_max_tilt_deg'] for r in rr]))))
    (dest/'aggregate.json').write_text(json.dumps(groups,indent=2),encoding='utf-8')
    with (dest/'aggregate.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(groups[0]));w.writeheader();w.writerows(groups)
    plt.rcParams.update({'font.family':'Microsoft YaHei','font.size':12,'axes.spines.top':False,'axes.spines.right':False,'figure.dpi':150})
    colors={'independent':'#d88738','coordinated':'#138c78'}
    labels={'independent':'独立控制基线','coordinated':'协调补偿'}
    fig,axs=plt.subplots(2,2,figsize=(12,8),layout='constrained')
    for col,task in enumerate(['single','bimanual']):
        for method in labels:
            gg=[g for g in groups if g['task']==task and g['method']==method]
            x=np.array([g['amplitude_mm'] for g in gg]);y=np.array([g['success_rate']*100 for g in gg])
            lo=y-np.array([g['ci95_low']*100 for g in gg]);hi=np.array([g['ci95_high']*100 for g in gg])-y
            axs[0,col].errorbar(x,y,yerr=[np.maximum(lo,0),np.maximum(hi,0)],marker='o',capsize=4,color=colors[method],label=labels[method])
            axs[1,col].plot(x,[g['mean_rmse_mm'] for g in gg],'-o',color=colors[method],label=labels[method])
        axs[0,col].set_title('单臂取物搬运' if task=='single' else '双臂托盘搬运')
        axs[0,col].set_ylabel('成功率 (%) · Wilson 95% 区间');axs[0,col].set_ylim(-6,106)
        axs[1,col].set_ylabel('末端位置 RMSE (mm)')
        for ax in axs[:,col]:ax.set_xlabel('底盘扰动幅值 A (mm)');ax.set_xticks([0,18,35,50]);ax.grid(alpha=.18)
    axs[0,0].legend(loc='lower left');fig.suptitle('192 次配对仿真  |  每组 12 个随机种子',fontsize=18)
    fig.savefig(dest/'robustness.png');fig.savefig(dest/'robustness.svg');plt.close(fig)
    a=np.loadtxt(root/'bimanual_independent_a18_s00/metrics.csv',delimiter=',',skiprows=1)
    b=np.loadtxt(root/'bimanual_coordinated_a18_s00/metrics.csv',delimiter=',',skiprows=1)
    fig,axs=plt.subplots(3,1,figsize=(12,8),sharex=True,layout='constrained')
    for arr,method in [(a,'independent'),(b,'coordinated')]:
        axs[0].plot(arr[:,0],arr[:,1]*1000,label=labels[method],color=colors[method],lw=1.2)
        axs[1].plot(arr[:,0],arr[:,4],color=colors[method],lw=1.4)
        axs[2].plot(arr[:,0],np.rad2deg(arr[:,5]),color=colors[method],lw=1.2)
    axs[0].set_ylabel('末端误差 (mm)');axs[1].set_ylabel('托盘高度 (m)');axs[2].set_ylabel('托盘倾角 (°)');axs[2].set_xlabel('时间 (s)')
    for ax in axs:ax.grid(alpha=.2)
    axs[0].legend();fig.suptitle('双臂搬运对照  |  A = 18 mm，seed = 0',fontsize=18)
    fig.savefig(dest/'paired_episode.png');fig.savefig(dest/'paired_episode.svg');plt.close(fig)
    lines=['# 灵驭仿真实验结果','', '以下数据由 `analyze.py` 从 192 次实验自动汇总。每个条件 12 个种子；两种方法使用相同的质量、摩擦、物体位置和扰动。输入为合成手部目标，不能解释为真人 VR 用户实验。','', '| 任务 | 扰动 A | 基线成功 | 补偿成功 | 基线 RMSE | 补偿 RMSE |','|---|---:|---:|---:|---:|---:|']
    for task in ['single','bimanual']:
        for amp in protocol['disturbance_m']:
            gg=[g for g in groups if g['task']==task and g['amplitude_mm']==amp*1000];a,b=gg
            lines.append(f"| {'单臂' if task=='single' else '双臂'} | {amp*1000:.0f} mm | {a['successes']}/{a['n']} | {b['successes']}/{b['n']} | {a['mean_rmse_mm']:.2f} mm | {b['mean_rmse_mm']:.2f} mm |")
    lines+=['','每个 12/12 成功组的 Wilson 95% 区间下界约为 75.8%，不能据此声称真实成功率为 100%。完整区间见 aggregate.csv。','', '## 评价定义','', '评价版本 2.0。成功必须同时满足：曾提升超过 7 cm，且提升后的夹爪接触累计不少于 0.5 秒；最后连续 1 秒内，水平误差小于 5 cm、桌面高度误差小于 3.5 cm、夹爪已经松开、线速度小于 0.02 m/s、角速度小于 0.1 rad/s、物体倾角小于 10°；双臂任务还要求独立载荷仍在托盘局部范围内。','', '所有任务固定运行 43 秒，因此本实验不能支持“任务完成时间缩短”的结论。','', '## 对照的适用范围','', '基线在名义底盘坐标下解算上肢关节；补偿组使用实际底盘位姿更新同一 IK 模型。两组共用关节限制、伺服参数、运动目标和接触模型。对照量化的是加入底盘反馈的收益，不是与 HoMeR、Mobile ALOHA 等完整系统的排名。','', '底盘横向与纵向扰动分别为 A 和 0.65A，偏航扰动为 0.9A 弧度；频率分别为 0.65、0.47、0.39 Hz。A=0 时仍存在动力学伺服跟随误差。实验仅覆盖这一扰动族。','', '## 原始证据','', '每次实验保留 summary.json、metrics.csv 和 trajectory.npz。trajectory.npz 包含 100 Hz 的 qpos、qvel、ctrl、双手目标及实际位置；手部目标姿态由基座名义偏航角确定。物理步长 2 ms，控制周期 10 ms。所有失败案例均保留。']
    (dest/'实验结果.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(groups,ensure_ascii=False,indent=2))

if __name__=='__main__':analyze()
