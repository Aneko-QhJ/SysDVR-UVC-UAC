# 当前132件接收器的末轮观察适配（2026-10-26）

已将[独立末轮控制器](A23_TERMINAL_OBSERVATION_WIRING.md)接到实际生成的driver、entry、coordinator和原checked export。当前132件基线、完整49..464消费历史与九个旧namespace绑定通过。最终r4在模拟IOKit/SDK操作下完成9个原生场景，正常三轮仍由原SDK、entry及导出消费者验收9216正确字节；新增消费者独立验证终态服务点。另7项拒绝检查通过。

这是实际接收器代码的离线适配验证。二进制只开放describe、check-archive、check-build；acquire-once直接exit2，生成workflow不可执行，原生正式permit初始化拒绝，Python正式issuer的fresh检查拒绝。没有可执行的硬件采集入口、启动计划或新授权。

新增3来源：tools/build_a23_live132_terminal.py、tools/audit_a23_live132_terminal.py、tools/a23_live132_terminal_consumer.py；共662来源，旧659字节保持。生成代码和冻结来源副本保存在build中；未改写旧126 build或此前sealed evidence。

## 真实代码接线

旧driver的`_complete`分支现在只返回，不再按quiet elapsed自行设置settled。第三轮保存后，coordinator只启动一次terminal worker；实际完整文件检查工作块返回、verifier归还后，复核job/permit并调用entry→driver的`terminalHealthPoll`。

该方法执行原driver健康检查，包括资源故障/interest latch、非法回调入口和存储尺寸/地址检查。不会提交ISO、BURST、STATUS或重新arm。服务采样发生在该方法返回YES之后，使用CLOCK_MONOTONIC_RAW纳秒；timer或外层循环执行本身不能算作一个成功服务点。

窗口使用唯一状态：至少250ms、每个相邻间隔最多32ms、最多512点，先检查间隔再检查elapsed。失败不重新初始化或换对象补试。达到窗口后仍运行原完整guard和轻量健康检查；控制器通过才向driver提交绑定session的终态证据，driver保存该证据并写原observation_complete事件，然后由原finalize、前后export guard和checked receipt继续收尾。

原固定三轮、每轮128项、lead32、传输期限、任意interest停止、一次性存储和完整轮间检查保持。该改变没有改善逐轮文件检查的关键路径，也没有放宽任何传输验收。

## 成功与失败证据

正常路径的SDK result/receipt、entry checkpoint、导出前后边界和单独terminal-observation.json含同一终态服务记录。新消费者先调用原SDK/entry/export校验，再核对这些记录相等、job/source/baseline/session绑定，并独立重算全部服务点。

消费者另外要求完整terminal_worker及terminal_final各一次、between_epochs两次；文件guard时间落在worker工作块内，所有完整文件检查均在服务窗口前或后，terminal_final在最后采样之后。SDK合成时钟及RAW时钟仍分开验收，不对绝对值作跨域对齐。

失败导出新增terminal-boundary.json，保留失败导出发生时的状态。若worker仍忙，边界明确pending/busy，不读取verifier；工作块返回后另写一次terminal-observation.json，保留最终归还记录。不能覆盖早先pending边界，也不能把局部窗口通过升级为整个导出成功。

外层退出门合并原轮间门和末轮门。模型关机确认可使loop finished，但末轮worker尚忙时仍不能退出。真实硬件入口关闭，因此尚未执行操作系统信号/真实关机与SDK故障交错。

## 最终r4结果

| 场景 | 结果 |
| --- | --- |
| normal | 三轮各3072正确字节，共9216；178个服务点，251.397ms，最大间隔1.657ms；原SDK/entry/导出及新消费者通过 |
| spent417-pre | 修改临时模型spent417记录，完整检查在模拟SDK打开前拒绝 |
| baseline132-pre | 修改临时132件日志原件，完整检查在模拟SDK打开前拒绝 |
| terminal-source | 末轮worker开始时修改临时新来源，窗口不启动；失败边界及最终返回记录保留 |
| terminal-stop | worker忙时退出并模型确认关机；loop虽finished，退出门仍等待实际worker返回；失败边界pending=true |
| terminal-interest | 观察阶段注入未知interest值，原故障机制停止；服务窗口失败，保留原始消息 |
| terminal-tail | 约200ms处注入80ms阻塞，实际最大间隔86.587ms，拒绝；不补开窗口 |
| terminal-old-iso | 观察阶段再交付旧ISO回调，原非法入口机制停止，不把已保存三轮升级为整体成功 |
| after-payload-bytes | 原导出后字节篡改场景拒绝；局部窗口已通过仍不代表导出成功 |

额外7项检查拒绝：错误job、把模拟材料按实测验收、导出字节篡改、旧126 builder接受新build、缺失单独终态文件、改写该文件、正式issuer在未就绪scope下fresh。最后一项仅调用只读fresh，没有initialize/prepare/issue，正式465 namespace不存在。

这里的32ms仍是本地实验阈值，不是macOS调度或USB时序保证。驱动健康方法已经接线并在模拟资源上执行；actual_sdk_poll_verified及actual_usb_verified保持false，不能称作真实SDK或实机验证。

## 尚未覆盖的收尾时间

正常记录中terminal worker完整检查477.047ms，在服务窗口开始前；terminal_final完整检查463.069ms，在最后采样后。从最后采样至控制器最终检查完成约467.755ms。随后原finalize和导出还会执行完整检查及IO。

这些时间没有计入新服务窗口，也没有被隐藏或当作合格服务。进入最终检查前有合格窗口，并不证明最终检查期间或导出之后仍持续服务。最后故障读取到SDK调用/文件写入之间的竞态、尚未交付消息、未来回调、SDK drain和存储释放/复用仍未证明。

消费者能验证提供记录的内部一致性、来源与job绑定，不能认证生产者或整段历史真实发生。离线正常结果不重判原417..464实测，亦不证明持续流。

## 开发版本及封存

- r1：生成category声明缺少nullability，在-Werror下编译拒绝，未运行fixture；保留日志，r2补充声明。
- r2：接收器编译、正常模拟导出完成，但独立SDK消费者拒绝quiet时长。原因是旧fixture每轮只推进少量合成时间，新RAW窗口等待未相应推进SDK合成时钟。
- r3：仅调整fixture的SDK合成时钟注入，按相邻RAW poll间隔加1ms推进其相对时间；不对齐绝对值、不改变原最低250ms验收。9场景与正常消费者通过。
- r4：新增失败边界/返回记录及busy期间模型关机后的退出门检查；最终9场景通过。上述失败版本均保持原样。

四版共7个原生编译作业、19个fixture进程、12个文件模式进程，均创建者直接wait。包含r1一个编译失败；r2原生正常进程exit0、消费者失败；r3/r4各9个fixture成功。模拟namespace共19，均在临时目录，不产生正式授权或采集范围。

额外验证初版把simulation=false放在临时非正式根，在构造时即被路径规则拒绝；该验证脚本失败已封存，随后r2改为仅对嵌入正式路径调用只读fresh，7项完成。未更改已通过的662来源束。

| 材料（相对private/analysis） | SHA256SUMS摘要 |
| --- | --- |
| A23-live132-terminal-review-20261026-r1 | 6835abd26b41f596a4b15725890c0fb92b5dd92128d73b4935fe190f08739408 |
| A23-live132-terminal-review-20261026-r2 | 8d663700b85d96db2cd1ee21d713181555303ac49192ed4be4261ae63ebc93db |
| A23-live132-terminal-review-20261026-r3 | 252eda8adb4bb2c8e75802d673cf83a17f9c50c0763c480997ea02ce25d8c844 |
| A23-live132-terminal-review-20261026-r4 | 50505814e014009b5284fbcd72ea8e92856c09b8ddab98270ec96794057b7798 |
| A23-live132-terminal-validation-20261026 | 6dcc8d6d7746a628a596a5cfc287b0b835c997e8efd5022d5104f2fac91acc72 |
| A23-live132-terminal-validation-20261026-r2 | 974bac645747b9727060b876eeb4a082bdcfb1327641643fa77b910a5836b8b4 |

最终来源、票据、九namespace清单及未改actual417见private/analysis/A23-live132-terminal-closeout-20261026。本轮USB/SD访问、真实SDK对象、正式新范围/namespace/授权均0；remaining=0、acquisition_enabled=false，132件快照此前已安全弹出，日志不待回收，当前现场未刷新。

下一项仅离线审查服务窗口结束到最终导出之后的故障检测边界，明确当前证据可以支持哪些结论，以及是否存在需要另立问题的实机缺口。不重复相同三轮、不继续扩张通用模型、不准备或自动执行硬件测试。465..512只是软件模型范围，未正式保留或授权。
