# -*- coding: utf-8 -*-
import sys, os
sys.stdout.reconfigure(encoding="utf-8")
from docx import Document
from docx.shared import Cm
from docx.oxml.ns import qn

SRC = r"D:\UserData\Desktop\Coding\Innovation and Entrepreneurship\2026大创\中期答辩材料\提交版\灵驭_中期汇报表_修订版_20261120.docx"
DST = r"D:\UserData\Desktop\Coding\Innovation and Entrepreneurship\2026大创\中期答辩材料\制作过程\汇报表_v4\candidate_v7.docx"
VZ = r"C:\Users\10141\.codex\visualizations\2026\11\20\01a1f773-1c45-7cf0-b932-52a3aba7ecf0\uniform"

doc = Document(SRC)
cell = doc.tables[1].cell(5, 0)
pic_pars = []
for par in cell.paragraphs:
    if par._p.findall('.//' + qn('w:drawing')):
        pic_pars.append(par)
print("picture paragraphs:", len(pic_pars))
assert len(pic_pars) == 6

for i, par in enumerate(pic_pars):
    for r in list(par.runs):
        r._r.getparent().remove(r._r)
    img = os.path.join(VZ, f"fig{i+1}.png")
    run = par.add_run()
    run.add_picture(img, width=Cm(14.0))

doc.save(DST)
d2 = Document(DST)
print("shapes:", len(d2.inline_shapes))
