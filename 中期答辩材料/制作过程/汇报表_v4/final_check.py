# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding="utf-8")
from docx import Document
p = r"D:\UserData\Desktop\Coding\Innovation and Entrepreneurship\2026大创\中期答辩材料\提交版\灵驭_中期汇报表_修订版_20261120.docx"
doc = Document(p)
print("inline shapes:", len(doc.inline_shapes))
t = doc.tables[1]
c2 = t.cell(5,0)
caps = [pp.text for pp in c2.paragraphs if pp.text.startswith("图")]
print("captions:", caps)
# check bold phrases present
targets = ["降幅约91%","每10 ms计算一次底盘与双臂如何分担前后运动","固定分配成功13/20（65%）","双层联合14/20（70%）","已投稿至ACL 2026并处于审稿阶段","总经费10,000元","已支出约950元","结余约9,050元"]
alltext = "".join(pp.text for pp in c2.paragraphs) + t.cell(18,0).text + t.cell(6,0).text + t.cell(8,0).text
for tg in targets:
    print("contains", tg, ":", tg in alltext)
