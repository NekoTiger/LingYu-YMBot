# -*- coding: utf-8 -*-
import sys, re
sys.stdout.reconfigure(encoding="utf-8")
import win32com.client as win32
from docx import Document
from docx.text.paragraph import Paragraph
from docx.table import Table

DOCX = r"D:\UserData\Desktop\Coding\Innovation and Entrepreneurship\2026大创\中期答辩材料\制作过程\汇报表_v4\candidate_v4.docx"
DOC = r"D:\UserData\Desktop\Coding\Innovation and Entrepreneurship\2026大创\中期答辩材料\制作过程\汇报表_v4\candidate_v4.doc"

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
            for row in t.rows:
                for c in row.cells:
                    # each merged cell appears once via tc iteration
                    out.append(c.text)
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
    print("docx len", len(docx_text), "doc len", len(doc_text))
    print("equal:", docx_text == doc_text)
    if docx_text != doc_text:
        import difflib
        sm = difflib.SequenceMatcher(None, docx_text, doc_text)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag != "equal":
                print(tag, repr(docx_text[i1:i2])[:160], "->", repr(doc_text[j1:j2])[:160])
    d.Close(False)
finally:
    app.Quit()
