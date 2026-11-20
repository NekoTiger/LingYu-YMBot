# -*- coding: utf-8 -*-
"""把提交版PPT第6-8页及第11页的"计划/待采集"口径更新为已完成口径。"""
import shutil
from datetime import datetime
from pathlib import Path

from pptx import Presentation

BASE = Path(r"D:\UserData\Desktop\Coding\Innovation and Entrepreneurship\2026大创\中期答辩材料")
PPTX = BASE / "提交版" / "灵驭_中期答辩_正式版.pptx"
BACKUP_DIR = BASE / "制作过程" / "归档_20261120修改前"


def replace_text(shape, old, new):
    if not shape.has_text_frame:
        return False
    changed = False
    for para in shape.text_frame.paragraphs:
        runs = para.runs
        full = "".join(r.text for r in runs)
        if old not in full:
            continue
        if any(r.text == old for r in runs):
            for r in runs:
                if r.text == old:
                    r.text = new
        else:
            runs[0].text = new
            for r in runs[1:]:
                r.text = ""
        changed = True
    return changed


def apply_replacement(slide, replacements):
    for old, new in replacements.items():
        for shape in slide.shapes:
            replace_text(shape, old, new)
            if shape.has_table:
                for row in shape.table.rows:
                    for cell in row.cells:
                        for para in cell.text_frame.paragraphs:
                            runs = para.runs
                            full = "".join(r.text for r in runs)
                            if old not in full:
                                continue
                            if any(r.text == old for r in runs):
                                for r in runs:
                                    if r.text == old:
                                        r.text = new
                            else:
                                runs[0].text = full.replace(old, new)
                                for r in runs[1:]:
                                    r.text = ""


def main():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup = BACKUP_DIR / "灵驭_中期答辩_正式版_20261120修改前.pptx"
    if not backup.exists():
        shutil.copy2(PPTX, backup)

    prs = Presentation(str(PPTX))
    slides = list(prs.slides)

    apply_replacement(slides[5], {
        "真人评价进入准备阶段": "真人对照实验已完成",
    })
    apply_replacement(slides[6], {
        "答辩前的真人对照实验": "真人对照实验：整体优势尚未确立",
        "计划于11月17—18日采集，检验辅助控制是否改善人的操作表现": "11月17—18日采集完成，固定分配65%，双层联合70%",
        "标准遥操作 / 辅助遥操作": "固定分配 / 双层联合",
        "60 cm / 75 cm目标台，静态绕障": "75 cm目标台，静态绕障，正常/低摩擦",
    })
    apply_replacement(slides[7], {
        "答辩前": "已完成",
        "检验辅助控制是否提高有效操作产出": "整体优势尚未确立，已定位主要失败原因",
    })
    apply_replacement(slides[10], {
        "真人对照实验已准备": "5人真人对照已完成",
    })

    notes = {
        5: "【建议25秒】在仿真验证之外，我们已用真实Quest 3接通控制链路，完成双手柄标定、双臂、夹爪和底盘联调。"
           "左图是实际设备输入驱动后保存的物理状态回放，不是头显画面截图，也不是合成控制器演示。"
           "随后在11月17—18日完成5位参与者的真人对照实验，采集40次正式试次和38次额外重试。\n\n"
           "来源：simulation/quest3/sessions/20261116_115607_04cd8e/session.json。来源字段webxr_live，设备声明Quest3。"
           "截图是该会话最高载荷状态的重新渲染。现有交互为第三人称立体仿真，刚性双手目标与同步平行夹爪；独立腕姿态及灵巧手仍待扩展。"
           "真人结果见 实验结果_20261120/正式实验分析报告.md。",
        6: "【建议65秒】真人对照实验已于11月17—18日完成：5位此前未使用VR的团队成员，练习约10分钟，每人8个正式试次共40次，另有38次额外重试。"
           "分析保留首次尝试，失败按240秒计时。固定分配成功13/20（65%），双层联合14/20（70%）；平均限时耗时145.4秒对150.9秒。"
           "正常场景各10/10，低摩擦复合场景3/10对4/10。13次首次失败中10次为散件离开托盘。"
           "按5位参与者配对，成功率差5个百分点，探索性95%区间约-29到+39个百分点，尚不能确立双层联合的整体优势。\n\n"
           "口径：不能把40次重复测量当成40位独立用户；约10分钟练习来自负责人回忆；重试主要因操作失误，仍保留首次失败口径。"
           "效率与剔除P01第5次人为暂停的敏感性分析见 实验结果_20261120/答辩结果页与讲稿.md。",
        7: "【建议40秒】本阶段的主要成果是形成一个可以解释、比较和复查的研究原型：阶段协调显著减少搬运中的腰部冗余运动，"
           "受扰输入实验支持完整共享控制组合的作用，真人对照实验确认整条采集、自动判定与配对分析链路可用，"
           "同时如实报告了整体优势尚未确立和主要失败原因。后续按原任务书补齐腕姿态、灵巧手和真实机器人参数与部署，"
           "并在扩大样本、统一练习与重试规则后重新检验人的操作表现。我的汇报结束，谢谢老师。\n\n"
           "本页后的补充页供问答查阅，不计入五分钟正文。前8页建议合计300秒，含第2页25秒视频。",
    }
    for idx, text in notes.items():
        notes_slide = slides[idx].notes_slide
        notes_slide.notes_text_frame.text = text

    prs.save(str(PPTX))
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"updated {PPTX.name} at {stamp}")
    print(f"backup: {backup.name}")


if __name__ == "__main__":
    main()
