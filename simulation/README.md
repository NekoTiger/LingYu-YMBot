# 灵驭仿真验收

**当前交付为 V3。** 请先阅读 [新版运行说明](research/README.md)、[研究设计与来源](research/研究设计与来源.md) 和 [最终独立验证结论](research/outputs/validation_r2_analysis/结论与限制.md)。根目录启动入口和 `验收.html` 已更新为轮地接触、腰部稳定与动态障碍任务。以下内容保留为第一版的运行档案。

本目录实现项目已有 YMBOT 的单臂取物搬运和双臂托盘搬运，使用 MuJoCo 接触动力学与 Mink 逆运动学。输入为合成手部目标；代码、数据和视频都在本机，运行不需要在线模型或 API。

## 先看成果

项目根目录双击 `打开仿真验收.cmd`，查看视频、统计和研究说明。主视频展示双臂夹起托盘、转弯搬运、放置松手；橙色物体为独立动态载荷。单臂视频展示抓取小物体后跨工作台搬运。

- `outputs/bimanual_demo/demo.mp4`：双臂主演示，43 秒，1 倍速。
- `outputs/single_demo/demo.mp4`：单臂演示，43 秒，1 倍速。
- `outputs/comparison/comparison.mp4`：同种子、同扰动的独立控制与双臂耦合补偿对照。
- `outputs/analysis/改进与验证.md`：三种方法的独立验证结果，是最终统计的首选入口。
- `outputs/analysis/实验结果.md`：第一轮两种方法的完整结果，包括后来发现的问题。
- `docs/研究路线与开源来源.md`：论文选择、实际复用和本项目新增内容。

## 实际运行

在项目根目录打开 PowerShell。独立 Python 环境已经安装在 `.venv`。

```powershell
# 重新计算一段物理仿真，保存视频及所有轨迹，约 1 分钟
.\.venv\Scripts\python.exe -X utf8 simulation/run.py --task bimanual --mode coupled --disturbance .035 --video --out simulation/outputs/acceptance_run

# 只计算、不录视频，通常数秒完成 43 秒模拟时间
.\.venv\Scripts\python.exe -X utf8 simulation/run.py --task single --mode coordinated --out simulation/outputs/acceptance_single

# 交互查看已记录的三维轨迹
.\.venv\Scripts\python.exe -X utf8 simulation/viewer.py

# 实时键盘操控
.\.venv\Scripts\python.exe -X utf8 simulation/interactive.py
```

三维回放支持鼠标旋转、缩放，空格暂停，R 从头播放，Esc 退出。回放直接展示保存的物理状态；需要重新做实验时运行 `run.py`。

实时操控：W/S 控制底盘前后，A/D 转向；方向键移动双手世界坐标目标，Q/E 降低/升高手，G 开合夹爪，C 循环切换独立控制、底盘反馈、双臂耦合三种模式，空格暂停。初始双手在托盘上方，先逐步按 Q 下移约 9 cm，再按 G 闭合，然后按 E 抬起。键盘接口是人工调试入口，不是已经连接的 VR 设备。

## 完整复现实验

```powershell
.\.venv\Scripts\python.exe -X utf8 simulation/build_model.py
.\.venv\Scripts\python.exe -X utf8 simulation/test_integrity.py
.\.venv\Scripts\python.exe -X utf8 simulation/benchmark.py --seeds 12 --workers 2
.\.venv\Scripts\python.exe -X utf8 simulation/evaluation.py
.\.venv\Scripts\python.exe -X utf8 simulation/analyze.py
.\.venv\Scripts\python.exe -X utf8 simulation/ablation.py
.\.venv\Scripts\python.exe -X utf8 simulation/final_analysis.py
```

两轮总计 384 次完整试验；生成日志数据会占用约 GB 级空间，实际以目录为准。为方便本机运行，MJCF 使用生成时的绝对网格路径；移动项目后先重跑 `build_model.py`。依赖固定在 `requirements-lock.txt`。新环境使用 Python 3.13，创建 venv 后安装该文件。重跑批量脚本会覆盖对应输出目录中本项目生成的实验文件。

## 当前可主张的进展

1. 完成机器人模型适配、上肢与躯干受限 IK、两个接触搬运任务及记录回放。
2. 发现单纯底盘反馈降低世界位置误差，却可能损害双臂共同夹持稳定性。
3. 增加双手相对位姿软约束，并在新种子上检验成功率、世界位置误差与相对误差的取舍。
4. 提供设备无关的输入包、WebXR 坐标变换、离合校准及数据完整性测试。

## 模型边界

- 现有 URDF 的手和车轮是固定关节。本轮替换手部外观为带固定安装适配的研究用平行夹爪；这不能当作真实灵巧手验证。
- 底盘使用平面 x/y/yaw 伺服。名义运输路径由后退、原地转弯和直行组成，但实际扰动允许平面横向运动；没有轮胎滑移、非完整约束或轮地接触模型，不能评估车轮动力学和防倾倒。
- 上肢启用理想重力补偿，惯性沿用 URDF，并非经过系统辨识的真机参数。原 CAD 网格仅供外观；碰撞主要覆盖地面、工作台、物体、夹爪和底盘盒体，未验证手臂自碰撞或完整环境碰撞。
- 本轮输入是预设轨迹，物体初始状态和目标位置已知，未实现视觉感知、自动导航或真人 VR 用户研究。
- 路线与阶段切换固定，当前结果不支持“比人类更快”或“示教效率已提高”的结论。
- 对照使用相同物理参数，不改变摩擦或夹持力来让改进方法获胜；物体由摩擦接触运动，没有焊接或隐藏绑定。

## 数据格式

`trajectory.npz`：100 Hz 的 `time`、`qpos`、`qvel`、`ctrl`、`hand_targets`、`hand_actual`、场景参数 `metadata`。手部目标每行为左手 xyz、右手 xyz、名义底盘 x/y/yaw、夹爪开度，共 10 个值；双手目标姿态为该名义 yaw 绕 z 轴的旋转。`hand_actual` 为双手实际 xyz。MuJoCo 自由关节四元数使用 wxyz 顺序。

`metrics.csv`：位置跟踪误差、物体世界位置和倾角、夹爪接触数与法向力总量、名义及实际底盘位姿。`summary.json`：场景参数、评价版本、成功条件各分项和汇总指标。最后 1 秒连续检查到位、静止、松手、直立与载荷保留；错误地把落地静止算作成功的情况会被高度和目标位置检查拒绝。

`hand_targets.jsonl`：可回放的设备无关目标包，每帧注明 `source: synthetic_reference`。`teleop.py` 提供格式校验和 WebXR 相对位置映射，真实设备尚未联调。

## 文件职责

| 文件 | 职责 |
|---|---|
| build_model.py / scene.py | 原模型转换和接触场景 |
| control.py | 三种方法共用的 IK 与相对约束 |
| run.py | 物理推进、任务目标和完整记录 |
| evaluation.py | 连续成功判据和离线重算 |
| benchmark.py / ablation.py | 两轮实验和独立验证 |
| analyze.py / final_analysis.py | 汇总、置信区间和图表 |
| viewer.py / interactive.py / teleop.py | 三维回放、人工输入与设备接口 |
| render_trace.py | 从保存轨迹导出演示和对照视频 |
| test_integrity.py | 物理模型、输入和限速检查 |

实际开源复用在 `third_party` 和研究路线说明中标注。原申报书、答辩材料及原始机器人资产未被改写；本轮没有制作 PPT、部署真机或发布外部仓库。
