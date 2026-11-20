"""Update the existing official form; preserve non-target OOXML and archive originals."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
from zipfile import ZipFile, ZIP_DEFLATED
from lxml import etree as E

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
QA = HERE / '汇报表更新_20261120'
ARCHIVE = HERE / '归档_20261120修改前'
SUBMIT = BASE / '提交版'
QA.mkdir(exist_ok=True)
ARCHIVE.mkdir(exist_ok=True)
for path in [SUBMIT / '灵驭_中期汇报表.docx', SUBMIT / '灵驭_中期汇报表.doc', HERE / 'report_content.json']:
    backup = ARCHIVE / path.name
    if not backup.exists():
        shutil.copy2(path, backup)

summary = json.loads((BASE / '实验结果_20261120/summary.json').read_text(encoding='utf-8'))
assert summary['primary_trials'] == 40 and summary['retries'] == 38
assert summary['overall']['fixed']['successes'] == 13 and summary['overall']['dual']['successes'] == 14
assert summary['cohort_clarification']['all_project_team_members']

data = json.loads((ARCHIVE / 'report_content.json').read_text(encoding='utf-8'))
data['report_date'] = '2026年11月20日'
data['progress'] = [
    '截至2026年11月20日，项目已完成移动双臂物理仿真、阶段协调控制、Quest 3真实输入链路及双层接触风险分配原型，并完成5位参与者、40个正式试次的真人对照采集与配对分析。研究已从系统联调推进到实际操作条件下的初步比较，形成原始记录、审计清单、分析报告和结果图表。',
    '1. 建立完整搬运任务与判定流程。基于YMBOT模型、MuJoCo和Mink，构建轮地驱动、限矩关节伺服及双臂接触抓取。任务包括夹取托盘、抬升、后退转弯、绕障、放置和撤手；成功要求双侧夹持、抬升至少8 cm、目标台承重、松爪撤手及物件留存并稳定1秒。碰撞、掉落、超时和操作者终止均保留记录。',
    '2. 完成阶段协调与工作空间跟随。抓取和高度调整阶段保留腰部可达性，搬运阶段保持腰部参考姿态，结合双手几何约束、滑移夹持及承重后释放。前期120次独立仿真中的同条件腰部消融显示，腰部最大角度变化范围均值由14.67°降至1.35°，两组均8/8成功；手部均方根误差由5.92 mm增至9.65 mm。工作空间跟随在8次脚本对照中完成任务，脚本摇杆指令时长均值减少约43.9%；该指标不代表真人负担已降低。',
    '3. 实现双层接触风险驱动的运动分配。分别依据接触力、摩擦利用率和相对滑移估计抓持风险，依据物件相对运动与预测边缘余量估计承载风险。每10 ms求解二维凸优化，分配底盘速度和双臂相对前后速度，约束补偿范围、各自及合成速度的变化，并按抓取、悬空搬运和放置阶段启用。风险量来自仿真状态，尚未实现真实传感估计。',
    '4. 完成合成输入的五组对照。冻结参数与源码后，采用4种接触条件、2个新种子，完成固定分配、仅抓持风险、仅承载风险、双层联合和统一降速的40次任务验证。前四组均8/8成功，统一降速组4/8成功。双层联合与固定分配的平均耗时分别为84.47 s和84.77 s，最大托盘倾角均值为2.11°和1.83°。另通过26项工程检查及20次固定输入短测试，识别抬升阶段的承载失稳边界。以上为合成输入试验，与真人数据分开统计。',
    '5. 完成冻结版本的真人对照。P01—P05均为项目团队成员，此前均未使用过VR，练习约10分钟。每人按2种方法×2种接触场景×2次重复完成8个正式试次，目标台高0.75 m、单次时限240秒。正常与低摩擦复合场景在两方法间按相同种子配对；后者同时降低夹持和承载摩擦、增加载荷并设置物件偏置，属于复合难度条件。参与者背景、练习约数及重试主要因操作失误，由负责人在采集后补充说明。',
    '共记录78次正式尝试，其中40次首次尝试、38次额外重试；另有19次试跑。主分析保留每个试次的首次结果，失败按240秒计入限时耗时，以5位参与者为独立统计单位。固定分配成功13/20（65%），双层联合14/20（70%）；平均限时耗时分别为145.4 s和150.9 s。正常场景两方法均10/10成功，低摩擦复合场景分别3/10和4/10成功。双层联合增加1次成功，但耗时略长，现有证据尚未确立整体优势。',
    '6. 完成数据复核并明确局限。首次13次失败中，10次为物件离开托盘，超时、操作者终止和载荷掉落各1次。已核对正式记录的冻结版本、排程、配置与事件，并检查首次试次轨迹连续性。P01第5次有人为暂停，仍保留为首次失败，并补充剔除对应整对试次的敏感性分析。重试不等量可能带来学习影响；团队内小样本限制外推。当前完成的是真人输入操控仿真机器人，实体机器人、灵巧手与示教学习仍在后续计划中。'
]
data['innovation'][2] = '3. 建立仿真消融与真人配对相结合的评价流程。分别设置夹持与承载条件，采用固定分配、两个单风险组、联合组和统一降速组进行合成输入消融；进一步完成5位VR新手的真人对照，按参与者配对汇总，并保留首次失败、重试和异常记录。当前已验证原型与流程可运行，方法的整体优势和适用范围仍需扩大样本检验。'
data['reflections'] = [
    '项目实施使我们把关注点从“能否搬到终点”进一步转向“为什么成功、在哪个阶段失败、改进付出了什么代价”。早期机器人身体晃动说明，仅最小化手部目标误差会使冗余求解器反复调用腰部。定位到自由度分配后，我们按任务阶段保持腰部姿态，并通过同条件消融验证作用，同时记录手部跟踪误差增加的代价。',
    '在新方法设计中，我们发现两类接触稳定不能相互替代：增加夹紧量能够改善把手接触，却不能直接阻止托盘内物件滑向边缘。因此，我们分别观测两层风险，再让风险影响双臂与底盘的分配。采用开源动力学和逆运动学组件，使研究精力能够集中于任务建模、控制机制和可复查的验证。',
    '真人实验进一步修正了我们对改进效果的预期。正常场景下两方法都能完成任务，困难集中在低摩擦复合场景。双层联合仅多成功1次，平均限时耗时反而略长，不能据此宣称整体性能提升。13次首次失败中有10次被判为物件离开托盘，也提示我们应结合操作轨迹继续检查抬升、转向和放置阶段，而不能只依赖前后运动分配解决所有失稳。',
    '负责人回顾，重试主要由操作失误引起。操作失误也是人机交互表现的一部分，不能为了提高成功率而删除。78次正式尝试中有38次重试，若只取每个试次的最后一次结果，两方法都会成为20/20成功，掩盖失败和额外练习。因此，本次采用首次尝试为主、全部尝试为补充的口径，并说明这是采集后确定的处理规则。后续应在采集前约定重试与技术中断的处理方法。',
    '5位参与者均为此前没有VR使用经验的团队成员，练习约10分钟，属于团队内便利样本。没有VR经验不代表不了解系统和研究目标，练习约数也不能代替严格一致的训练记录。不同数量的重试还可能改变后续熟练度。我们将本轮定位为小规模可行性与初步比较实验，后续招募团队外参与者，统一训练和顺序安排，再检验方法是否具有稳定优势。',
    'P01第5次因人为暂停或离开设备，真实计时明显长于仿真时间，说明实际效率还受操作流程影响。我们保留该次首次失败，并补充剔除受影响整对试次的敏感性分析。冻结源码、保存原始输入、按试次窗口统计以及分别报告仿真与墙钟时间，使异常能够被追溯，也避免把流程停顿误解释为控制器性能。'
]
data['plan'] = [
    '（一）中期结果整理与答辩准备',
    '本轮5位参与者、40个正式试次的采集和分析已完成。11月20—21日，结合已形成的分析报告完善中期材料、演示与答辩讲稿，向导师汇报成功、失败及异常情况。将合成输入验证与真人结果分开呈现，明确65%与70%的首次成功率、失败计240秒的耗时口径，以及小样本和重试带来的解释限制。',
    '（二）下一轮实验与方法改进',
    '2026年11月至2027年1月，重点检查低摩擦复合场景中的物件离盘过程，改进抬升姿态、垂向速度与搬运阶段协调。保留本轮冻结版本作为基线，在开发阶段调参后使用新种子验证；进一步分别改变摩擦、载荷和偏置，区分各因素影响，记录成功率、耗时和意图跟踪代价。',
    '招募团队外参与者，统一并记录每种方法的训练时间与操作说明，合理安排休息。采集前明确首次尝试、重试和技术中断的分析规则，完善随机化或顺序平衡，继续以参与者为独立样本。加入操作难度与负担评价，结合轨迹和经同意的录像复核失败原因，避免用离合次数或腰部角度直接替代疲劳测量。',
    '逐步研究风险估计误差对控制的影响，扩展独立腕姿态和灵巧手映射。在平台条件具备后，完成执行器、摩擦与碰撞参数辨识及实体机器人集成，将仿真中的理想状态输入替换为可实现的传感估计。',
    '（三）后续阶段安排',
    '2027年2—3月，扩展操作者、载荷与扰动条件，研究更高维运动分配，完善真人实验与示教数据质量评价。2027年4—5月，完成研究报告、软件整理及论文研究，依据实际成果推进结题。经费使用与报销按实际支出及学校规定核对归档。'
]

limits = {'progress': 2000, 'innovation': 600, 'reflections': 2000, 'plan': 2000}
counts = {k: sum(map(len, data[k])) for k in limits}
assert all(counts[k] <= limit for k, limit in limits.items()), counts

SRC = ARCHIVE / '灵驭_中期汇报表.docx'
OUT = QA / '灵驭_中期汇报表.docx'
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
def w(name):
    return '{' + NS['w'] + '}' + name

with ZipFile(SRC) as z:
    items = {n: z.read(n) for n in z.namelist()}
root = E.fromstring(items['word/document.xml'])
body = root.find('w:body', NS)
tables = body.findall('w:tbl', NS)
rows = tables[1].findall('w:tr', NS)
original_cover_xml = E.tostring(tables[0])
original_rows_xml = [E.tostring(row) for row in rows]

def text_of(p):
    return ''.join(p.itertext())

def set_text(p, text, bold=None):
    first = p.find('w:r', NS)
    rpr = deepcopy(first.find('w:rPr', NS)) if first is not None and first.find('w:rPr', NS) is not None else E.Element(w('rPr'))
    for child in list(p):
        if child.tag != w('pPr'):
            p.remove(child)
    if bold is not None:
        for tag in ('b', 'bCs'):
            for element in rpr.findall('w:' + tag, NS):
                rpr.remove(element)
        if bold:
            E.SubElement(rpr, w('b'))
    r = E.SubElement(p, w('r'))
    r.append(rpr)
    t = E.SubElement(r, w('t'))
    t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
    t.text = text

def replace_cell(row_index, texts, heading=False):
    cell = rows[row_index].find('w:tc', NS)
    paras = cell.findall('w:p', NS)
    template = deepcopy(paras[1] if heading or row_index == 18 else paras[0])
    retained_heading = paras[0] if heading else None
    for p in paras:
        if p is not retained_heading:
            cell.remove(p)
    for text in texts:
        p = deepcopy(template)
        for key in list(p.attrib):
            if E.QName(key).localname in ('paraId', 'textId'):
                del p.attrib[key]
        subhead = text.startswith('（')
        set_text(p, text, bold=subhead)
        pp = p.find('w:pPr', NS)
        if pp is not None:
            for tag in ('keepNext', 'pageBreakBefore'):
                for element in pp.findall('w:' + tag, NS):
                    pp.remove(element)
            if subhead:
                E.SubElement(pp, w('keepNext'))
        cell.append(p)
    trpr = rows[row_index].find('w:trPr', NS)
    if trpr is None:
        trpr = E.Element(w('trPr'))
        rows[row_index].insert(0, trpr)
    split = trpr.find('w:cantSplit', NS)
    if split is None:
        split = E.SubElement(trpr, w('cantSplit'))
    split.set(w('val'), '0')

replace_cell(5, data['progress'])
replace_cell(6, data['innovation'], heading=True)
replace_cell(8, data['reflections'], heading=True)
replace_cell(18, data['plan'])
for p in body.findall('w:p', NS):
    if '填表日期' in text_of(p):
        set_text(p, '填表日期：' + data['report_date'])

# Word requires a paragraph after a table; keep that empty marker from producing a blank page.
after_main_table = list(body)[list(body).index(tables[1]) + 1:]
for p in after_main_table:
    if p.tag == w('p') and not ''.join(p.itertext()).strip():
        for child in list(p):
            p.remove(child)
        pp = E.SubElement(p, w('pPr'))
        E.SubElement(pp, w('spacing'), {w('before'): '0', w('after'): '0', w('line'): '20', w('lineRule'): 'exact'})
        E.SubElement(pp, w('snapToGrid'), {w('val'): '0'})
        rp = E.SubElement(pp, w('rPr'))
        E.SubElement(rp, w('sz'), {w('val'): '2'})

# All school labels, cover fields, member details, table geometry and other parts stay intact.
assert E.tostring(tables[0]) == original_cover_xml
for index, (new, old) in enumerate(zip(rows, original_rows_xml)):
    if index not in (5, 6, 8, 18):
        assert E.tostring(new) == old, index
items['word/document.xml'] = E.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)
with ZipFile(OUT, 'w', ZIP_DEFLATED) as z:
    for name, value in items.items():
        z.writestr(name, value)
with ZipFile(SRC) as a, ZipFile(OUT) as b:
    changed = [n for n in a.namelist() if a.read(n) != b.read(n)]
assert changed == ['word/document.xml']
text = ''.join(root.itertext())
for stale in ('真人预实验尚待开展', '计划邀请5位参与者', '后续将先完成新版真人试跑', '截至2026年11月15日'):
    assert stale not in text, stale
for required in ('13/20（65%）', '14/20（70%）', '145.4 s和150.9 s', '38次额外重试', '团队成员', '未使用过VR', '操作失误'):
    assert required in text, required

(QA / 'report_content.json').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
(QA / 'checks.json').write_text(json.dumps({'counts': counts, 'changed_parts': changed,
    'preserved_rows': [i for i in range(len(rows)) if i not in (5, 6, 8, 18)],
    'source_sha256': hashlib.sha256(SRC.read_bytes()).hexdigest(),
    'summary_sha256': hashlib.sha256((BASE / '实验结果_20261120/summary.json').read_bytes()).hexdigest()}, ensure_ascii=False, indent=2), encoding='utf-8')
print(OUT)
print(counts)
