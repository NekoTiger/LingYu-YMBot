"""Analyze fixed-parameter validation separately from development."""
import json,csv,math
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import mujoco
from scene import make_scene
from scipy.stats import binomtest
from analyze import wilson
from build_model import HERE

def relative_metrics(root):
    cache={}
    for summary in root.rglob('summary.json'):
        p=summary.parent
        if not (p/'trajectory.npz').exists():continue
        r=json.loads(summary.read_text(encoding='utf-8'));t=np.load(p/'trajectory.npz')
        err=(t['hand_actual'][:,:3]-t['hand_actual'][:,3:6])-(t['hand_targets'][:,:3]-t['hand_targets'][:,3:6])
        mask=(t['time']>=5.5)&(t['time']<38.5)
        # World separation includes common yaw lag. The relative task itself
        # lives in the right-hand frame, so evaluate in that frame as well.
        r['world_separation_rmse_m']=float(np.sqrt(np.mean(np.sum(err[mask]**2,axis=1))))
        if r['task'] not in cache:
            mm,dd,_=make_scene(r['task'],r['seed'],r['disturbance']);cache[r['task']]=(mm,dd)
        mm,dd=cache[r['task']]
        indices=np.flatnonzero(mask);cmd=t['hand_targets'][indices];qposes=t['qpos']
        desired=cmd[:,:3]-cmd[:,3:6];c=np.cos(cmd[:,8]);s=np.sin(cmd[:,8])
        wanted=np.column_stack([c*desired[:,0]+s*desired[:,1],-s*desired[:,0]+c*desired[:,1],desired[:,2]])
        errors=[];angles=[]
        for k,index in enumerate(indices):
            dd.qpos[:]=qposes[index];mujoco.mj_kinematics(mm,dd)
            rr=dd.site('right_ee').xmat.reshape(3,3);ll=dd.site('left_ee').xmat.reshape(3,3)
            relative=rr.T@(dd.site('left_ee').xpos-dd.site('right_ee').xpos)
            errors.append(np.sum((relative-wanted[k])**2))
            angles.append(np.arccos(np.clip((np.trace(rr.T@ll)-1)/2,-1,1)))
        r['relative_position_rmse_m']=float(np.sqrt(np.mean(errors)))
        r['relative_orientation_rmse_deg']=float(np.rad2deg(np.sqrt(np.mean(np.square(angles)))))
        summary.write_text(json.dumps(r,indent=2,ensure_ascii=False),encoding='utf-8')

def main():
    root=HERE/'outputs/ablation';rows=json.loads((root/'results.json').read_text(encoding='utf-8'))
    if len(rows)!=192:raise RuntimeError('Ablation not complete')
    relative_metrics(root)
    relative_metrics(HERE/'outputs/benchmark')
    rows=[]
    for p in sorted(root.rglob('summary.json')):
        r=json.loads(p.read_text(encoding='utf-8'));r['split']=p.parent.parent.name;rows.append(r)
    (root/'results.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    validation=[r for r in rows if r['split']=='validation']
    dest=HERE/'outputs/analysis';groups=[]
    methods=['independent','coordinated','coupled'];amps=[0,.018,.035,.05]
    colors=['#cc8336','#6586a8','#148777'];labels=['独立控制','底盘反馈补偿','反馈 + 双臂相对约束']
    for amp in amps:
        for method in methods:
            rr=[r for r in validation if r['mode']==method and r['disturbance']==amp]
            k=sum(r['success'] for r in rr);ci=wilson(k,len(rr));successes=[r for r in rr if r['success']]
            groups.append(dict(amplitude_mm=amp*1000,method=method,n=len(rr),successes=k,ci95_low=ci[0],ci95_high=ci[1],rmse_mm=float(np.mean([r['ee_rmse_m'] for r in rr])*1000),relative_rmse_mm=float(np.mean([r['relative_position_rmse_m'] for r in rr])*1000),relative_orientation_rmse_deg=float(np.mean([r['relative_orientation_rmse_deg'] for r in rr])),placement_success_mm=float(np.mean([r['placement_error_m'] for r in successes])*1000) if successes else None))
    (dest/'validation_aggregate.json').write_text(json.dumps(groups,indent=2),encoding='utf-8')
    with (dest/'validation_aggregate.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(groups[0]));w.writeheader();w.writerows(groups)
    plt.rcParams.update({'font.family':'Microsoft YaHei','font.size':12,'axes.spines.top':False,'axes.spines.right':False,'figure.dpi':150})
    fig,axs=plt.subplots(1,3,figsize=(15,4.7),layout='constrained')
    for meth,col,lab in zip(methods,colors,labels):
        gg=[g for g in groups if g['method']==meth];x=np.array([g['amplitude_mm'] for g in gg]);y=np.array([g['successes']/g['n']*100 for g in gg])
        lo=y-np.array([g['ci95_low']*100 for g in gg]);hi=np.array([g['ci95_high']*100 for g in gg])-y
        axs[0].errorbar(x,y,yerr=[np.maximum(lo,0),np.maximum(hi,0)],color=col,label=lab,marker='o',capsize=4)
        axs[1].plot(x,[g['rmse_mm'] for g in gg],'-o',color=col,label=lab)
        axs[2].plot(x,[g['relative_rmse_mm'] for g in gg],'-o',color=col,label=lab)
    axs[0].set_ylabel('任务成功率 (%)');axs[0].set_ylim(-6,106)
    axs[1].set_ylabel('双手世界位置 RMSE (mm)');axs[2].set_ylabel('右手坐标系内相对位置 RMSE (mm)')
    for ax in axs:ax.set_xlabel('底盘扰动幅值 A (mm)');ax.set_xticks([0,18,35,50]);ax.grid(alpha=.2)
    axs[0].legend(loc='lower left',fontsize=9)
    fig.suptitle('双臂搬运独立验证  |  新种子 100–111，每条件 12 次，共 144 次',fontsize=16)
    fig.savefig(dest/'validation.png');fig.savefig(dest/'validation.svg');plt.close(fig)
    # Matched outcomes; exploratory p-values, not corrected for multiple tests.
    comparisons=[]
    for amp in amps:
        a={r['seed']:r for r in validation if r['mode']=='coordinated' and r['disturbance']==amp}
        b={r['seed']:r for r in validation if r['mode']=='coupled' and r['disturbance']==amp}
        wins=sum(b[s]['success'] and not a[s]['success'] for s in a);losses=sum(a[s]['success'] and not b[s]['success'] for s in a)
        pval=binomtest(wins,wins+losses,.5).pvalue if wins+losses else 1.
        comparisons.append({'amplitude_mm':amp*1000,'coupling_wins':wins,'coupling_losses':losses,'paired_exact_p_exploratory':pval})
    (dest/'paired_validation.json').write_text(json.dumps(comparisons,indent=2),encoding='utf-8')
    text=['# 双臂协调改进与独立验证','', '第一轮 192 次实验发现，世界坐标反馈能降低手部误差，但较大扰动下双臂托盘仍会滑脱。因此增加双手相对位姿软约束，在相同物理模型和关节伺服下优先维持共同夹持几何关系。代价是世界位置误差可能增加。','', '参数在开发种子 0 上确定为：相对位置成本 50、相对姿态成本 10；随后固定参数。先补齐开发种子 0–11 的 48 次实验，再对新种子 100–111 做三种方法 × 四档扰动的 144 次配对验证。加上第一轮，共 384 次完整记录。开发与验证分开汇总。','', '| 扰动 | 方法 | 成功次数 | 世界位置 RMSE | 相对位置 RMSE |','|---:|---|---:|---:|---:|']
    for g in groups:
        text.append(f"| {g['amplitude_mm']:.0f} mm | {labels[methods.index(g['method'])]} | {g['successes']}/{g['n']} | {g['rmse_mm']:.2f} mm | {g['relative_rmse_mm']:.2f} mm |")
    text+=['','成功判据使用最后连续 1 秒的到位、静止、松手与载荷保留检查，详见 evaluation.py 和实验结果.md。误差在所有试验上统计，失败试验也包含在内。放置误差均值只对成功试验计算，并明确记录为 placement_success_mm。','', '相对位置指标在右手实际坐标系中计算：R_right^T (p_left - p_right)，对照目标的同一相对变换。该指标由保存的关节轨迹重新做正运动学得到，统计 5.5–38.5 秒整个夹持目标阶段（包括掉落之后，未按成功截断）。世界坐标下的双手间向量误差另记 world_separation_rmse_m；它混入整体偏航跟踪误差，不能与手内坐标指标混用。','', '12/12 成功的 Wilson 95% 区间为约 [75.8%, 100%]。当前只验证有限参数范围和预设任务，不能外推到任意物体、真人输入或真机。','', '相对约束本身是已有机器人控制方法。本轮可主张的进展是：针对所用平台发现独立末端补偿的接触失稳问题，加入相对任务约束，并在未调参种子上进行了可复现消融验证。尚不能主张首创该理论。','', '主视频采用开发种子 0、A=35 mm；它是演示案例，不能代表全部试验。正式验证统计来自另列的 144 次新种子结果。','', '配对精确检验保存在 paired_validation.json，仅作探索分析，未作多重比较校正。最重要的证据是配对成功次数、误差和完整失败轨迹。']
    (dest/'改进与验证.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
    print(json.dumps(groups,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
