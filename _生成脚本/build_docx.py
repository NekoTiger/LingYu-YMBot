# -*- coding: utf-8 -*-
"""生成《灵驭项目进展与 Quest 3 实验说明.docx》"""
import os

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "灵驭_项目进展与实验说明.docx")

EA = "微软雅黑"
LATIN = "Calibri"
HEADER_FILL = "1F3864"
ALT_FILL = "EDF1F8"
BORDER = "D9D9D9"
BLACK = RGBColor(0, 0, 0)
WHITE = RGBColor(255, 255, 255)

doc = Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Inches(8.5), Inches(11)
sec.top_margin = sec.bottom_margin = Inches(0.9)
sec.left_margin = sec.right_margin = Inches(1.0)


def set_ea(el, name=EA):
    rpr = el.get_or_add_rPr()
    rpr.get_or_add_rFonts().set(qn("w:eastAsia"), name)


def tune(style, size, before, after):
    style.font.name = LATIN
    style.font.size = Pt(size)
    style.font.bold = True
    style.font.color.rgb = BLACK
    style.paragraph_format.space_before = Pt(before)
    style.paragraph_format.space_after = Pt(after)
    set_ea(style.element)


normal = doc.styles["Normal"]
normal.font.name = LATIN
normal.font.size = Pt(11)
normal.font.color.rgb = BLACK
normal.paragraph_format.space_after = Pt(6)
normal.paragraph_format.line_spacing = 1.15
set_ea(normal.element)

tune(doc.styles["Heading 1"], 15, 14, 6)
tune(doc.styles["Heading 2"], 12.5, 10, 4)

title_style = doc.styles["Title"]
title_style.font.name = LATIN
title_style.font.size = Pt(22)
title_style.font.bold = True
title_style.font.color.rgb = BLACK
title_style.paragraph_format.space_after = Pt(4)
set_ea(title_style.element)
for ppr in title_style.element.findall(qn("w:pPr")):
    for pbdr in ppr.findall(qn("w:pBdr")):
        ppr.remove(pbdr)


def para(text="", lead=None, style=None, size=None, align=None, space_after=None):
    p = doc.add_paragraph(style=style)
    if align is not None:
        p.alignment = align
    if lead:
        rl = p.add_run(lead)
        rl.bold = True
        if size:
            rl.font.size = Pt(size)
        set_ea(rl._element)
    if text:
        r = p.add_run(text)
        if size:
            r.font.size = Pt(size)
        set_ea(r._element)
    if space_after is not None:
        p.paragraph_format.space_after = Pt(space_after)
    return p


def shade(cell, fill):
    tcpr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tcpr.append(shd)


def make_table(headers, rows, widths, size=10.5):
    table = doc.add_table(rows=1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    tblpr = table._tbl.tblPr
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tblpr.append(layout)
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = OxmlElement("w:" + edge)
        e.set(qn("w:val"), "single")
        e.set(qn("w:sz"), "4")
        e.set(qn("w:space"), "0")
        e.set(qn("w:color"), BORDER)
        borders.append(e)
    tblpr.append(borders)
    mar = OxmlElement("w:tblCellMar")
    for tag in ("top", "left", "bottom", "right"):
        m = OxmlElement("w:" + tag)
        m.set(qn("w:w"), "80" if tag in ("top", "bottom") else "100")
        m.set(qn("w:type"), "dxa")
        mar.append(m)
    tblpr.append(mar)

    def fill(cell, text, bold, color, align, width, bg=None):
        cell.width = Inches(width)
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        p = cell.paragraphs[0]
        p.alignment = align
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.line_spacing = 1.15
        r = p.add_run(text)
        r.font.size = Pt(size)
        r.bold = bold
        r.font.color.rgb = color
        set_ea(r._element)
        if bg:
            shade(cell, bg)

    for i, h in enumerate(headers):
        fill(table.rows[0].cells[i], h, True, WHITE, WD_ALIGN_PARAGRAPH.CENTER, widths[i], HEADER_FILL)
    for ri, row in enumerate(rows):
        cells = table.add_row().cells
        for ci, item in enumerate(row):
            if isinstance(item, tuple):
                text, align = item
            else:
                text, align = item, WD_ALIGN_PARAGRAPH.LEFT
            fill(cells[ci], text, False, BLACK, align, widths[ci], ALT_FILL if ri % 2 else None)
    header_trpr = table.rows[0]._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    header_trpr.append(tbl_header)
    for row in table.rows:
        trpr = row._tr.get_or_add_trPr()
        cant_split = OxmlElement("w:cantSplit")
        cant_split.set(qn("w:val"), "true")
        trpr.append(cant_split)
    return table


title = doc.add_paragraph(style="Title")
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
tr = title.add_run("灵驭项目进展与 Quest 3 实验说明")
set_ea(tr._element)

para("负责人：蔡晓虎 · 2026 年 11 月 18 日 · 项目组内部说明",
     size=11, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=14)

para("各位好。11 月 21 日中期答辩前，需要大家完成 Quest 3 里的真人对照实验，并在答辩现场讲清各自承担的工作。"
     "这份说明把项目背景、当前进展、实验安排和答辩分工整理在一起，实验前我会再当面演示一遍操作。")

doc.add_heading("项目是什么", level=1)
para("「灵驭」是基于 VR 遥操作的人形轮式机器人灵巧作业与协调运动控制项目（校级培育项目，编号 2026PY-600，"
     "指导教师王长波教授）。简单说：人戴上 Quest 3，用手柄在 VR 里遥控一个轮式人形机器人，"
     "完成「抓起托盘 → 绕过障碍 → 搬到另一张台面放下」的搬运任务。项目研究的是：双手忙着精细操作时，"
     "机器人的双臂与轮式底盘该怎么配合，才能抓得稳、放得稳、人还不累。")
para("中期研究问题：在轮式双臂机器人的 VR 搬运任务中，协调辅助能否提高完整任务成功率、缩短限时耗时、"
     "提高单位时间成功次数，同时减少不必要的腰部运动？", style="List Bullet")
para("当前载体是电脑上的物理仿真（MuJoCo + YMBOT 机器人模型 + Mink 逆运动学）；接入实体机器人是后续阶段。",
     style="List Bullet")

doc.add_heading("目前的进展", level=1)
make_table(
    ["时间", "进展"],
    [
        (("2026-05", WD_ALIGN_PARAGRAPH.CENTER), "立项申报与立项答辩通过"),
        (("5 月-10 月", WD_ALIGN_PARAGRAPH.CENTER), "文献调研与方案设计；搭建移动双臂物理仿真、完整搬运任务与物理判据"),
        (("11 月上中旬", WD_ALIGN_PARAGRAPH.CENTER), "阶段协调控制（搬运阶段腰部保持等）通过 120 次独立自动验证；完成动态障碍版本"),
        (("11-16", WD_ALIGN_PARAGRAPH.CENTER), "Quest 3 头显与双手柄首次真实接入：浏览器 WebXR → USB → 电脑仿真，头显内可实时操控"),
        (("11-17", WD_ALIGN_PARAGRAPH.CENTER), "「双层接触风险分配」原型：5 组方法对照、40 次完整任务自动验证、26 项检查通过"),
        (("11-18", WD_ALIGN_PARAGRAPH.CENTER), "中期汇报表与答辩 PPT 定稿；进入真人实验阶段"),
        (("11-21", WD_ALIGN_PARAGRAPH.CENTER), "中期答辩（汇报 5 分钟 + 提问 5 分钟）"),
    ],
    [1.3, 5.0],
)
para("目前已有的仿真证据来自自动脚本，不是真人数据：", space_after=2)
para("搬运阶段腰部保持把同条件腰部最大变化范围均值从 14.67° 降到 1.35°，代价是手部跟踪 RMSE 从 5.92 mm 升到 9.65 mm。",
     style="List Bullet")
para("新「双层联合」方法与固定分配基线在 40 次完整任务中各 8/8 成功，平均耗时 84.47 秒对 84.77 秒——"
     "目前还没有证明新方法更好。", style="List Bullet")
para("这正是真人实验要回答的问题：真人操作下，新方法是否更稳、更快、更好用。", style="List Bullet")

doc.add_heading("系统是怎么运转的", level=1)
para("只需要了解三点，不用懂代码：", space_after=2)
para("Quest 3 浏览器打开网页点「进入 VR」，两只手柄的位置实时映射成机器人双手；"
     "头显里看到的是立体仿真画面（默认并肩视角，可切换）。", style="List Bullet")
para("握键相当于离合：同时按住两侧握键，双手才控制机器人；松开任一侧即停；每次重新握住都会重新标定。",
     style="List Bullet")
para("扳机控制夹爪开合；左摇杆控制底盘前进和转向。", style="List Bullet")

doc.add_heading("你们要做的实验（每人约 60-90 分钟）", level=1)
para("每位同学一次到场完成：先练习，再完成 8 次正式试次。具体流程：", space_after=2)
para("先跟我约时间。到场后先练习两种方法，各约 10 分钟，熟悉抓取、移动、转向、放置，可以随时提问。",
     style="List Number")
para("正式试次每人 8 次 = 2 种方法 × 2 种接触场景 × 2 次重复，顺序由程序交错安排，按提示完成即可。",
     style="List Number")
para("每轮流程：观察员点「准备场景」→ 点「开始计时」→ 你在 VR 里完成任务 → 成功或失败自动记录。",
     style="List Number")
para("任务路线：源台抓起托盘 → 先后退至障碍外侧 → 转向 → 绕到目标台一侧 → 靠近 → 在绿色目标区放下 → 抬手撤离。",
     style="List Number")
para("固定分配（基线）按固定规则分配双臂与底盘运动；双层联合（新方法）实时估计「夹爪抓得稳不稳」和"
     "「托盘上的物件稳不稳」两类接触风险，动态调整双臂与底盘的分配。接触场景分正常摩擦和低摩擦两种。",
     lead="两种方法：")
para("双侧夹持 → 抬升至少 8 cm → 目标台承重 → 松爪 → 双手撤离 → 物件留存并稳定 1 秒。"
     "撞障碍、物件掉落、超时（约 4 分钟，以试跑后冻结的协议为准）或手动终止都记失败。",
     lead="成功判据（程序自动判定）：")
para("", lead="操作速记：", space_after=2)
para("同时握住两侧握键才开始动；松开任一侧 = 暂停运动（计时继续）。", style="List Bullet")
para("扳机同步开合夹爪；左摇杆控制底盘。", style="List Bullet")
para("卡住按 B 停止；松开双握键后按 X 恢复，再重新握住。", style="List Bullet")
para("没握离合时：右摇杆转视角、左 Y 切视角，不用绕机器人走动。", style="List Bullet")
para("到台前用双手小幅调整；下放要等台面承重再松爪。", style="List Bullet")
para("", lead="注意事项：", space_after=2)
para("试次会录一段佩戴操作录像和电脑画面（用编号对应，不记姓名，需要你同意）。", style="List Bullet")
para("失败、超时、中断全部如实保留；不会挑好的结果重录。", style="List Bullet")
para("每次实验配一位观察员，负责核对编号、准备场景、计时、记录卡顿与失败原因，大家轮换。", style="List Bullet")

doc.add_heading("接下来几天的安排", level=1)
make_table(
    ["日期", "事项"],
    [
        (("11-18 ~ 19", WD_ALIGN_PARAGRAPH.CENTER), "负责人 P00 试跑，调整时限，冻结协议与源码"),
        (("11-18 ~ 20", WD_ALIGN_PARAGRAPH.CENTER), "五位同学正式实验（每人约 60-90 分钟，预约制）"),
        (("11-19", WD_ALIGN_PARAGRAPH.CENTER), "汇总配对结果，核对录像与轨迹"),
        (("11-20", WD_ALIGN_PARAGRAPH.CENTER), "数据复核、导师审阅、模拟答辩（全体参加）"),
        (("11-21", WD_ALIGN_PARAGRAPH.CENTER), "正式答辩（5 分钟汇报 + 5 分钟提问，全体到场）"),
    ],
    [1.3, 5.0],
)

doc.add_heading("答辩前各自准备什么", level=1)
para("提问环节可能问到每个人，重点是你做了什么、用了哪些开源组件、改了什么、一个失败案例及原因。")
make_table(
    ["成员", "项目内分工", "重点准备"],
    [
        ("蔡晓虎（负责人）", "统筹方案、系统联调与实验组织", "总体汇报与答辩"),
        ("张潇瀚", "VR 映射、交互界面与设备联调", "WebXR 输入链路、手柄到手臂的映射、离合标定"),
        ("颜硕", "协调控制、仿真与消融验证", "阶段协调与腰部保持、双层风险分配、消融结果"),
        ("宋易乐", "软硬件集成、测试与数据采集", "设备连接与记录流程、自己的试次数据"),
        ("邓智文", "文献整理、数据分析与研究报告", "文献背景、指标口径、汇总分析"),
    ],
    [1.5, 2.3, 2.5],
)
para("每个人都要能讲自己的试次数据：成功几次、失败原因是什么、哪个环节最卡。", space_after=0)

doc.add_heading("想了解更多", level=1)
para("实验安排与协议：simulation/quest3/11月21日答辩推进与实验安排.md", style="List Bullet")
para("正式实验入口与操作：simulation/quest3/双层风险版使用与方法.md（根目录双击 启动Quest3双层风险版.cmd）",
     style="List Bullet")
para("项目背景全貌：proposal_text.txt", style="List Bullet")
para("中期汇报表（11-18 定稿）：中期答辩材料/提交版/灵驭_中期汇报表.docx", style="List Bullet")

doc.save(OUT)
print("saved:", OUT)
