# -*- coding: utf-8 -*-
import sys, os
sys.stdout.reconfigure(encoding="utf-8")
import win32com.client as win32

DOCX = r"D:\UserData\Desktop\Coding\Innovation and Entrepreneurship\2026大创\中期答辩材料\制作过程\汇报表_v4\candidate_v4.docx"
PDF = r"D:\UserData\Desktop\Coding\Innovation and Entrepreneurship\2026大创\中期答辩材料\制作过程\汇报表_v4\candidate_v4.pdf"
DOC = r"D:\UserData\Desktop\Coding\Innovation and Entrepreneurship\2026大创\中期答辩材料\制作过程\汇报表_v4\candidate_v4.doc"

app = win32.DispatchEx("Word.Application")
app.Visible = False
app.DisplayAlerts = 0
try:
    d = app.Documents.Open(DOCX, ReadOnly=True)
    d.Repaginate()
    app.ScreenRefresh()
    print("pages:", d.ComputeStatistics(2))
    d.ExportAsFixedFormat(PDF, 17)
    d.SaveAs2(DOC, 0)
    d.Close(False)
finally:
    app.Quit()
print("done")
