import copy
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from lxml import etree as E

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
SRC = HERE / 'template.docx'
OUT = BASE / '提交版' / '灵驭_中期汇报表.docx'
data = json.loads((HERE / 'report_content.json').read_text(encoding='utf-8'))
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
def w(x): return '{'+NS['w']+'}'+x
with ZipFile(SRC) as z:
    items = {name: z.read(name) for name in z.namelist()}
root = E.fromstring(items['word/document.xml'])
body = root.find('w:body', NS)
tables = body.findall('w:tbl', NS)
def rows(t): return t.findall('w:tr', NS)
def cells(r): return r.findall('w:tc', NS)
def prop(parent, name, **attrs):
    el = parent.find('w:'+name, NS)
    if el is None: el = E.SubElement(parent,w(name))
    for k,v in attrs.items(): el.set(w(k), str(v))
    return el
def paragraph(text, *, bold=False, size=24, align='left', after=65, indent=True, keep=False):
    p = E.Element(w('p')); pp = E.SubElement(p,w('pPr'))
    prop(pp,'jc',val=align); prop(pp,'spacing',before=0,after=after,line=360,lineRule='auto')
    prop(pp,'ind',firstLine=480 if indent else 0)
    prop(pp,'widowControl',val=1)
    if keep: prop(pp,'keepNext')
    r=E.SubElement(p,w('r')); rp=E.SubElement(r,w('rPr'))
    prop(rp,'rFonts',ascii='Times New Roman',hAnsi='Times New Roman',eastAsia='宋体')
    prop(rp,'sz',val=size); prop(rp,'szCs',val=size); prop(rp,'color',val='000000')
    if bold: prop(rp,'b')
    if '【待确认' in text: prop(rp,'highlight',val='yellow')
    t=E.SubElement(r,w('t')); t.text=text; t.set('{http://www.w3.org/XML/1998/namespace}space','preserve')
    return p
def fill(cell, texts, *, cover=False, size=24, heading=None):
    for p in list(cell):
        if p.tag != w('tcPr'): cell.remove(p)
    cp=prop(cell,'tcPr'); prop(cp,'vAlign',val='center' if cover else 'top')
    if not cover:
        mar=prop(cp,'tcMar')
        for edge in ['top','bottom','left','right']: prop(mar,edge,w=90,type='dxa')
    if heading is not None: cell.append(paragraph(heading,bold=True,indent=False,keep=True))
    for s in texts:
        h=s.startswith('（')
        cell.append(paragraph(s,bold=h,size=size,align='center' if cover else 'left',after=0 if cover else 65,indent=not cover and not h,keep=h))

# Preserve the official cover and both tables, replacing their editable slots.
bp=body.findall('w:p',NS)
for p in bp[7:17]:
    if not ''.join(p.itertext()).strip():
        pp=prop(p,'pPr'); prop(pp,'spacing',before=0,after=0,line=140,lineRule='exact')
for p in bp:
    text=''.join(p.itertext())
    if '项目编号' in text:
        new=paragraph('项目编号：'+data['project_number'],size=24,indent=False)
        p.getparent().replace(p,new)
    elif '填表日期' in text:
        new=paragraph('填表日期：'+data.get('report_date','2026年11月16日'),size=28,align='center',indent=False)
        p.getparent().replace(p,new)

cover=[
    '“灵驭”——基于VR遥操作的人形轮式机器人灵巧作业与协调运动控制',
    '蔡晓虎','计算机科学与技术学院','计算机科学与技术','17316311998',
    '10245102487@stu.ecnu.edu.cn','王长波 教授；李洋 副教授',data['start_date']]
for i,s in enumerate(cover): fill(cells(rows(tables[0])[i])[-1],[s],cover=True,size=21 if i in [0,5,6,7] else 24)

r=rows(tables[1])
fill(cells(r[0])[-1],['教师科研课题的子项目'],cover=True)
fill(cells(r[1])[-1],[data['affiliation']],cover=True,size=22)
fill(cells(r[3])[0],data['goals'])
fill(cells(r[5])[0],data['progress'])
fill(cells(r[6])[0],data['innovation'],heading='三、项目创新点（项目实施过程中使用的新方法或者项目特色，600字以内）')
fill(cells(r[8])[0],data['reflections'],heading='四、研究心得\n（项目实施过程中的得失成败，如在创新思维和成长方面有何收获，有何值得借鉴的成功经验和失败教训等，2000字以内）')
people=[
    ('蔡晓虎','10245102487','统筹方案、系统联调与实验组织'),
    ('张潇瀚','10245102417','VR映射、交互界面与设备联调'),
    ('颜硕','10245102482','协调控制、仿真与消融验证'),
    ('宋易乐','10255102520','软硬件集成、测试与数据采集'),
    ('邓智文','10255102464','文献整理、数据分析与研究报告')]
for i,(name,sid,task) in enumerate(people,12):
    for c,value in zip(cells(r[i]),[name,sid,'计算机科学与技术',task]):
        fill(c,[value],cover=True,size=20)
plan=[s.replace('{funding}',data['funding']) for s in data['plan']]
if not data['funding']:
    plan=[s.replace('（二）答辩前','（一）答辩前').replace('（三）后续','（二）后续') for s in plan[2:]]
fill(cells(r[18])[0],plan)

# Blank template paragraphs supplied writing space; filled text now determines row height.
for index in [3,5,6,8,18]:
    pr=r[index].find('w:trPr',NS)
    if pr is not None:
        for h in list(pr):
            if h.tag in [w('trHeight'),w('cantSplit')]: pr.remove(h)
for index in [7,9]:
    for c in cells(r[index]): fill(c,[''],cover=True,size=2)
    pr=prop(r[index],'trPr'); prop(pr,'trHeight',val=12,hRule='atLeast')
for index in [2,4,10,11,17]:
    for p in r[index].findall('.//w:p',NS): prop(prop(p,'pPr'),'keepNext')

items['word/document.xml']=E.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True)
OUT.parent.mkdir(exist_ok=True)
with ZipFile(OUT,'w',ZIP_DEFLATED) as z:
    for name,value in items.items(): z.writestr(name,value)
limits={'progress':2000,'innovation':600,'reflections':2000,'plan':2000}
counts={k:sum(len(s) for s in data[k]) for k in limits}
assert all(counts[k]<=v for k,v in limits.items()), counts
with ZipFile(SRC) as a, ZipFile(OUT) as b:
    changed=[n for n in a.namelist() if a.read(n)!=b.read(n)]
assert changed==['word/document.xml'],changed
(HERE/'report_validation.json').write_text(json.dumps({'counts':counts,'changed_parts':changed,'source_sha256':hashlib.sha256(SRC.read_bytes()).hexdigest()},ensure_ascii=False,indent=2),encoding='utf-8')
(HERE/'artifact.md').write_text('''# 中期汇报表模板契约
保留学校附件2转换所得 template.docx，原始 .doc 不修改。
来源为同目录 template.pdf 及 template-render 的5页目检图。A4纵向，单节，页边距上下2.54 cm、左右3.175 cm。
保留封面学校标题、两张表的列网格、合并关系、边框、六个栏目顺序和行政信息字段。黑色宋体正文12 pt，1.5倍行距；封面数据10.5–12 pt，成员行10 pt，以适应窄单元格。
编辑定位：document.xml/body/tbl[1]行1–8末格为封面值；tbl[2]行1–2末格为来源和依托单位，行4/6为目标和进展，行7/9为创新和心得，行13–17为成员，行19为经费及计划。
空白写作行改为正文自然流动，允许报告页数随内容增长。封面和正文标题保留学校含义。未知行政信息黄色标记待确认；不填写未经确认的经费数值。
除 document.xml 外所有包成员逐字节保留，生成时检查源SHA256和修改清单。由于本机无LibreOffice，已运行 render_docx.py 并定位为缺少soffice.exe；改用已安装Microsoft Word原生PDF导出，再用捆绑Poppler生成逐页PNG并目检。
''',encoding='utf-8')
print(OUT)
print(counts)
