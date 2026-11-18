# 灵驭 V3 仿真验收

Quest 3 接入准备见 [Quest 3 接入包](../quest3/README.md)。项目根目录新增 `启动Quest3仿真.cmd` 和 `连接Quest3_USB.cmd`。电脑端使用合成控制器输入做通信和物理回归；实际头显仍待到场验证，不计入下述 V3 实验数据。

先打开项目根目录的 `打开仿真验收.cmd`，或直接打开 `simulation/验收.html`。旧页面已保存为 `simulation/验收_v1_存档.html`。如果原页面已经打开，刷新后查看 V3 标题。

## 三种入口

|入口|作用|
|---|---|
|启动三维回放.cmd|打开新版动态任务的保存状态；鼠标旋转、缩放，空格暂停，R 重播。回放不会重新计算动力学|
|启动实时操控.cmd|实时推进轮地接触动力学，输入键盘或 JSONL 位姿包|
|重新运行复杂任务.cmd|从初始场景重新运行共享控制任务，生成独立的状态、指标和日志|

实时操控：W/S 短时前进/后退；A/D 短时转向；方向键调整双手的水平目标；Q/E 降低/抬高手部；G 开合夹爪；空格暂停。手部位置有范围限制。驾车时保持腰部姿态，调整手部目标时允许腰部重新协调。该入口没有真实 VR 硬件连接；没有使用保存状态代替物理执行。

## 重新运行

在项目根目录的 PowerShell 中执行：

```powershell
.\.venv\Scripts\python.exe -X utf8 simulation/research/research_runner_v2.py --seed 401 --dynamic --noise .006 --latency .08 --dropout .1 --target-height .75 --out simulation/research/outputs/acceptance_run
.\.venv\Scripts\python.exe -X utf8 simulation/v2/render.py simulation/research/outputs/acceptance_run
.\.venv\Scripts\python.exe -X utf8 simulation/v2/viewer.py simulation/research/outputs/acceptance_run
```

第一条真正运行物理仿真，第二条把保存的轨迹渲染为 1920×1080、25 fps 原速视频，末尾停留 2 s。渲染不改变轨迹。第三条提供可旋转视角的三维状态检查。

```powershell
# 重跑完整修正版验证；会覆盖该目录中的同名验证结果，建议先备份。
.\.venv\Scripts\python.exe -X utf8 simulation/research/benchmark_v2.py
.\.venv\Scripts\python.exe -X utf8 simulation/research/analyze.py simulation/research/outputs/validation_r2
.\.venv\Scripts\python.exe -X utf8 simulation/research/verify.py simulation/research/outputs/validation_r2
```

依赖位于项目 `.venv`，版本锁文件见 `simulation/requirements-lock.txt`。模型转换沿用项目内的 YMBOT URDF 与网格，场景 XML 引用原始本机网格路径；搬到另一台电脑时，应保留 `ym_assets`，重新运行 `simulation/build_model.py`，然后重新生成场景。已经录好的 MP4 不依赖 Python 和网格。

## 实验文件

- `outputs/validation_r2/`：最终独立种子 400–407 的 120 次试验和冻结源码。
- `outputs/validation_r2_analysis/`：汇总表、每次试验指标、图表、结果解读。
- `outputs/validation/`：第一轮 120 次实验；低台面缺陷被用于后续改进，所以不能再当作修正版的独立验证。
- `../v2/outputs/validation/`：轮地动力学与夹持反馈的另外 128 次验证，与 V3 分开统计。
- `outputs/demo_dynamic/`、`outputs/demo_low/`：从最终独立验证复制的完整演示及原始数据；选择规则在 `selection.json`。
- `outputs/waist_comparison/`：同条件腰部控制对照，原速截取 8–38 s，不插值改变关节运动。

每次试验包含 `scene.xml`、`summary.json`、`trajectory.npz`、`metrics.csv`、`input_packets.jsonl`。轨迹存有 qpos、qvel、执行器命令、目标、任务阶段和指标。包记录标注 `source: synthetic_tracking_model` 和 `hardware_verified: false`，不是人类示教数据。

实际输入接口沿用 `simulation/teleop.py` 的坐标变换与离合标定。实时入口可用 `--packets <路径>`，包需包含 timestamp、frame=world_meters、left/right、rotation、aperture（0–0.045 m），可选 base_twist=[前向速度,偏航角速度]。输入按时间单调递增验证；实时回放重新运行物理控制，不直接写入机器人关节状态。

## 研究解释

阅读 [研究设计与来源](研究设计与来源.md) 和 `outputs/validation_r2_analysis/结论与限制.md`。关键问题是“带载移动中抑制腰部冗余运动，并处理遥操作输入扰动”，不是声称已经训练自主策略或完成真机 VR 系统。

最终成功判断必须同时包含抓取确认、抬升、无障碍碰撞、目标支撑、松手、散件留存和最后 1 s 的位置/速度稳定。独立核验脚本重新从最后 100 个状态重建接触和物体状态，不只读取成功标记。HTML 做静态资源核验；视频和代表帧做解码与图像检查，未通过浏览器自动化进行页面视觉验收。
