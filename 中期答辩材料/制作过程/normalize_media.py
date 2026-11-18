from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from lxml import etree as E
here=Path(__file__).resolve().parent
with ZipFile(here/'candidate_native.pptx') as z: parts={n:z.read(n) for n in z.namelist()}
root=E.fromstring(parts['ppt/slides/slide2.xml'])
rid='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
count=0
for e in root.iter():
    if e.tag.endswith('}hlinkClick') and e.get('action')=='ppaction://media' and e.get(rid)=='' :
        del e.attrib[rid]
        count+=1
assert count==1,count
parts['ppt/slides/slide2.xml']=E.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True)
with ZipFile(here/'candidate_ready.pptx','w',ZIP_DEFLATED) as z:
    for name,data in parts.items(): z.writestr(name,data)
print('Normalized empty optional relationship on native media action; embedded media retained.')
