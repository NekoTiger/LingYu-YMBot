# -*- coding: utf-8 -*-
import sys, copy
sys.stdout.reconfigure(encoding="utf-8")
from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

SRC = r"D:\UserData\Desktop\Coding\Innovation and Entrepreneurship\2026大创\中期答辩材料\提交版\灵驭_中期汇报表_修订版_20261120.docx"
DST = r"D:\UserData\Desktop\Coding\Innovation and Entrepreneurship\2026大创\中期答辩材料\制作过程\汇报表_v4\candidate_v6.docx"
VZ = r"C:\Users\10141\.codex\visualizations\2026\11\20\01a1f773-1c45-7cf0-b932-52a3aba7ecf0"
FIG_ROBOT = VZ + r"\ppt_road\image1.png"
FIG_CALIB = VZ + r"\ppt_road\image2.png"

doc = Document(SRC)
t = doc.tables[1]
cell2 = t.cell(5, 0)
paras = cell2.paragraphs

# 1) find first figure caption paragraph index
first_cap = None
for i, p in enumerate(paras):
    if p.text.startswith("图"):
        first_cap = i
        break
assert first_cap is not None
anchor = paras[first_cap - 1]._p  # picture paragraph of current 图1

def add_figure_pair(cell, path, width_cm, caption):
    p_img = cell.add_paragraph()
    p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pf = p_img.paragraph_format
    pf.first_line_indent = Pt(0)
    pf.space_before = Pt(6)
    pf.space_after = Pt(0)
    pf.keep_with_next = True
    p_img.add_run().add_picture(path, width=Cm(width_cm))
    p_cap = cell.add_paragraph()
    p_cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cf = p_cap.paragraph_format
    cf.first_line_indent = Pt(0)
    cf.space_before = Pt(0)
    cf.space_after = Pt(8)
    cr = p_cap.add_run(caption)
    cr.font.size = Pt(10.5)
    cr.font.name = "Times New Roman"
    cr._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
    return p_img, p_cap

p1, c1 = add_figure_pair(cell2, FIG_ROBOT, 8.5, "图1 双臂轮式人形机器人平台（YMBOT 模型渲染，托盘与散件）")
p2, c2 = add_figure_pair(cell2, FIG_CALIB, 13.8, "图2 双臂夹取标定阶段仿真界面")
anchor.addprevious(p1._p)
anchor.addprevious(p2._p)
anchor.addprevious(c1._p)
anchor.addprevious(c2._p)

# 2) renumber existing captions 图1->图3 ... 图4->图6 (descending)
paras = cell2.paragraphs
renames = [("图4", "图6"), ("图3", "图5"), ("图2", "图4"), ("图1", "图3")]
for old, new in renames:
    for p in paras:
        if p.text.startswith(old):
            # only caption paragraphs; skip those already renamed to higher numbers
            p.runs[0].text = new + p.runs[0].text[len(old):]
            break  # exactly one per number after renumbering

# 3) update intro cross-reference
intro = cell2.paragraphs[0]
for r in intro.runs:
    if "图1至图4" in r.text:
        r.text = r.text.replace("仿真场景、五组任务对照、真人实验结果与论文首页见图1至图4。",
                                "机器人平台、标定界面、仿真场景、五组任务对照、真人实验结果与论文首页见图1至图6。")
        break
else:
    print("WARN: intro cross-ref not found in a single run")

# 4) fix funding numbers
cell6 = t.cell(18, 0)
fund_par = None
for p in cell6.paragraphs:
    if "总经费" in p.text:
        fund_par = p
        break
assert fund_par is not None
new_text = "项目立项批复总经费1,500元。截至2026年11月20日，中期阶段已支出约950元，其中实验耗材费约800元，用于高带宽USB串流数据线、3D打印托盘把手与固定治具、线材与防滑固定件；资料费约150元，用于参考书与打印装订。仿真与真人实验主要依托学院工作站、Meta Quest 3与开源软件完成，暂无软件、计算与差旅支出。结余约550元，将按预算用于后续实验耗材、3D打印固定件与打印装订；论文版面费及软件著作权登记等支出将视结题进度另行申请。"
bold_phrases = ["总经费1,500元", "已支出约950元", "实验耗材费约800元", "资料费约150元", "结余约550元"]
rpr_base = copy.deepcopy(fund_par.runs[0]._r.rPr)
p_el = fund_par._p
idx = list(p_el).index(fund_par.runs[0]._r)
for r in fund_par.runs:
    p_el.remove(r._r)

def make_run(rpr, text, bold):
    nr = OxmlElement('w:r')
    nr.append(copy.deepcopy(rpr))
    rp = nr.find(qn('w:rPr'))
    if bold:
        if rp.find(qn('w:b')) is None:
            rp.insert(0, OxmlElement('w:b'))
    t_el = OxmlElement('w:t')
    t_el.text = text
    t_el.set(qn('xml:space'), 'preserve')
    nr.append(t_el)
    return nr

spans = []
for ph in bold_phrases:
    pos = 0
    while True:
        i = new_text.find(ph, pos)
        if i == -1:
            break
        spans.append((i, i + len(ph)))
        pos = i + len(ph)
spans.sort()
seg_start = 0
for s, e in spans:
    if s > seg_start:
        p_el.insert(idx, make_run(rpr_base, new_text[seg_start:s], False)); idx += 1
    p_el.insert(idx, make_run(rpr_base, new_text[s:e], True)); idx += 1
    seg_start = e
if seg_start < len(new_text):
    p_el.insert(idx, make_run(rpr_base, new_text[seg_start:], False)); idx += 1

doc.save(DST)
print("saved", DST)

d2 = Document(DST)
print("shapes:", len(d2.inline_shapes))
c = d2.tables[1].cell(5, 0)
print([p.text for p in c.paragraphs if p.text.startswith("图")])
c6 = d2.tables[1].cell(18, 0)
for p in c6.paragraphs:
    if "总经费" in p.text:
        print(p.text)
