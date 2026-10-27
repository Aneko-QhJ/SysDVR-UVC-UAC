# A23执行候选：前置过期检查与EXE3保存（2026-10-15）

已把[上轮执行审查](A23_EXECUTION_READINESS.md)中的两个设备缺口落实到独立候选：
**过期后不再新开一次Process；正常导出和诊断文件保存失败都可尝试保存独立EXE3关联文件。**
主机被动等待的核心策略也已实现为C模块，但真实IOKit通知适配器和采集入口尚未接入。
这些改动没有实机运行，原SDK控制超时的根因仍未知。

[生成工具](../tools/build_a23_execution_v3_candidate.py)核验V2和执行审查封存，复制两配置
完整源码后，仅改变main、追加两个既有runtime/file编译单元、recipe头，并加入两个新头，
共六个生成文件不同。生产源码、旧device实现、全部V1/V2 wire格式、旧解析器和封存保持。
新模板位于device的ep0_execution_v3.h及runtime/file片段，只有生成树使用。

## 窗口修正与边界

等待ready和处理请求的循环都增加调用前的过期/停止检查，原调用后的检查保留。采集或
休眠返回后先检查，再处理下一轮请求。窗口仍从USB ready之前开始，0仍表示禁用；不重置
窗口，也不取消正在执行的同步调用。

十次native程序执行逐字提取候选VideoStreamThread函数体：九组30秒模型和一组禁用窗口、
显式停止模型。USB/时间/采集/日志及窗口记录接口由注入服务替代；不运行Switch线程。

| 原模型场景 | V2 | 本轮隔离候选 |
| --- | --- | --- |
| 29990ms ready、1ms处理、50ms休眠跨期 | 又开始一次Process，30042ms停止 | 不再开始，30041ms停止 |
| 1000ms ready、45000ms采集失败、16ms休眠 | 又开始一次Process，46018ms停止 | 不再开始，46017ms停止 |
| 已在处理中的45000ms同步调用 | 46000ms才停止 | 同样；没有中断调用 |
| ready到45000ms才返回 | 不处理请求 | 同样；返回后才能检查 |
| 窗口禁用 | 需要显式停止 | 三次Process后注入显式停止，正常离开循环 |

九组启用模型均没有“期限已过又开始Process”的调用。时长只是注入值和控制流结果，不是
设备实测延迟或最坏运行上界。每轮增加的时钟查询成本也未在设备上测量。

## 独立EXE3关联封装

[独立分析器](../tools/analyze_ep0_execution_v3.py)固定接受EP0EXE3/version3，内嵌的
INI1、OWN2或DIA2仍由原版本解析器独立核验。EXE3与REL2互相拒绝，不增加V2兼容回退。

| 内容 | 记录与限制 |
| --- | --- |
| 256字节头 | 布局、组件长度、三个CRC及保留字段 |
| 身份 | recipe、boot/session nonce、writer/exporter及startup writer的局部对应 |
| 本地窗口 | 精确window_start、频率、成功WaitReady返回时刻（可无）、stop及expired/requested原因 |
| 原始文件保存结果 | 调用已返回、返回值、阶段/Result、可能存在文件、读回字节数和commit确认 |
| 原始材料 | 完整OWN2或DIA2字节，即使该原始文件未成功保存 |
| 启动材料 | 最多1120字节INI1；启动身份已禁用时允许无INI1，不能伪造成功身份 |

最大EXE3为14432字节（256+1120+13056），正常OWN2最大封装为14416字节。
窗口start与TRC2 start分别记录并核对先后，stop必须等于内嵌trace freeze，频率必须一致。
ready只是设备API成功返回的本地记录，不证明主机枚举或USB总线某阶段已经完成。
stop是CandidateStop使用的冻结边界，位于末尾日志、线程join和文件保存之前；不能当作
线程已经退出或整次诊断已经完成的时间。

新文件使用独立的`/ep0-<boot+session>.execution.bin`路径，独占创建、flush、大小核对、完整
分块读回比较、Close后commit；一次尝试，不删除/覆盖/截短旧文件，不自动重试。旧REL2的
DIA2成功receipt门禁原样保留，新候选用EXE3承担本次正常/失败关联落盘。

## 实际退出分支与失败保留

76次native执行编译了候选**实际main退出分支、原normal/diagnostic文件adapter、新EXE3
文件adapter及追加runtime**。原始终结账本、最大trace/INI、时钟、FS、join和身份结果由
电脑fixture注入；Finish是否正常也由模型选择，不能把本组结果当成真实ownership验收。
本组窗口记录函数为实际代码，但窗口时间手工注入；与上组视频循环模型分别执行。

两种退出路径各38组：18种原文件情形/18种EXE3文件情形（共同成功项只算一次），再加
video join、audio join和exporter身份查询失败。具体包括正常、短读、FS打开、创建/冲突、
文件打开、部分/静默短写、损坏、flush/size/读回异常、零读/超读及commit错误。

- 正常导出后，原文件保存调用返回即构造EXE3；原文件保存失败也保留其完整内存字节和
  失败receipt。只有OWN2与EXE3均确认保存，main才关闭线程并允许原清理流程。
- 诊断路径无论DIA2文件保存成功与否，都尝试构造和保存EXE3；诊断始终保留资源，EXE3
  成功也不改变这一点。
- join或exporter身份失败仍保留资源，不取可能存活的owner信息、不打开证据文件。原
  内存启动/关联路径保持；本轮不为未知handoff强行保存EXE3。
- 原始封装必须已在内存中有效生成，context/window必须完成且双方join成功，才能生成
  EXE3。原始序列化失败、缺身份或缺停止记录仍可能没有EXE3，不能声称所有失败必有文件。
- EXE3自身保存失败保留可能存在的文件及不可变内存。它可以保存原文件的失败结果，但
  不能在自身字节内认证“本EXE3最终保存成功”。

模型原文件和EXE3磁盘内容分别保存，部分/损坏文件未被成功样例覆盖。commit错误可留下
完整可解码字节，content_verified=true仍必须保留commit_acknowledged=false。原始内存
CRC保持，重复保存/构造不再产生FS操作；短一个字节的输出拒绝且输出未改写。

## 主机等待策略已实现到哪一步

新增[a23_passive_wait_policy.h](../host/a23_passive_wait_policy.h)，是队列内使用的实际C策略：
开始→注册→排空初始iterator→等待→唯一选择→一次交接；中断/拔出/超时等进入不可重启的
停止态。已有实例、未注册先到达、模糊/零身份、反向时钟、截止时刻到达及选择后额外到达
均拒绝继续，不能自动重选。等待期限只约束交接前，交接后不能用它替代SDK传输期限。

一个native程序在ASan/UBSan下验证447组策略场景，包括101个到达时刻×4种候选数量和
43项已有实例/事件次序/终止等边界，最多一次交接。身份、时间和通知均注入，没有IOKit、
SDK、USB、票据或接收器调用；交接一个ID不代表通过真实描述符检查或取得硬件许可。

**真实通知适配器尚未实现，旧主机入口仍只查找一次。** 下一步需要把该策略接入独立
IOKit适配器，验证先注册后排空、iterator有效性、对象保留、串行回调及停止后的回调排空，
再对接一次性门禁及持久日志。不得因策略模型通过就启动当前接收器。

## 完整链接、成本与验证

两配置各13对象完整链接，26个编译单元严格格式检查通过；新recipe逐字出现在最终ELF
只读段。绑定53个源输入、原封存、实际编译器/libnx/specs及相关SDK头；ARM未执行，未打包。

| 项目 | dormant | window-30s |
| --- | --- | --- |
| text | 157090 | 157474 |
| 相对V2 text | +3352 | +3424 |
| data | 13760 | 13760 |
| BSS | 1052592 | 1052592 |
| 相对V2 BSS | +16384 | +16384 |
| 最大项目函数自身栈 | 1376 | 1376 |

最终符号核验execution_bytes=14432、execution_window=56；原exported=13040、
diagnostic_bytes=13056、session_bytes=14368、session_work=14176保持。共享已有startup
工作区在join之后使用；静态增加不能当作线程栈证明。新ELF重新核验logger GetSize失败
只Close、限长511和自身栈832；未移用旧完整formatter回放证书，完整线程/TLS/重入成本未知。

本轮87次native程序执行=10次视频循环+76次退出/文件+1次含447场景的等待策略。
新增13项检查和上轮16项回归共29项全部通过、0跳过，不宣称全库通过。最终504条封存、
V2的396条、上轮25条及历史run17条核验；53个源输入、七个生产输入、三份票据保持。
另独立解码70份EXE3并执行新decoder CLI，坏CRC/错误recipe/修复外层CRC后的内部矛盾均
拒绝，原文件commit失败不被改判成功。

- [完整候选审查](../private/analysis/A23-execution-v3-candidate-review-20261015/audit.json)
- [window-30s完整源码](../private/analysis/A23-execution-v3-candidate-review-20261015/window-30s/source/sysmodule/main.c)
- [完整ELF](../private/analysis/A23-execution-v3-candidate-review-20261015/window-30s/full.elf)
- [原文件commit失败但EXE3成功的样例](../private/analysis/A23-execution-v3-candidate-review-20261015/normal-primary-commit-error-execution-ok.execution.json)
- [独立验证](../private/analysis/A23-execution-v3-candidate-validation-20261015/validation.json)
- [29项回归的运行观察记录](../private/analysis/A23-execution-v3-candidate-validation-20261015/regression-observation.json)

```sh
PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3.12 \
  research/usb-ds-iso/tools/build_a23_execution_v3_candidate.py --output /private/tmp/a23-execution-v3-new
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=research/usb-ds-iso/tests /opt/homebrew/bin/python3.12 \
  -m unittest test_a23_execution_v3_candidate test_a23_execution_readiness -v
```

输出必须是新目录；`--native-only`可跳过ARM构建。当前三票据仍为0，无新USB/SD访问、
ARM执行、设备包或部署。下一项先完成真实主机通知适配与EXE3材料收集/比较对接，再核对
这些可达路径的线程/TLS/栈及对象生命周期；此后才形成一次诊断准备。V2比较器只接受原
OWN2/DIA2/REL2，尚不能直接输入EXE3；局部CRC、recipe、nonce也不能认证同一实机run。
