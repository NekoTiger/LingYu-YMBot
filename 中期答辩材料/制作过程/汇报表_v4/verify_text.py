# -*- coding: utf-8 -*-
import sys, re
sys.stdout.reconfigure(encoding="utf-8")
import win32com.client as win32
from docx import Document

DOCX = r"D:\UserData\Desktop\Coding\Innovation and Entrepreneurship\2026大创\中期答辩材料\制作过程\汇报表_v4\candidate_v4.docx"
DOC = r"D:\UserData\Desktop\Coding\Innovation and Entrepreneurship\2026大创\中期答辩材料\制作过程\汇报表_v4\candidate_v4.doc"

def norm(s):
    return re.sub(r"\s+", "", s)

doc = Document(DOCX)
parts = [p.text for p in doc.paragraphs]
for t in doc.tables:
    for row in t.rows:
        for c in row.cells:
            parts.append(c.text)
docx_text = norm("".join(parts))

app = win32.DispatchEx("Word.Application")
app.Visible = False
app.DisplayAlerts = 0
try:
    d = app.Documents.Open(DOC, ReadOnly=True)
    doc_text = norm(d.Content.Text)
    print("docx len", len(docx_text), "doc len", len(doc_text))
    print("equal:", docx_text == doc_text)
    if docx_text != doc_text:
        import difflib
        sm = difflib.SequenceMatcher(None, docx_text, doc_text)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag != "equal":
                print(tag, repr(docx_text[i1:i2])[:120], "->", repr(doc_text[j1:j2])[:120])
    print("doc pages:", d.ComputeStatistics(2))
    d.Close(False)
finally:
    app.Quit()
