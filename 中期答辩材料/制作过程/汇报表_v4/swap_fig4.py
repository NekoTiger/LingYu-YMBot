# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding="utf-8")
from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn

SRC = r"D:\UserData\Desktop\Coding\Innovation and Entrepreneurship\2026大创\中期答辩材料\提交版\灵驭_中期汇报表_修订版_20261120.docx"
DST = r"D:\UserData\Desktop\Coding\Innovation and Entrepreneurship\2026大创\中期答辩材料\制作过程\汇报表_v4\candidate_v5.docx"
NEW_FIG = r"C:\Users\10141\.codex\visualizations\2026\11\20\01a1f773-1c45-7cf0-b932-52a3aba7ecf0\paper_formal_page.png"

doc = Document(SRC)
cell = doc.tables[1].cell(5, 0)
paras = cell.paragraphs
cap_idx = None
for i, p in enumerate(paras):
    if p.text.startswith("图4"):
        cap_idx = i
        break
assert cap_idx is not None
pic_idx = cap_idx - 1
pic_par = paras[pic_idx]
cap_par = paras[cap_idx]
assert len(pic_par._p.findall('.//' + qn('w:drawing'))) == 1
cap_par._p.getparent().remove(cap_par._p)
pic_par._p.getparent().remove(pic_par._p)

p_img = cell.add_paragraph()
p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
pf = p_img.paragraph_format
pf.first_line_indent = Pt(0)
pf.space_before = Pt(6)
pf.space_after = Pt(0)
pf.keep_with_next = True
run = p_img.add_run()
run.add_picture(NEW_FIG, width=Cm(12.5))

p_cap = cell.add_paragraph()
p_cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
cf = p_cap.paragraph_format
cf.first_line_indent = Pt(0)
cf.space_before = Pt(0)
cf.space_after = Pt(8)
cr = p_cap.add_run("图4 投稿论文首页（英文标题与摘要）")
cr.font.size = Pt(10.5)
cr.font.name = "Times New Roman"
cr._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')

doc.save(DST)
print("saved", DST)
d2 = Document(DST)
print("inline shapes:", len(d2.inline_shapes))
