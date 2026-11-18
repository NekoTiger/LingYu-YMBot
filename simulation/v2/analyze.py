from pathlib import Path
import json,csv,math
from collections import defaultdict
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.stats import binomtest
from model import HERE

def wilson(k,n):
    z=1.95996398454;p=k/n;den=1+z*z/n;c=(p+z*z/(2*n))/den;half=z*np.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return [c-half,c+half]

root=HERE/'outputs/validation';results=json.loads((root/'results.json').read_text(encoding='utf-8'));groups=defaultdict(list)
for row in results:groups[('nominal' if row['load_scale']==1 else 'heavy_slippery',row['target_height'],row['method'])].append(row)
out=HERE/'outputs/analysis';out.mkdir(parents=True,exist_ok=True);aggregate=[]
for (condition,h,method),rows in sorted(groups.items()):
    n=len(rows);k=sum(r['success'] for r in rows);good=[r for r in rows if r['success']]
    aggregate.append(dict(condition=condition,target_height=h,method=method,n=n,success=k,rate=k/n,ci95=wilson(k,n),mean_time_success=np.mean([r['completion_time_s'] for r in good]).item() if good else None,mean_max_slip_mm=np.mean([r['max_slip_m']*1000 for r in rows]).item(),max_base_tilt_deg=max(r['max_base_tilt_deg'] for r in rows),failures={f:sum(r['failure']==f for r in rows) for f in set(r['failure'] for r in rows) if f is not None}))
(out/'aggregate.json').write_text(json.dumps(aggregate,ensure_ascii=False,indent=2),encoding='utf-8')
with (out/'aggregate.csv').open('w',newline='',encoding='utf-8-sig') as f:
    writer=csv.DictWriter(f,fieldnames=aggregate[0].keys());writer.writeheader();writer.writerows(aggregate)
heavy={method:{r['seed']:r for r in results if r['load_scale']>1 and r['method']==method} for method in ['uncoupled','coupled','grip','adaptive']}
paired={}
for method in ['grip','adaptive']:
    wins=sum(not heavy['coupled'][s]['success'] and heavy[method][s]['success'] for s in heavy[method]);losses=sum(heavy['coupled'][s]['success'] and not heavy[method][s]['success'] for s in heavy[method])
    paired[method]={'baseline':'coupled','paired_wins':wins,'paired_losses':losses,'exact_mcnemar_p':float(binomtest(wins,wins+losses,.5).pvalue) if wins+losses else 1.}
(out/'paired.json').write_text(json.dumps(paired,indent=2),encoding='utf-8')
plt.rcParams.update({'font.sans-serif':['Microsoft YaHei'],'axes.unicode_minus':False,'font.size':12,'figure.facecolor':'#f7f9fb','axes.facecolor':'#f7f9fb'})
methods=['uncoupled','coupled','grip','adaptive'];labels=['独立双臂\n固定夹持','耦合双臂\n固定夹持','耦合双臂\n反馈夹持','反馈夹持\n与自适应限速'];colors=['#9ba6b3','#607e9f','#36a7a2','#167e70']
fig,axes=plt.subplots(1,3,figsize=(16,5.4));fig.subplots_adjust(top=.78,bottom=.20,wspace=.38)
fig.suptitle('轮地接触模型：128 次独立验证',fontsize=21,fontweight='bold',y=.97)
fig.text(.5,.88,'3 种目标高度 × 4 种控制器 × 8 个种子；另有 32 次重载低摩擦测试',ha='center',color='#526477',fontsize=12)
for ax,cond,title in [(axes[0],'nominal','常规任务：55 / 70 / 75 cm'),(axes[1],'heavy_slippery','重载 + 低摩擦 + 8 N·m 偏航扰动')]:
    for i,method in enumerate(methods):
        subset=[r for r in results if (r['load_scale']==1)==(cond=='nominal') and r['method']==method];n=len(subset);k=sum(r['success'] for r in subset);lo,hi=wilson(k,n)
        ax.bar(i,k/n,color=colors[i],width=.62);ax.errorbar(i,k/n,yerr=[[k/n-lo],[hi-k/n]],fmt='none',ecolor='#22323f',capsize=4)
        ax.text(i,k/n+.075,f'{k}/{n}',ha='center',fontsize=13,fontweight='bold')
    ax.set_title(title,fontsize=12);ax.set_ylim(0,1.23);ax.set_yticks([0,.5,1],['0%','50%','100%']);ax.set_xticks(range(4),labels,fontsize=10);ax.spines[['top','right']].set_visible(False)
for i,method in enumerate(methods):
    vals=np.array([r['max_slip_m']*1000 for r in heavy[method].values()]);axes[2].scatter(np.full(len(vals),i)+np.linspace(-.10,.10,len(vals)),vals,color=colors[i],s=36)
    axes[2].plot([i-.22,i+.22],[np.median(vals)]*2,color=colors[i],lw=4)
axes[2].set_xticks(range(4),labels,fontsize=10);axes[2].set_title('重载任务中的最大夹持滑移',fontsize=12);axes[2].set_ylabel('mm（包含失败轨迹）');axes[2].spines[['top','right']].set_visible(False)
fig.text(.02,.035,'误差线为 Wilson 95% 区间；状态由仿真直接读取，未验证视觉感知、VR 硬件和真机。',fontsize=10,color='#526477')
fig.savefig(out/'validation.png',dpi=160);fig.savefig(out/'validation.pdf');plt.close(fig)
lines=['# V2 仿真验证报告','','本轮把底盘换成自由车体与轮地接触，加入接触驱动的阶段切换、几何绕障路径和滑移反馈夹持。与 V1 的底盘位置伺服模型分开统计。','','## 预先固定的验证方案','','开发只用种子 0、1；以下使用 200–207。常规任务三种高度（55、70、75 cm），另有重载低摩擦条件。每个场景的四种方法使用相同物理参数和扰动，共 128 次。参数与运行时源码 SHA-256 在 `validation/protocol.json`。','','常规托盘主体质量 0.45–0.75 kg，重载为其 2.5 倍；两把手和松散物件共 0.17 kg。常规摩擦系数 0.9–1.5，重载为其 0.35 倍。手指垫与把手同步设置摩擦系数，避免 MuJoCo 取接触对最大摩擦系数导致扫描无效。重载在进入直行段后施加 8 N·m、持续 1 s 的底盘偏航外力矩；未能抬起的试验不会进入该扰动阶段。','','## 全量结果','','|条件|台面/cm|方法|成功|成功试验平均耗时/s|最大滑移均值/mm|','|---|---:|---|---:|---:|---:|']
for a in aggregate:lines.append(f"|{a['condition']}|{a['target_height']*100:.0f}|{a['method']}|{a['success']}/{a['n']}|{a['mean_time_success']:.2f}|{a['mean_max_slip_mm']:.2f}|" if a['mean_time_success'] is not None else f"|{a['condition']}|{a['target_height']*100:.0f}|{a['method']}|{a['success']}/{a['n']}|—|{a['mean_max_slip_mm']:.2f}|")
lines+=['','方法：uncoupled 为无双臂相对约束；coupled 增加 Mink 双臂相对位姿任务；grip 再增加根据下滑量调整夹紧预载；adaptive 再根据跟踪误差、倾角与滑移速度调节轮速。所有方法均使用相同的位姿反馈、物理模型、关节限位、轮速斜坡和接触阶段守卫。','','## 成功标准','','必须先验证双侧夹持、抬升，再完成绕障、放置、松手、撤手。末尾连续 1 s 满足：平面误差 < 35 mm，高度误差 < 10 mm，线速度 < 0.02 m/s，角速度 < 0.1 rad/s，倾角 < 0.12 rad，两手无托盘接触，散件仍在托盘区域；整个任务没有检测到机器人/货物与中间障碍物的接触。失败与超时均保留在分母中。','','## 配对比较','']
for method,p in paired.items():lines.append(f"- {method} 相对 coupled：{p['paired_wins']} 个由失败变成功，{p['paired_losses']} 个由成功变失败；精确 McNemar p={p['exact_mcnemar_p']:.5f}。样本量只有 8 对，不能外推为真实部署成功率。")
lines+=['','## 如何解读','','常规任务用于证明执行能力，不能据此声称改进算法优于基线。重载结果须结合 grip 消融一起看，不能把反馈夹持的收益全部归因于限速。最大滑移统计只包含抬升、搬运、对准阶段；失败时的滑落也计入，不能当作“仅成功抓取”的精度。','','## 保留的限制','','- VR 位姿映射、JSONL 输入与键盘控制入口可用；本批实验是程序生成的目标与状态守卫，不是人类 VR 演示。观测来自仿真理想状态。','- 驱动轮是接触驱动；小脚轮采用低摩擦球接触近似。研究夹爪替代原模型固定手；关节驱动限矩 100 N·m，车轮 20 N·m，指爪 35 N，均非经实机辨识的参数。','- 碰撞几何包含底盘、指爪与手臂代理，可与环境碰撞；尚未做全身网格自碰撞验证。路线是根据已知障碍包围盒构造的几何走廊，不是视觉建图或通用规划器。','- 开发测试的 85 cm 目标在抬升阶段未通过可达性守卫；当前证明范围是 55–75 cm，不能宣称任意高度。失败记录保留在 `outputs/dev_high*`。','- 滑移反馈、速度调节、阶段守卫属于系统控制改进，未声称提出新控制理论或完整复现 Mobile ALOHA / HoMeR 学习系统。','- 小样本仿真只能支持阶段性进展，国家级认定仍由学院评审与名额决定。']
(out/'V2验证报告.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps(aggregate,ensure_ascii=False,indent=2));print(paired)
