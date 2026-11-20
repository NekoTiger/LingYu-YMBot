# -*- coding: utf-8 -*-
import sys, os
sys.stdout.reconfigure(encoding="utf-8")
from PIL import Image

ROOT = r"D:\UserData\Desktop\Coding\Innovation and Entrepreneurship\2026大创"
VZ = r"C:\Users\10141\.codex\visualizations\2026\11\20\01a1f773-1c45-7cf0-b932-52a3aba7ecf0"
OUT = os.path.join(VZ, "uniform")
os.makedirs(OUT, exist_ok=True)

CW, CH = 1600, 1000

def letterbox(src, dst):
    im = Image.open(src).convert("RGB")
    scale = min(CW / im.width, CH / im.height)
    nw, nh = round(im.width * scale), round(im.height * scale)
    im = im.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGB", (CW, CH), (255, 255, 255))
    canvas.paste(im, ((CW - nw) // 2, (CH - nh) // 2))
    canvas.save(dst)
    print(dst, canvas.size, "content", (nw, nh))

letterbox(os.path.join(VZ, "ppt_formal", "image1.png"), os.path.join(OUT, "fig1.png"))
letterbox(os.path.join(VZ, "ppt_road", "image2.png"), os.path.join(OUT, "fig2.png"))
letterbox(os.path.join(ROOT, "仿真成果_20261117_双层风险", "搬运.png"), os.path.join(OUT, "fig3.png"))
letterbox(os.path.join(ROOT, "仿真成果_20261117_双层风险", "五组任务对照.png"), os.path.join(OUT, "fig4.png"))
letterbox(os.path.join(ROOT, "中期答辩材料", "实验结果_20261120", "01_正式实验主结果.png"), os.path.join(OUT, "fig5.png"))
