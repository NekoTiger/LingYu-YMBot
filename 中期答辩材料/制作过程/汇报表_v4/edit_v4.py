# -*- coding: utf-8 -*-
import sys, copy
sys.stdout.reconfigure(encoding="utf-8")
from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

SRC = r"D:\UserData\Desktop\Coding\Innovation and Entrepreneurship\2026大创\中期答辩材料\提交版\灵驭_中期汇报表_修订版_20261120.docx"
DST = r"D:\UserData\Desktop\Coding\Innovation and Entrepreneurship\2026大创\中期答辩材料\制作过程\汇报表_v4\candidate_v4.docx"
ROOT = r"D:\UserData\Desktop\Coding\Innovation and Entrepreneurship\2026大创"
VZ = r"C:\Users\10141\.codex\visualizations\2026\11\20\01a1f773-1c45-7cf0-b932-52a3aba7ecf0"

FIG_SIM = ROOT + r"\仿真成果_20261117_双层风险\搬运.png"
FIG_5G = ROOT + r"\仿真成果_20261117_双层风险\五组任务对照.png"
FIG_HUMAN = ROOT + r"\中期答辩材料\实验结果_20261120\01_正式实验主结果.png"
FIG_PAPER = VZ + r"\paper_page1_hi.png"

doc = Document(SRC)
t = doc.tables[1]

missing_report = []

def apply_bold(par, phrases):
    runs = par.runs
    if not runs:
        return
    full = "".join(r.text for r in runs)
    ranges = []
    for ph in phrases:
        pos, n = 0, 0
        while True:
            i = full.find(ph, pos)
            if i == -1:
                break
            ranges.append((i, i + len(ph)))
            n += 1
            pos = i + len(ph)
        if n == 0:
            missing_report.append(ph)
    if not ranges:
        return
    ranges.sort()
    merged = []
    for s, e in ranges:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    def is_bold(pos):
        return any(s <= pos < e for s, e in merged)

    new_elems = []
    pos = 0
    for r in runs:
        text = r.text
        if not text:
            new_elems.append(copy.deepcopy(r._r))
            continue
        k = 0
        while k < len(text):
            g = pos + k
            bold = is_bold(g)
            j = k
            while j < len(text) and is_bold(pos + j) == bold:
                j += 1
            seg = text[k:j]
            nr = copy.deepcopy(r._r)
            ts = nr.findall(qn('w:t'))
            if ts:
                ts[0].text = seg
                ts[0].set(qn('xml:space'), 'preserve')
                for extra in ts[1:]:
                    nr.remove(extra)
            else:
                t_el = OxmlElement('w:t')
                t_el.text = seg
                t_el.set(qn('xml:space'), 'preserve')
                nr.append(t_el)
            if bold:
                rpr = nr.find(qn('w:rPr'))
                if rpr is None:
                    rpr = OxmlElement('w:rPr')
                    nr.insert(0, rpr)
                if rpr.find(qn('w:b')) is None:
                    rpr.insert(0, OxmlElement('w:b'))
            new_elems.append(nr)
            k = j
        pos += len(text)
    idx = list(par._p).index(runs[0]._r)
    for r in runs:
        par._p.remove(r._r)
    for nr in new_elems:
        par._p.insert(idx, nr)
        idx += 1

def make_run(rpr_src, text, bold=False):
    nr = OxmlElement('w:r')
    if rpr_src is not None:
        nr.append(copy.deepcopy(rpr_src))
    rpr = nr.find(qn('w:rPr'))
    if bold:
        if rpr is None:
            rpr = OxmlElement('w:rPr')
            nr.insert(0, rpr)
        if rpr.find(qn('w:b')) is None:
            rpr.insert(0, OxmlElement('w:b'))
    t_el = OxmlElement('w:t')
    t_el.text = text
    t_el.set(qn('xml:space'), 'preserve')
    nr.append(t_el)
    return nr

def strip_runs(p_el):
    for r in p_el.findall(qn('w:r')):
        p_el.remove(r)

# ---------- Section II: bold key phrases ----------
cell2 = t.cell(5, 0)
p2 = cell2.paragraphs
assert len(p2) == 9, len(p2)
apply_bold(p2[0], ["降幅约91%", "每10 ms计算一次底盘与双臂如何分担前后运动", "5位团队成员完成了40个正式试次"])
apply_bold(p2[1], ["每次试次的输入、状态与判定均自动留存"])
apply_bold(p2[2], ["两组均8/8成功", "直接目标跟踪均0/8完成，完整控制均保持8/8成功", "平均缩短约43.9%"])
apply_bold(p2[3], ["底盘速度上限0.16 m/s、手臂补偿范围±45 mm", "求解耗时中位数为0.258 ms、P95为0.485 ms"])
apply_bold(p2[4], ["前四组均8/8成功，统一降速组4/8成功", "双层联合与固定分配的平均耗时分别为84.47 s和84.77 s"])
apply_bold(p2[5], ["实验协议与相关源码在采集前以哈希锁定"])
apply_bold(p2[6], ["固定分配成功13/20（65%），双层联合14/20（70%）", "平均限时耗时分别为145.4 s和150.9 s", "正常场景两方法均10/10成功，低摩擦复合场景分别3/10和4/10成功"])
apply_bold(p2[8], ["《LINGYU: Risk-Grounded Shared Teleoperation and Action Mediation for Compound Bimanual Mobile Manipulation Demonstrations》", "已投稿至ACL 2026并处于审稿阶段"])

# cross-reference to figures in intro
p2[0].runs[-1].text = p2[0].runs[-1].text + "仿真场景、五组任务对照、真人实验结果与论文首页见图1至图4。"

# ---------- Section II: append figures ----------
figs = [
    (FIG_SIM, 13.8, "图1 双臂托盘搬运仿真场景（右侧面板实时显示双层接触风险与指令分配）"),
    (FIG_5G, 13.8, "图2 合成输入五组物理任务对照（柱为均值、点为单次试验、红叉为失败）"),
    (FIG_HUMAN, 13.8, "图3 真人正式实验主结果（5位参与者，首次成功率与平均限时耗时）"),
    (FIG_PAPER, 12.5, "图4 已投稿论文首页"),
]
for path, width_cm, caption in figs:
    p_img = cell2.add_paragraph()
    p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pf = p_img.paragraph_format
    pf.first_line_indent = Pt(0)
    pf.space_before = Pt(6)
    pf.space_after = Pt(0)
    pf.keep_with_next = True
    run = p_img.add_run()
    run.add_picture(path, width=Cm(width_cm))
    p_cap = cell2.add_paragraph()
    p_cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cf = p_cap.paragraph_format
    cf.first_line_indent = Pt(0)
    cf.space_before = Pt(0)
    cf.space_after = Pt(8)
    cr = p_cap.add_run(caption)
    cr.font.size = Pt(10.5)
    cr.font.name = "Times New Roman"
    cr._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')

# ---------- Section III: bold ----------
cell3 = t.cell(6, 0)
p3 = cell3.paragraphs
apply_bold(p3[1], ["在100 Hz控制周期内", "中位求解耗时0.258 ms"])
apply_bold(p3[2], ["补偿范围（±45 mm）"])
apply_bold(p3[3], ["由5位VR新手完成配对试次", "哈希锁定协议与源码"])

# ---------- Section IV: bold ----------
cell4 = t.cell(8, 0)
p4 = cell4.paragraphs
apply_bold(p4[1], ["把中期成果整理成论文并投稿"])
apply_bold(p4[3], ["13次首次失败中有10次被判为物件离开托盘"])

# ---------- Section VI: funding + renumber + cleanup ----------
cell6 = t.cell(18, 0)
p6 = cell6.paragraphs
assert len(p6) == 8, len(p6)

heading_src = p6[0]._p
body_src = p6[1]._p
heading_rpr = p6[0].runs[0]._r.rPr
body_rpr = p6[1].runs[0]._r.rPr

# new heading paragraph
h = copy.deepcopy(heading_src)
strip_runs(h)
h.append(make_run(heading_rpr, "（一）经费使用情况", bold=True))
p6[0]._p.addprevious(h)

# new body paragraph
body = copy.deepcopy(body_src)
strip_runs(body)
funding = "项目立项批复总经费10,000元。截至2026年11月20日，中期阶段已支出约950元，其中实验耗材费约800元，用于高带宽USB串流数据线、3D打印托盘把手与固定治具、线材与防滑固定件；资料费约150元，用于参考书与打印装订。仿真与真人实验主要依托学院工作站、Meta Quest 3与开源软件完成，暂无软件、计算与差旅支出。结余约9,050元，将按预算用于后续真机联调耗材、外部受试者实验、论文版面费及软件著作权登记等。"
bold_phrases = ["总经费10,000元", "已支出约950元", "实验耗材费约800元", "资料费约150元", "结余约9,050元"]
spans = []
for ph in bold_phrases:
    pos = 0
    while True:
        i = funding.find(ph, pos)
        if i == -1:
            break
        spans.append((i, i + len(ph)))
        pos = i + len(ph)
spans.sort()
seg_start = 0
for s, e in spans:
    if s > seg_start:
        body.append(make_run(body_rpr, funding[seg_start:s], bold=False))
    body.append(make_run(body_rpr, funding[s:e], bold=True))
    seg_start = e
if seg_start < len(funding):
    body.append(make_run(body_rpr, funding[seg_start:], bold=False))
h.addnext(body)

# renumber old subsections
p6 = cell6.paragraphs  # refresh
old = p6[2]  # （一）中期结果整理与答辩准备
old.runs[0].text = old.runs[0].text.replace("（一）", "（二）", 1)
old = p6[4]  # （二）下一轮实验与方法改进
old.runs[0].text = old.runs[0].text.replace("（二）", "（三）", 1)

# fix bolded whole paragraph of （三）后续阶段安排 and drop stale duplicate
p6 = cell6.paragraphs  # refresh
par_plan = p6[8]  # （三）后续阶段安排 + content in one bold run
run0 = par_plan.runs[0]
content_text = run0.text.split("\n", 1)[1]
# build content paragraph from copy
newc = copy.deepcopy(par_plan._p)
strip_runs(newc)
rpr_base = copy.deepcopy(run0._r.rPr)
if rpr_base.find(qn('w:b')) is not None:
    rpr_base.remove(rpr_base.find(qn('w:b')))
newc.append(make_run(rpr_base, content_text, bold=False))
par_plan._p.addnext(newc)
# fix heading run: keep first w:t as new heading, drop br and second w:t
tss = run0._r.findall(qn('w:t'))
tss[0].text = "（四）后续阶段安排"
for br in run0._r.findall(qn('w:br')):
    run0._r.remove(br)
for extra in tss[1:]:
    run0._r.remove(extra)
# remove stale duplicate paragraph (originally last)
p6 = cell6.paragraphs
stale = p6[-1]
assert stale.text.startswith("2027年2—3月，扩展操作者"), stale.text[:30]
stale._p.getparent().remove(stale._p)

doc.save(DST)
print("missing bold phrases:", missing_report if missing_report else "NONE")
print("saved", DST)

# quick verification of final Section VI paragraphs
doc2 = Document(DST)
c6 = doc2.tables[1].cell(18, 0)
for i, pp in enumerate(c6.paragraphs):
    print(f"VI[{i}]", pp.text[:60])
c2 = doc2.tables[1].cell(5, 0)
print("SectionII paras:", len(c2.paragraphs))
print("last paras:", [p.text[:40] for p in c2.paragraphs[-8:]])
