# -*- coding: utf-8 -*-
import sys, os, zipfile
sys.stdout.reconfigure(encoding="utf-8")
BASE = r"D:\UserData\Desktop\Coding\Innovation and Entrepreneurship\2026大创\中期答辩材料\提交版"
VZ = r"C:\Users\10141\.codex\visualizations\2026\11\20\01a1f773-1c45-7cf0-b932-52a3aba7ecf0"
for name in ["灵驭_中期答辩_路演修订版_20261120.pptx", "灵驭_中期答辩_正式版.pptx"]:
    src = os.path.join(BASE, name)
    dst = os.path.join(VZ, "ppt_" + ("road" if "路演" in name else "formal"))
    os.makedirs(dst, exist_ok=True)
    with zipfile.ZipFile(src) as z:
        for n in z.namelist():
            if n.startswith("ppt/media/") and not n.endswith("/"):
                data = z.read(n)
                out = os.path.join(dst, os.path.basename(n))
                with open(out, "wb") as fh:
                    fh.write(data)
    print("==", name, "==")
    for f in sorted(os.listdir(dst), key=lambda x: -os.path.getsize(os.path.join(dst,x))):
        print(os.path.getsize(os.path.join(dst,f)), f)
