# -*- coding: utf-8 -*-
import sys, re
sys.stdout.reconfigure(encoding="utf-8")
import win32com.client as win32
from docx import Document
from docx.text.paragraph import Paragraph
from docx.table import Table, _Cell
from docx.oxml.ns import qn

DOCX = r"D:\UserData\Desktop\Coding\Innovation and Entrepreneurship\2026大创\中期答辩材料\制作过程\汇报表_v4\candidate_v6.docx"
DOC = r"D:\UserData\Desktop\Coding\Innovation and Entrepreneurship\2026大创\中期答辩材料\制作过程\汇报表_v4\candidate_v6.doc"

def norm(s):
    return re.sub(r"\s+", "", s)

def iter_text(doc):
    body = doc.element.body
    out = []
    for child in body.iterchildren():
        tag = child.tag.split('}')[1]
        if tag == 'p':
            out.append(Paragraph(child, doc).text)
        elif tag == 'tbl':
            t = Table(child, doc)
            for tr in t._tbl.findall(qn('w:tr')):
                for tc in tr.findall(qn('w:tc')):
                    out.append(_Cell(tc, t).text)
    return "".join(out)

doc = Document(DOCX)
docx_text = norm(iter_text(doc))
app = win32.DispatchEx("Word.Application")
app.Visible = False
app.DisplayAlerts = 0
try:
    d = app.Documents.Open(DOC, ReadOnly=True)
    raw = d.Content.Text.replace("\x07", "").replace("\x01", "")
    doc_text = norm(raw)
    print("equal:", docx_text == doc_text, "| docx", len(docx_text), "doc", len(doc_text))
    print("doc pages:", d.ComputeStatistics(2))
    d.Close(False)
finally:
    app.Quit()
