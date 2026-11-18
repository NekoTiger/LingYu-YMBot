import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {Presentation, PresentationFile} from '@oai/artifact-tool';

const HERE=path.dirname(fileURLToPath(import.meta.url));
const ROOT=path.resolve(HERE,'../..');
const ASSET=path.join(HERE,'assets');
const images=Object.fromEntries(await Promise.all(['cover.png','task.png','placement.png','quest_live.png'].map(async name=>[name,new Uint8Array(await fs.readFile(path.join(ASSET,name)))])));
const OUT=path.join(HERE,'deck-render');
await fs.mkdir(OUT,{recursive:true});
const FONT='Microsoft YaHei';
const C={ink:'#152B3D',teal:'#007F86',muted:'#607382',gray:'#A9B7C2',light:'#E3E9EC',gold:'#B2782B',white:'#FFFFFF'};
const p=Presentation.create({slideSize:{width:1280,height:720}});
const agg=JSON.parse(await fs.readFile(path.join(ROOT,'simulation/research/outputs/validation_r2_analysis/aggregate.json'),'utf8'));
const row=(condition,method)=>agg.find(r=>r.condition===condition&&r.method===method);
const free=row('tracking','shared_free_waist'), full=row('tracking','shared');
const reduce=(100*(1-full.waist_peak_to_peak_deg/free.waist_peak_to_peak_deg)).toFixed(1);
const text=(s,t,x,y,w,h,size=26,color=C.ink,bold=false,name='')=>{
  const o=s.shapes.add({geometry:'textbox',name:name||t.slice(0,24),position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
  o.text=t;o.text.style={typeface:FONT,fontSize:size,color,bold,autoFit:'none',wrap:'square',insets:0,verticalAlignment:'top'}; return o;
};
const pic=(s,name,x,y,w,h,fit='cover')=>s.images.add({blob:images[name],contentType:'image/png',alt:name,fit,position:{left:x,top:y,width:w,height:h}});
function slide(title,sub=''){
  const s=p.slides.add();s.background.fill=C.white;
  const n=p.slides.items.length;
  text(s,n<=8?'华东师范大学  本科生创新训练培育项目':'补充材料  供问答查阅',64,25,1000,24,16,C.muted);
  text(s,title,64,77,1150,66,44,C.ink,true,'slide-title');
  if(sub)text(s,sub,66,147,1148,46,23,C.muted);
  text(s,'灵驭  /  中期研究进展  /  数据截至 2026.11.16',64,677,1000,24,15,C.muted);
  text(s,String(n).padStart(2,'0'),1160,674,56,28,18,C.muted);
  return s;
}
function table(s,values,x,y,w,h,widths,sz=23){
  const t=s.tables.add({rows:values.length,columns:values[0].length,left:x,top:y,width:w,height:h,values,columnWidths:widths});
  t.borders.assign({style:'solid',fill:C.light,width:.6});
  t.cells.block({row:0,column:0,rowCount:values.length,columnCount:values[0].length}).assign({margins:{left:14,right:14,top:10,bottom:10},anchor:'center'});
  for(let r=0;r<values.length;r++)for(let c=0;c<values[0].length;c++){
    const cell=t.getCell(r,c);cell.fill=r===0?C.ink:r%2===0?'#F4F7F8':C.white;
    cell.text.style={typeface:FONT,fontSize:sz,color:r===0?C.white:C.ink,bold:r===0,alignment:c===0?'left':'center',verticalAlignment:'middle',autoFit:'none'};
  }
  return t;
}
function bars(s,categories,series,x,y,w,h,max,unit,title,size=20){
  const ch=s.charts.add('bar',{position:{left:x,top:y,width:w,height:h},title,titleTextStyle:{typeface:FONT,fontSize:24,fill:C.ink},categories,series,
    chartFill:C.white,plotAreaFill:C.white,chartLine:{fill:'none',width:0},
    barOptions:{direction:'column',grouping:'clustered',gapWidth:90},hasLegend:series.length>1,
    legend:{position:'bottom',textStyle:{typeface:FONT,fontSize:size,fill:C.ink}},
    xAxis:{textStyle:{typeface:FONT,fontSize:size,fill:C.ink},line:{fill:C.gray,width:1}},
    yAxis:{min:0,max,majorUnit:unit,numberFormatCode:'0',textStyle:{typeface:FONT,fontSize:size,fill:C.muted},majorGridlines:{fill:C.light,width:.7}},
    dataLabels:{showValue:true,position:'outEnd',numberFormatCode:max<=9?'0':'0.00',textStyle:{typeface:FONT,fontSize:24,fill:C.ink,bold:true}}
  });return ch;
}
const resultsSource='数据：simulation/research/outputs/validation_r2_analysis/aggregate.json、per_trial.json、结论与限制.md。协议：simulation/research/研究设计与来源.md。独立验证种子400—407。';

// 01
{
 const s=p.slides.add();s.background.fill=C.white;
 pic(s,'cover.png',655,0,625,720);
 text(s,'华东师范大学',64,46,530,38,25,C.muted);
 text(s,'2026年度本科生创新训练培育项目',64,91,550,30,19,C.muted);
 text(s,'灵驭',60,193,550,112,88,C.ink,true);
 text(s,'基于VR遥操作的人形轮式机器人\n灵巧作业与协调运动控制',64,320,560,108,33,C.ink,true);
 text(s,'中期汇报',65,462,520,42,28,C.teal);
 text(s,'汇报人  蔡晓虎\n指导教师  王长波教授、李洋副教授',65,536,560,72,22,C.ink);
 text(s,'计算机科学与技术学院  VPX研究组\n2026.11.21',65,634,560,64,19,C.muted);
 s.speakerNotes.text='【建议15秒】各位老师好，我汇报的是灵驭项目。我们聚焦轮式人形机器人在双臂搬运时的遥操作协调问题。本阶段完成了物理仿真、阶段协调控制及真实Quest接入，下面重点介绍方法和实验依据。\n\n封面机器人为本项目YMBOT仿真模型，来自demo_dynamic保存状态第800帧，不是真机照片。项目和人员信息源于立项申报书。';
}
// 02
{
 const s=slide('完整搬运任务中的协调难题','双手夹持自由负载，底盘移动时仍需保持抓持和可靠放置');
 pic(s,'task.png',64,215,800,450);
 text(s,'抓取与抬升',905,227,300,38,27,C.ink,true);
 text(s,'双侧接触确认\n托盘上散件保持自由',905,276,310,68,23,C.muted);
 text(s,'移动与让行',905,365,300,38,27,C.ink,true);
 text(s,'后退、转弯、绕障\n载荷范围参与避障判断',905,414,310,68,23,C.muted);
 text(s,'异高放置',905,505,300,38,27,C.ink,true);
 text(s,'确认台面承重后松手\n撤手并保持稳定',905,553,310,68,23,C.muted);
 s.speakerNotes.text='【建议35秒，含25秒视频】我们的任务是把带散件的托盘从源台搬到不同高度的目标台。难点贯穿全过程：抓起时需要可达性，移动时需要稳定，放下时还要确认载荷真正转移给桌面。视频是合成输入驱动的物理仿真，货物没有绑定到手上。\n\n播放25秒原速节选，依次展示抓取抬升、移动让行与放置。节选保留原视频时间标记，中间有剪辑。动态让行属于V3受控仿真，当前真人实验使用静态绕障。\n来源：simulation/research/outputs/demo_dynamic；seed401；目标台75 cm；本页视频包含3—12、22—30、51—59秒三个片段。';
}
// 03
{
 const s=slide('任务阶段驱动的共享控制','操作者给出作业意图，系统依据任务阶段协调冗余自由度与物理反馈');
 table(s,[['任务阶段','腰部与双臂分工','关键反馈'],['抓取与高度调整','腰部参与，提高可达性','接触确认与滑移'],['带载移动','保持腰部姿态，双臂补偿','载荷倾角与跟踪误差'],['放置与撤手','低速下放，完成支撑转移','桌面承重与物件留存']],64,224,1152,285,[250,500,402],25);
 text(s,'输入侧',65,552,180,36,25,C.teal,true);
 text(s,'底盘坐标重投影、刚性抓持投影、60 ms目标滤波',245,551,970,45,26);
 text(s,'执行侧',65,611,180,36,25,C.teal,true);
 text(s,'MuJoCo接触动力学与Mink逆运动学，保持相同执行器上限',245,611,970,43,24);
 s.speakerNotes.text='【建议45秒】我们的改进围绕任务阶段展开。抓取和改变高度时，允许腰部参与以获得足够工作空间；搬运时保持腰部姿态，让双臂承担主要补偿，避免求解器持续借用腰部追逐手部误差。输入侧使用底盘坐标重投影与双手刚性抓持约束，减少移动和输入扰动对抓持的影响。执行侧根据滑移、倾角和桌面承重调整夹持、速度与释放。这里的腰部保持作用于逆运动学分配，物理关节仍由限矩伺服驱动。\n\n问：为什么不一直锁腰？答：抓取及异高放置需要腰部提供可达性，所以按阶段分工；保持不是删除或焊接腰部关节。问：是否首创算法？答：基础IK、坐标变换和反馈均有既有方法，贡献是面向本任务的协调设计及消融验证。\n'+resultsSource+'\nMink：https://github.com/kevinzakka/mink；MuJoCo：https://mujoco.readthedocs.io/en/stable/overview.html';
}
// 04
{
 const s=slide('腰部稳定性改善及其精度代价','同场景、同输入处理的配对消融，每种方法8个场景种子');
 bars(s,['取消腰部保持','阶段腰部保持'],[{name:'腰部范围',values:[14.67,1.35],fill:C.teal}],64,218,550,322,18,6,'搬运阶段腰部角度范围（°）');
 bars(s,['取消腰部保持','阶段腰部保持'],[{name:'手部RMSE',values:[5.92,9.65],fill:C.gray}],668,218,548,322,12,4,'手部位置 RMSE（mm）');
 text(s,reduce+'%',64,551,270,83,65,C.teal,true);
 text(s,'腰部角度范围下降',345,569,440,42,28,C.ink,true);
 text(s,'两组均完成 8 / 8\n稳定性收益伴随跟踪误差增加',853,563,364,72,24,C.ink);
 s.speakerNotes.text='【建议45秒】为了判断腰部模块本身的作用，我们固定场景、输入处理和其他控制，只改变搬运阶段是否保持腰部姿态。八个配对场景中，腰部角度变化范围均值从14.67度降至1.35度，下降90.8%。但手部RMSE由5.92毫米增至9.65毫米，两组都完成八次任务。因此结论是减少冗余运动并保持任务完成，代价是部分手部跟踪精度，不能说所有指标都更好。\n\n指标定义：搬运阶段三个腰部关节分别求峰峰值，取最大值后按试验求均值，并非机身整体倾角。RMSE相对于无噪声意图计算，双手等权，搬运阶段10 Hz采样。比较条件tracking，shared_free_waist与shared。\n'+resultsSource;
}
// 05
{
 const s=slide('受扰输入下的任务鲁棒性','完整研究协议共120次试验，图示3种输入条件下的对照，每种方法每条件8次');
 bars(s,['无附加扰动','中等扰动','强扰动'],[
   {name:'直接目标跟踪',values:[8,0,0],fill:C.gray},
   {name:'完整共享控制',values:[8,8,8],fill:C.teal}],64,218,770,350,9,2,'完整任务成功次数 / 8',22);
 text(s,'中等扰动',891,233,310,42,26,C.ink,true);
 text(s,'6 mm 位置噪声\n80 ms 延迟\n10% 丢包',891,283,320,118,26,C.muted);
 text(s,'强扰动',891,430,310,42,26,C.ink,true);
 text(s,'12 mm / 160 ms / 20%',891,481,340,75,24,C.muted);
 text(s,'8 / 8 的 Wilson 95% 区间约为 67.6%–100%，结果限于这组受控仿真条件',64,605,1152,47,22,C.muted);
 s.speakerNotes.text='【建议40秒】接着检验输入扰动。中等条件为每轴六毫米位置噪声、八十毫秒延迟和百分之十丢包，强条件加倍。直接跟踪在受扰条件下均未完成任务，完整共享控制在各八个场景中完成任务。实验说明输入处理和协调辅助的组合对本任务有作用。它不是某款头显实测噪声，也不能由八次成功推断真实部署百分之百可靠。\n\n基线保留相同的夹持反馈、限速、阶段守卫和避障。仅腰部保持在中等扰动下同样0/8，说明收益不能全部归于腰部模块。第一轮种子300—307已用于修改支撑反馈；图表仅使用修正版新种子400—407，不把开发数据混为独立验证。\n'+resultsSource;
}
// 06
{
 const s=slide('真实Quest 3输入已接通仿真控制','WebXR手柄输入、离合标定、双臂与底盘控制、物理状态记录');
 pic(s,'quest_live.png',64,218,760,435);
 text(s,'已完成链路联调',873,229,345,42,28,C.teal,true);
 text(s,'真实双手柄驱动双臂\n夹爪与底盘响应\n输入与物理轨迹同步留存',873,291,345,143,26,C.ink);
 text(s,'真人评价进入准备阶段',873,476,345,43,27,C.ink,true);
 text(s,'已实现双模式实验入口\n自动计时与物理判定\n匿名编号、失败记录与配对分析',873,536,345,112,24,C.muted);
 s.speakerNotes.text='【建议35秒】在仿真验证之外，我们已用真实Quest 3接通控制链路，完成双手柄标定、双臂、夹爪和底盘联调。左图是实际设备输入驱动后保存的物理状态回放，不是头显画面截图，也不是合成控制器演示。当前试用用于熟悉操作和排查接口，正式用户实验还未完成。我们已搭好两模式试验入口以及自动判定和配对分析工具。\n\n来源：simulation/quest3/sessions/20261116_115607_04cd8e/session.json、raw_webxr.jsonl及states_*.npz。来源字段webxr_live，设备声明Quest3；hardware_verified:false是原记录器保守字段，不能据此声称实体机器人验证。截图是该会话最高载荷状态的重新渲染。现有交互为第三人称立体仿真，刚性双手目标与同步平行夹爪；独立腕姿态及灵巧手仍待扩展。';
}
// 07
{
 const s=slide('答辩前的真人对照实验','计划于11月17—18日采集，检验辅助控制是否改善人的操作表现');
 text(s,'5',64,216,180,108,86,C.teal,true);text(s,'位参与者',65,329,240,40,27);
 text(s,'8',430,216,180,108,86,C.teal,true);text(s,'次正式试验 / 人',431,329,350,40,27);
 text(s,'40',850,216,290,108,86,C.teal,true);text(s,'次重复测量',852,329,330,40,27);
 table(s,[['实验因素','设置'],['控制模式','标准遥操作 / 辅助遥操作'],['任务场景','60 cm / 75 cm目标台，静态绕障'],['重复与控制','每种条件2次，交错顺序，共用物理参数']],64,401,1152,190,[260,892],23);
 text(s,'按参与者配对分析成功率、限时耗时及单位试次时间成功次数，独立样本量为5人',65,629,1150,34,22,C.muted);
 s.speakerNotes.text='【建议40秒】下一步把问题落到人的使用效果。已协调五位参与者，每人比较两种控制模式、两种台面高度，各重复两次，共四十次。正式采集前统一练习并固定版本，采用交错顺序、相同物理参数和相同基础输入处理。分析以五位参与者配对，记录失败和超时，重点看成功率、限时耗时以及单位试次时间内成功次数。目前这一页是已安排的实验计划，不是完成后的用户研究结论。\n\n补充：候选单次时限240秒，先由负责人P00试跑确认，正式采集前固定。效率分母为试次计时窗口，包含停止恢复与追踪中断，不包含练习休息及场景装载。不能将40次重复测量当成40位独立用户。五人是探索性研究，后续需扩大样本。\n来源：用户2026年11月16日提供的参与者与时间安排；simulation/quest3/study.py、trial.py、analyze_study.py。';
}
// 08
{
 const s=slide('阶段成果与后续研究','以稳定控制和可复查的实验过程支撑后续示教数据采集');
 text(s,'本阶段',64,227,225,48,30,C.teal,true);
 text(s,'完成任务平台与阶段协调控制\n取得120次独立仿真与模块消融证据\n接通真实Quest输入并建立真人实验流程',322,224,875,155,30,C.ink);
 text(s,'答辩前',64,424,225,48,30,C.teal,true);
 text(s,'完成真人对照采集与结果复核\n检验辅助控制是否提高有效操作产出',322,421,875,105,29,C.ink);
 text(s,'后续',64,582,225,48,30,C.teal,true);
 text(s,'腕姿态与灵巧手扩展、参数辨识、实体机器人集成',322,579,875,58,27,C.muted);
 s.speakerNotes.text='【建议45秒】本阶段的主要成果是形成一个可以解释、比较和复查的研究原型。阶段协调显著减少了搬运中的腰部冗余运动，受扰输入实验支持完整共享控制组合的作用，同时我们保留了手部精度代价与失败记录。答辩前将集中完成真人对照，判断这些控制收益能否转化为实际操作效率。后续按原任务书补齐腕姿态、灵巧手和真实机器人参数与部署，逐步形成可用的示教采集系统。我的汇报结束，谢谢老师。\n\n本页后的补充页供问答查阅，不计入五分钟正文。前8页建议合计300秒，含第2页25秒视频。';
}
// 09
{
 const s=slide('模块消融结果','中等扰动条件，数据与主文相同，每种方法8次');
 table(s,[['方法','成功','腰部范围 / °','手部RMSE / mm','成功耗时 / s'],
 ['完整方法','8 / 8','1.35','9.65','60.95'],['取消腰部保持','8 / 8','14.67','5.92','61.43'],['取消底盘重投影','8 / 8','1.51','13.84','62.64'],['取消支撑反馈','7 / 8','1.35','9.65','62.25'],['仅腰部保持','0 / 8','2.49','18.05','—'],['直接目标跟踪','0 / 8','28.17','14.53','—']],64,218,1152,352,[300,160,220,250,222],23);
 text(s,'时间仅统计成功试验；角度与误差统计进入搬运的轨迹，包括后来失败的试验',64,600,1152,45,22,C.muted);
 s.speakerNotes.text='问：每个模块贡献是什么？答：腰部保持主要降低冗余运动；重投影主要改善误差与耗时；支撑反馈修复低台面悬停，但最终验证只从7/8到8/8，样本不足以宣称显著成功率优势。完整输入处理组合对受扰任务重要，仅保持腰部不足。不同方法失败阶段不同，因此时间只统计成功样本，不把空缺当0秒。\n'+resultsSource;
}
// 10
{
 const s=slide('成功判据与失败修复','用完整物理过程判定任务，避免仅凭最终位置或人工标签认定成功');
 pic(s,'placement.png',64,218,640,399);
 text(s,'物理成功条件',758,224,450,42,28,C.ink,true);
 text(s,'双侧抓持并抬升\n全过程无障碍碰撞\n目标台承重、松手与撤手\n散件留存并连续稳定1秒',758,288,454,175,26);
 text(s,'低台面悬停的修复',758,503,454,42,28,C.teal,true);
 text(s,'从首次接触固定目标\n改为低速下放并确认承重',758,560,454,83,25,C.muted);
 s.speakerNotes.text='问：怎么证明不是动画？答：轮地接触驱动、限矩伺服和自由负载都在动力学中推进，保存qpos、qvel、ctrl、输入与接触指标；V3另用独立脚本重建末段状态复核。回放只用于展示，重新运行才重新求解物理。问：最重要失败是什么？答：首次接触就固定手部目标，会在低台面把托盘悬在手中，桌面未真正承重。改成低速下放至承重确认，再释放。原失败轨迹保留。\n图片：demo_dynamic第5450帧保存状态。来源：simulation/research/verify.py、研究设计与来源.md。真人实验另有trial.py的全过程判据，不能混为同一数据集。';
}
// 11
{
 const s=slide('与立项目标的对应关系','已完成的证据与下一阶段待验证内容');
 table(s,[['立项目标','当前证据','后续验证'],['上肢遥操作','Quest输入、双臂映射\n同步平行夹爪','独立腕姿态\n灵巧手映射'],['上下肢协调','阶段腰部保持、底盘补偿\n接触与载荷反馈消融','感知误差与未知扰动\n真实执行器参数'],['数据采集效率','输入与物理记录工具\n真人对照实验已准备','5人探索性实验\n扩大样本与任务'],['软硬件集成','真实头显控制仿真机器人','真实机器人部署\n安全范围与参数辨识']],64,210,1152,350,[250,450,452],24);
 text(s,'当前结果支持设定任务下的系统改进；尚未形成灵巧手真机系统或模仿学习策略',64,626,1152,36,22,C.muted);
 s.speakerNotes.text='问：为什么与申报书中的灵巧手还有差距？答：中期优先建立可测量的双臂移动操作控制与验证平台，用研究平行夹爪验证抓持和支撑机制；腕姿态和灵巧手仍需推进，已纳入后续计划。问：是真实VR还是仿真？答：真实Quest控制仿真机器人，120次统计是另行开展的合成输入实验；实体机器人未完成。问：是不是只是开源拼接？答：动力学和IK使用成熟组件，新增工作是任务阶段协调、输入与物理反馈组合、失败修复和消融评价；不把基础组件声称原创。\n依据：立项申报书、当前代码和记录。';
}
// 12
{
 const s=slide('研究来源与实现分工','明确区分实际使用的基础组件与任务、交互参考');
 const refs=[
 ['MuJoCo','接触动力学、仿真状态与渲染','mujoco.readthedocs.io'],
 ['Mink','逆运动学任务、自由度约束与求解','github.com/kevinzakka/mink'],
 ['Mobile ALOHA  ·  Fu et al., 2024','移动双臂任务与示教采集参考','arXiv:2401.02117'],
 ['Open-TeleVision  ·  Cheng et al., 2024','沉浸式遥操作与运动映射参考','arXiv:2407.01512']
 ];
 refs.forEach((r,i)=>{const y=222+i*100;text(s,r[0],64,y,620,39,27,C.ink,true);text(s,r[1],64,y+43,670,36,23,C.muted);text(s,r[2],780,y+20,440,48,22,C.teal);});
 s.speakerNotes.text='本项目实际使用MuJoCo与Mink。Mobile ALOHA、Open-TeleVision作为相关工作与任务设计参考，未复现其模仿学习训练或真实机器人性能。\n参考文献：\nFu, Z., Zhao, T. Z., Finn, C. Mobile ALOHA: Learning Bimanual Mobile Manipulation with Low-Cost Whole-Body Teleoperation. 2024. https://arxiv.org/abs/2401.02117\nCheng, X., Li, J., Yang, S., Yang, G., Wang, X. Open-TeleVision: Teleoperation with Immersive Active Visual Feedback. 2024. https://arxiv.org/abs/2407.01512\nMink: https://github.com/kevinzakka/mink\nMuJoCo: https://mujoco.readthedocs.io/en/stable/overview.html\n前两篇论文题名、作者、年份已于2026年11月16日核对原始arXiv页面；本页不引用其性能数字作为本项目结果。';
}

await (await PresentationFile.exportPptx(p)).save(path.join(HERE,'candidate.pptx'));
await fs.writeFile(path.join(HERE,'deck_notes.txt'),p.slides.items.map((s,i)=>`第${i+1}页\n${s.speakerNotes.text}`).join('\n\n'));
for(let i=0;i<p.slides.items.length;i++){
 const blob=await p.export({slide:p.slides.items[i],format:'png',scale:1});
 await fs.writeFile(path.join(OUT,`slide-${String(i+1).padStart(2,'0')}.png`),new Uint8Array(await blob.arrayBuffer()));
 console.log(`Rendered slide ${i+1}`);
}
await fs.writeFile(path.join(HERE,'deck_authoring.json'),JSON.stringify({slides:p.slides.items.length,font:FONT,ratio:reduce,nativeCharts:[4,5],nativeTables:[3,7,9,11],notes:true},null,2));
console.log('Saved candidate.pptx');
