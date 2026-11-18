"""Keep unsuccessful exploratory probes visible in the delivery."""
import hashlib
import json
from pathlib import Path
import shutil
import numpy as np

def report():
    here=Path(__file__).parent;out=here.parents[1]/'仿真成果_20261117_双层风险'
    text=['# 补充探索：连续换向与偏心方向','',
          '这两组在观察常规任务结果后追加，控制器参数未调整。它们是探索性物理测试，不并入 40 次完整任务，也不标作真人实验。每组五种方法、两个种子，共 20 次短测试。','']
    checks={}
    for stem,title in [('risk_reversal_20261117','A：前偏心 35 mm，0.6 s 半周期换向'),
                       ('risk_reversal_adverse_20261117','B：后偏心 35 mm，1.8 s 半周期换向')]:
        root=here/'outputs'/stem
        rows=json.loads((root/'results.json').read_text(encoding='utf-8'));protocol=json.loads((root/'protocol.json').read_text(encoding='utf-8'))
        pair_hash={};loss_times=[]
        for r in rows:
            session=Path(r['session'])
            packets=[json.loads(line)['packet'] for line in (session/'raw_webxr.jsonl').read_text(encoding='utf-8').splitlines()]
            digest=hashlib.sha256(json.dumps(packets,sort_keys=True).encode()).hexdigest()
            pair_hash.setdefault(r['seed'],set()).add(digest)
            risks=[json.loads(line) for line in (session/'risk_control.jsonl').read_text(encoding='utf-8').splitlines()]
            first=next((x['sim_time'] for x in risks if x['edge_margin_m']<-.066 and x['parcel_support_n']<.1),None)
            if first is not None:loss_times.append(first)
        assert all(len(v)==1 for v in pair_hash.values()),'Input packets differ across paired policies'
        checks[stem]={'identical_input_by_seed':{str(k):next(iter(v)) for k,v in pair_hash.items()},
            'complete_trials':len(rows),'loss_before_pulse_count':sum(t<10 for t in loss_times),'first_loss_times_s':loss_times}
        text+=['## '+title,'','| 方法 | 末时仍承载 | 最大滑移/mm | 最大倾角/° | 物体运动范围/mm | 指令误差 RMSE/(m/s) |','|---|---:|---:|---:|---:|---:|']
        for p,name in [('fixed','固定分配'),('grip_only','仅抓持'),('payload_only','仅承载'),('dual','双层联合'),('slow','统一降速')]:
            a=[r for r in rows if r['policy']==p]
            text.append(f"| {name} | {sum(r['retained_at_end'] for r in a)}/{len(a)} | "+' | '.join(f'{np.mean([r[k] for r in a]):.3f}' for k in ['max_slip_mm','max_tilt_deg','object_excursion_mm','command_rmse_m_s'])+' |')
        text+=['','表中极值和范围均统计 10～24 s，随后对两个种子取均值。“末时仍承载”只是物理状态，不等于完成搬运放置任务。', '']
        if loss_times:text+=[f'该组 {sum(t<10 for t in loss_times)}/10 次在换向开始前已脱离托盘（首次完全越出约 {min(loss_times):.2f}～{max(loss_times):.2f} s）。因此后续换向数据不能证明承载阶段的算法优势；这个结果暴露的是抬升阶段未覆盖的失稳。','']
        else:text+=['该组没有持续激发明显的承载滑移，两种风险方法与固定规则差别很小。0.6 s 换向快于指令限幅的充分跟踪时间，物体出现净位移，因此它也不能解释为位置保持测试。此结果不支持“联合风险方法已明显更优”。','']
        target=out/'补充试验'/stem;target.mkdir(parents=True,exist_ok=True)
        for name in ('protocol.json','results.json','generator_snapshot.py'):shutil.copy2(root/name,target/name)
    text+=['## 对后续实现的直接要求','','优先把抬升阶段的托盘姿态与垂向速度纳入风险处理，再设计能够持续激活两类风险、同时保留明确操作目标的试验。当前前后分配原型的实现与接口已经完成，但它还没有解决这些边界。',
           '','各方法相同种子的输入包已逐包哈希核对一致；记录见 supplementary_checks.json。两轮参数与生成器均单独保存，可复核，没有删除失败。']
    (out/'补充探索与失败边界.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
    (out/'supplementary_checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':report()
