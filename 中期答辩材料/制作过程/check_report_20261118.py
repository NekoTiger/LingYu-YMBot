from pathlib import Path
import hashlib
import json
from docx import Document
from pdf2image import convert_from_path
from pypdf import PdfReader

HERE=Path(__file__).resolve().parent
QA=HERE/'汇报表更新_20261118'
BIN=Path('C:/Program Files/WindowsApps/OpenAI.CodexPrimaryRuntime.v26-1116-1220-0_26.1116.1220.0_x64__3k8sg7r9htsxt/dependencies/native/poppler/Library/bin')
image_hash={}
page_text={}
for kind in ('docx','doc'):
    pdf=QA/f'report_{kind}.pdf'
    out=QA/f'{kind}_render'
    out.mkdir(exist_ok=True)
    pages=convert_from_path(str(pdf),dpi=144,poppler_path=str(BIN))
    image_hash[kind]=[]
    for i,image in enumerate(pages,1):
        image.save(out/f'page-{i}.png')
        image_hash[kind].append(hashlib.sha256(image.tobytes()).hexdigest())
    page_text[kind]=[p.extract_text() for p in PdfReader(pdf).pages]

source=Document(HERE/'归档_20261118修改前/灵驭_中期汇报表.docx')
target=Document(HERE.parent/'提交版/灵驭_中期汇报表.docx')
content=json.loads((HERE/'report_content.json').read_text(encoding='utf-8'))
for key,row,skip in [('goals',3,0),('progress',5,0),('innovation',6,1),('reflections',8,1),('plan',18,0)]:
    assert [p.text for p in target.tables[1].rows[row].cells[0].paragraphs][skip:]==content[key],key
def matrix(table):return [[c.text for c in row.cells] for row in table.rows]
assert len(target.tables)==len(source.tables)==2
assert matrix(target.tables[0])==matrix(source.tables[0]),'Administrative cover changed'
for index in [0,1,*range(10,18)]:
    assert [c.text for c in target.tables[1].rows[index].cells]==[c.text for c in source.tables[1].rows[index].cells],index
text='\n'.join(page_text['docx'])
for expected in ['2026年11月18日','双层接触风险','26项','40次','84.47','84.77','9.54','9.60','2.11','1.83','尚未证明','（一）答辩前','优先改进抬升阶段']:
    assert expected in text.replace(' ',''),expected
assert '11月16日完成负责人试跑' not in text
assert '【待确认' not in text
assert page_text['doc']==page_text['docx'],'DOC and DOCX page text differs'
results={'pages':len(image_hash['docx']),'doc_docx_page_text_identical':True,'doc_docx_pixels_identical':image_hash['doc']==image_hash['docx'],'administrative_and_team_fields_preserved':True,
         'required_numbers_and_date_found':True,'image_sha256':image_hash,
         'final_files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (HERE.parent/'提交版').glob('灵驭_中期汇报表.doc*')}}
(QA/'checks.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
(QA/'page_text.txt').write_text('\n\n'.join(f'PAGE {i+1}\n{s}' for i,s in enumerate(page_text['docx'])),encoding='utf-8')
print(json.dumps({k:v for k,v in results.items() if k not in ('image_sha256','final_files')},ensure_ascii=False))
