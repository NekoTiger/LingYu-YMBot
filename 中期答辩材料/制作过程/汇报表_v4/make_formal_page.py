# -*- coding: utf-8 -*-
import sys, re
sys.stdout.reconfigure(encoding="utf-8")
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

VZ = r"C:\Users\10141\.codex\visualizations\2026\11\20\01a1f773-1c45-7cf0-b932-52a3aba7ecf0"
abstract = open(VZ + r"\paper_abstract.txt", encoding="utf-8").read().strip()

doc = Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
sec.top_margin = sec.bottom_margin = Cm(2.0)
sec.left_margin = sec.right_margin = Cm(2.2)

def style_run(run, size, bold=False, italic=False, ea="宋体", ascii_f="Times New Roman"):
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.name = ascii_f
    rpr = run._element.get_or_add_rPr()
    rf = rpr.find(qn('w:rFonts'))
    if rf is None:
        rf = OxmlElement('w:rFonts')
        rpr.append(rf)
    rf.set(qn('w:ascii'), ascii_f)
    rf.set(qn('w:hAnsi'), ascii_f)
    rf.set(qn('w:eastAsia'), ea)

def set_borders(tbl):
    tblPr = tbl._tbl.tblPr
    borders = OxmlElement('w:tblBorders')
    for edge in ('top','left','bottom','right'):
        el = OxmlElement('w:' + edge)
        el.set(qn('w:val'), 'single')
        el.set(qn('w:sz'), '8')
        el.set(qn('w:space'), '0')
        el.set(qn('w:color'), '000000')
        borders.append(el)
    tblPr.append(borders)

tbl = doc.add_table(rows=1, cols=1)
tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
set_borders(tbl)
cell = tbl.cell(0, 0)
cell.width = Cm(16.6)

def add_par(text, size, bold=False, italic=False, align=WD_ALIGN_PARAGRAPH.CENTER,
            space_before=0, space_after=0, line=None, ea="宋体"):
    p = cell.add_paragraph()
    p.alignment = align
    pf = p.paragraph_format
    pf.first_line_indent = Pt(0)
    pf.space_before = Pt(space_before)
    pf.space_after = Pt(space_after)
    if line:
        pf.line_spacing = line
    r = p.add_run(text)
    style_run(r, size, bold=bold, italic=italic, ea=ea)
    return p

add_par("", 6, space_after=2)
add_par("“灵驭”——基于VR遥操作的人形轮式机器人灵巧作业与协调运动控制", 10.5, bold=True, space_after=10)
add_par("LINGYU: Risk-Grounded Shared Teleoperation and", 16, bold=True, space_after=2)
add_par("Action Mediation for Compound Bimanual", 16, bold=True, space_after=2)
add_par("Mobile Manipulation Demonstrations", 16, bold=True, space_after=12)
add_par("Xiaohu Cai, Xiaohan Zhang, Shuo Yan, Yile Song, Zhiwen Deng, Yang Li*, Changbo Wang*", 11, space_after=4)
add_par("School of Computer Science and Technology, East China Normal University", 10, italic=True, space_after=1)
add_par("Robotics and Intelligent Systems Laboratory & Visual Perception + X (VPX) Group", 10, italic=True, space_after=14)
add_par("Abstract", 12, bold=True, align=WD_ALIGN_PARAGRAPH.LEFT, space_after=4)
add_par(abstract, 10.5, align=WD_ALIGN_PARAGRAPH.JUSTIFY, space_after=6, line=1.15)
add_par("", 6, space_after=4)

OUT = r"D:\UserData\Desktop\Coding\Innovation and Entrepreneurship\2026大创\中期答辩材料\制作过程\汇报表_v4\paper_formal_page.docx"
doc.save(OUT)
print("saved", OUT)
