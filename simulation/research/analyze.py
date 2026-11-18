"""All-trial analysis; no success-only filtering of kinematic quality metrics."""
from pathlib import Path
from collections import defaultdict,Counter
import argparse,json,csv
import numpy as np,mujoco
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.stats import binomtest

HERE=Path(__file__).resolve().parent
METHODS={'adaptive':'直接跟踪','stable':'仅腰部稳定','shared_free_waist':'去掉腰部稳定','shared_no_contact':'去掉支撑反馈','shared_no_frame':'去掉坐标补偿','shared':'完整方法'}
def condition(r):
    if not r['safety']:return 'without_safety'
    if r['noise']==0:return 'clean'
    return 'tracking' if r['noise']<.01 else 'severe'
def ci(k,n):
    p=k/n;z=1.95996398454;den=1+z*z/n;c=(p+z*z/(2*n))/den;h=z*np.sqrt(p*(1-p)/n+z*z/(4*n*n))/den;return [c-h,c+h]

def analyze(folder):
    root=Path(folder);out=root.parent/(root.name+'_analysis');out.mkdir(exist_ok=True);rs=json.loads((root/'results.json').read_text(encoding='utf-8'))
    m=None;trialmetrics=[]
    for r in rs:
        trial=root/r['trial_name'];z=np.load(trial/'trajectory.npz');q=z['qpos'];vel=z['qvel'];raw=z['metrics'];ids=z['phase'];targets=z['targets'];mask=np.array([r['phases'][p]=='navigate' for p in ids])
        if m is None:m=mujoco.MjModel.from_xml_path(str(trial/'scene.xml'));d=mujoco.MjData(m)
        qi=[int(m.joint('Body_Joint'+str(j)).qposadr[0])for j in [1,2,3]];vi=[int(m.joint('Body_Joint'+str(j)).dofadr[0])for j in [1,2,3]]
        extra={'condition':condition(r),'waist_peak_to_peak_deg':None,'waist_rms_velocity_deg_s':None,'hand_rmse_mm':None,'navigation_s':float(mask.sum()*.01)}
        if mask.sum()>20:
            extra['waist_peak_to_peak_deg']=float(np.max(np.ptp(np.rad2deg(q[mask][:,qi]),axis=0)))
            extra['waist_rms_velocity_deg_s']=float(np.sqrt(np.mean(np.rad2deg(vel[mask][:,vi])**2)))
            errs=[]
            for i in np.flatnonzero(mask)[::10]:
                d.qpos[:]=q[i];mujoco.mj_kinematics(m,d)
                hands=np.array([d.site(s+'_ee').xpos for s in ['left','right']]);errs.append(np.sum((hands-targets[i,:6].reshape(2,3))**2,axis=1).mean())
            extra['hand_rmse_mm']=float(np.sqrt(np.mean(errs))*1000)
        trialmetrics.append({**r,**extra})
    (out/'per_trial.json').write_text(json.dumps(trialmetrics,ensure_ascii=False,indent=2),encoding='utf-8');groups=defaultdict(list)
    for r in trialmetrics:groups[(r['condition'],r['method'])].append(r)
    aggregate=[]
    for (cond,method),rows in sorted(groups.items()):
        n=len(rows);k=sum(r['success'] for r in rows);good=[r for r in rows if r['success']]
        def avg(key,subset=rows):
            vals=[r[key] for r in subset if r[key] is not None];return float(np.mean(vals))if vals else None
        aggregate.append({'condition':cond,'method':method,'n':n,'success':k,'ci95':ci(k,n),'mean_success_time_s':avg('completion_time_s',good),'waist_peak_to_peak_deg':avg('waist_peak_to_peak_deg'),'waist_rms_velocity_deg_s':avg('waist_rms_velocity_deg_s'),'hand_rmse_mm':avg('hand_rmse_mm'),'mean_slip_mm':1000*avg('max_slip_m'),'mean_wait_s':avg('safety_wait_s'),'collision_episodes':sum(r['obstacle_contact_frames']>0 for r in rows),'failed_before_navigation':sum(r['navigation_s']<.2 for r in rows),'failure_reasons':dict(Counter(r['failure'] for r in rows if r['failure']))})
    (out/'aggregate.json').write_text(json.dumps(aggregate,ensure_ascii=False,indent=2),encoding='utf-8')
    with (out/'aggregate.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(aggregate[0]));w.writeheader();w.writerows(aggregate)
    plt.rcParams.update({'font.sans-serif':['Microsoft YaHei'],'axes.unicode_minus':False,'font.size':11})
    ms=['adaptive','stable','shared_free_waist','shared_no_contact','shared_no_frame','shared'];colors=['#93a3b1','#6c88aa','#d2ac6d','#9b8ab4','#58aaa8','#127e78']
    fig,axes=plt.subplots(1,3,figsize=(17,5.8));fig.subplots_adjust(top=.80,bottom=.24,wspace=.32)
    fig.suptitle(f'动态障碍与遥操作输入扰动：{len(rs)} 次独立验证',fontsize=20,fontweight='bold')
    for ax,cond,title in [(axes[0],'clean','清洁输入 / 同样动态障碍'),(axes[1],'tracking','6 mm 噪声 / 80 ms 延迟 / 10% 丢包')]:
        for i,method in enumerate(ms):
            a=next(a for a in aggregate if a['condition']==cond and a['method']==method);rate=a['success']/a['n'];lo,hi=a['ci95']
            ax.bar(i,rate,color=colors[i]);ax.errorbar(i,rate,yerr=[[rate-lo],[hi-rate]],fmt='none',ecolor='#22323f',capsize=3);ax.text(i,rate+.065,f"{a['success']}/{a['n']}",ha='center',fontsize=11)
        ax.set_ylim(0,1.22);ax.set_yticks([0,.5,1],['0%','50%','100%']);ax.set_xticks(range(len(ms)),[METHODS[s] for s in ms],rotation=40,ha='right',fontsize=10);ax.set_title(title,fontsize=12)
    for i,method in enumerate(ms):
        vals=[r['waist_peak_to_peak_deg']for r in groups[('tracking',method)] if r['waist_peak_to_peak_deg']is not None]
        axes[2].scatter(np.full(len(vals),i)+np.linspace(-.12,.12,len(vals)),vals,color=colors[i],s=25)
        if vals:axes[2].plot([i-.22,i+.22],[np.median(vals)]*2,color=colors[i],lw=3)
    axes[2].set_title('搬运期间腰部最大角度变化范围',fontsize=12);axes[2].set_ylabel('°（三个关节取最大值）');axes[2].set_xticks(range(len(ms)),[METHODS[s]for s in ms],rotation=40,ha='right',fontsize=10)
    for ax in axes:ax.spines[['top','right']].set_visible(False)
    fig.text(.03,.025,'成功必须通过接触、抬升、无碰撞、松手和末尾稳定检查。误差线为 Wilson 95% 区间。输入为合成数据，未验证真实 VR 用户。',fontsize=10,color='#536474')
    fig.savefig(out/'research_results.png',dpi=160);fig.savefig(out/'research_results.pdf');plt.close(fig)
    # Compare waist stabilization within the same complete input pipeline.
    pairs=[]
    for cond in ['clean','tracking']:
        lookup={method:{r['seed']:r for r in groups[(cond,method)]}for method in ['shared','shared_free_waist','adaptive']}
        for baseline in ['shared_free_waist','adaptive']:
            common=sorted(set(lookup['shared'])&set(lookup[baseline]));wins=sum(lookup['shared'][s]['success'] and not lookup[baseline][s]['success']for s in common);loss=sum(not lookup['shared'][s]['success'] and lookup[baseline][s]['success']for s in common)
            pairs.append({'condition':cond,'baseline':baseline,'wins':wins,'losses':loss,'p':float(binomtest(wins,wins+loss,.5).pvalue)if wins+loss else 1.})
    (out/'paired_tests.json').write_text(json.dumps(pairs,indent=2),encoding='utf-8')
    print(json.dumps(aggregate,ensure_ascii=False,indent=2))
    return out,aggregate

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder',nargs='?',default=str(HERE/'outputs/validation'));a=p.parse_args();analyze(a.folder)
