# 启动关联与独立保存ARM候选（2026-10-14）

在上一轮启动ARM候选的新副本中接入REL1：VideoThread在Ep0CandidateStart成功后发布既有writer/boot/session nonce，main在诊断保存返回后发布绑定该份DIA1输入的不可变receipt，再构建关联文件。原DIA1保存成功后才一次保存独立session文件；失败join、初始化失败和原DIA1保存失败都不触发REL1文件操作。旧封存、生产、三票据与格式保持，remaining=0，USB/SD访问0，根因未知。

两窗口各完整链接13对象ELF，未执行或打包。45项实际启动函数回放、20项实际main退出片段、20项文件adapter及6项容量检查共91项native通过ASan/UBSan；15项新增与415项相关Python回归无跳过。新候选包含真实服务API调用与启动hook，但电脑回放仍为服务/线程/FS模型，不能代替实机证据。

## 候选中的绑定与发布

原startup runtime函数正文保持，只在生成副本追加两个只读bridge：状态2返回当前journal和startup writer；其他状态返回NULL/0。VideoThread从已完成的startup状态2/3取得writer，调用REL1 context单次发布；复用已有两次randomGet和一次视频SID查询，不增加random/USB/SVC查询，也不因绑定拒绝改变视频循环的stop/服务Result。启动SID失败/0时仍执行原服务流程，可产生EP0-only关联，不能伪造INI1或启动writer。

新session runtime持有context、receipt、工作区及输出的静态存储；capture单次CAS→构建→release发布immutable bytes，重复调用不重置或改写。未完成启动的身份Result显示0，避免把发布中的值标记成已完成。输出工作区沿用7776byte、wire上限7968byte，无新增约8KB自动数组。

fatal路径在原Ep0StartupFatal记录并seal之后、原fatalThrow/R_THROW之前只复制启动信息；UVC初始化失败在seal后、原return 1之前同样复制。callback正文保持，不写startup/session状态，也不触发保存。部分线程启动失败时可有视频线程并发发布context，但StartupOnly不读取owner、guard、admission或sink；仍仅复制当前已发布startup前缀。真实fatal处理与进程存活未测，内存文件不保证fatal后能够回收。

## main路径与文件入口

| 路径 | REL1内存记录 | REL1文件/资源处理 |
| --- | --- | --- |
| 任一join失败 | 请求EP0但先旁路，reason=1 | 无EP0 getter/receipt/FS调用；原sleep保留 |
| exporter查询失败 | 独立startup，reason=0 | 不读EP0；无FS；原sleep保留 |
| 未启动/没有context | startup，reason=2 | 不伪造nonce/join；无关联文件 |
| owner不满足旧DIA1门槛 | startup，reason=3 | 无关联文件；保留原退出行为 |
| Finish拒绝，DIA1保存失败 | 关联诊断及该次保存返回状态 | 无第二次FS尝试；原sleep保留 |
| Finish拒绝，DIA1保存成功 | 关联startup/DIA1/admission/receipt | 独立保存REL1一次；成功/失败均sleep保留 |
| 正常Finish/正常保存成功 | startup-only，旧DIA1拒绝正常owner | 无REL1文件；原threadClose/授权/回调清理 |
| 正常保存失败 | startup-only | 无DIA1/REL1回退；原sleep保留 |
| 初始化失败/fatal | startup或metadata | 仅内存，不根据历史FS成功写卡或伪造交接 |

receipt在Ep0CandidateSaveDiagnostic返回后读取其独立bytes和SinkState，保存长度/CRC；相同DIA1重新序列化的长度/CRC必须一致。runtime仅在request、双join成功且context完整发布时取得EP0 getter；failed join/无context先旁路，未声明保存返回时不读取诊断bytes/receipt。join、身份、CRC及nonce仍为本地观察，均不认证运行时来源。

新文件入口额外检查双join、不可变REL1、context/DIA1/receipt存在及DIA1 commit已ack，防止绕过main在旧DIA1失败后开启新FS尝试。只接受本runtime生成的可信内存，入口不是任意REL1文件的语义validator。路径为`/ep0-<boot+session的64个hex字符>.session.bin`，不同于旧diagnostic/normal路径；不删除、覆写或重试。一次当前fsOpenSdCardFileSystem后exclusive create/open→write→flush→size→完整readback→close→commit，临时file/fs句柄关闭，USB/Core/线程资源保留。

独立session sink接受192..7968byte与REL1 magic，旧normal 6640/DIA1 6656byte策略不改。commit失败可保留本session文件content_verified=true、ack=false；这个最终结果只保留在独立内存SinkState。文件中的receipt描述之前的DIA1保存，不能代表REL1自己的最终保存/commit：envelope_own_save_result_recorded恒false。新增模型验证REL1 commit失败时，嵌入DIA1 ack仍true而外部REL1 ack为false，不把两次操作合并。

## 原生验证与成本边界

45项启动回放使用实际__appInit/Core/Capture/UVC/Launch函数副本；旧44项Result/资源/身份计数与journal事件逐项保持，新full-launch将__appInit、UVC初始化与两线程Launch合并，完整44/64条，无overflow/invalid。fatal路径的REL1与原INI1事件一致，启动identity失败/0/中断只输出metadata，EP0 getter为poison断言且无读取。

20项退出模型执行新候选实际main尾部与原callback，涵盖正常清理、join/exporter失败、live/unstarted、原诊断/正常保存错误、新REL1写入/collision/commit错误、startup身份禁用及绑定缺失。只有原healthy路径获得清理：2线程close、UVC/Core/sm各1；诊断及任何失败均0。shutdown harness把独立full-launch实际回放产生的44条API事件经runtime hooks再回放，复用当前journal；它未执行完整真实服务启动到shutdown，不能当成真实线程时序证据。

20项文件模型验证短读、open/create/collision/write/flush/size/read/commit错误、静默短写/损坏、零/超长读count、第二次读失败以及7968byte最大文件。最大样例额外填充startup到64条，16身份槽/128trace记录属于容量注入。receipt由实际诊断adapter返回计算，不直接注入SinkState；底层FS Result/内容及线程状态仍注入。6项独立sink容量检查在create前拒绝7969、191和错误magic，并核对旧两sink上限。所有native文件只在电脑保存。

| 编译器/链接器观察 | 默认窗口关闭 | 30秒窗口 |
| --- | ---: | ---: |
| 完整对象数 | 13 | 13 |
| 相对上一startup候选的text增量 | 9264byte | 9280byte |
| data增量 | 0 | 0 |
| BSS增量 | 16384byte | 16384byte |
| session_capture函数栈 | 352byte | 352byte |
| Ep0SessionSaveJoined函数栈 | 560byte | 560byte |

使用相同SDK/compiler与新增-fstack-usage保存逐函数报告。size中的text为工具报告的只读/代码段总计，BSS增量包括链接对齐；不是实测运行开销。项目函数最大报告1376byte，包含此前已有函数；未包含SDK完整调用链、异常路径栈、峰值/时间/实际SD持久性验证，不能据单函数数值宣称线程栈安全。

## 证据与下一步

- [关联runtime](../device/ep0_session_runtime.c)、[独立文件adapter](../device/ep0_session_file.c)、[容量策略](../device/ep0_session_sink.h)、[构建/回放工具](../tools/build_a23_session_candidate.py)、[交叉检查](../tests/test_a23_session_candidate.py)。旧[REL1原型](A23_SESSION_CORRELATION.md)和[启动ARM候选](A23_STARTUP_ARM_CANDIDATE.md)作为封存输入。
- [审查audit](../private/analysis/A23-session-candidate-review-20261014/audit.json)、[manifest](../private/analysis/A23-session-candidate-review-20261014/SHA256SUMS)：两套完整新源码/ELF/map/recipe、逐函数栈、91项native与独立解码。
- [验证摘要](../private/analysis/A23-session-candidate-validation-20261014/validation.json)、[manifest](../private/analysis/A23-session-candidate-validation-20261014/SHA256SUMS)：415项回归、生产/源码快照、票据、历史封存及文档链接。

下一步电脑审查startup/helper细阶段及64条预算、REL1输入/单次发布的并发与中断边界，以及完整栈调用链与静态成本；需要先明确初始化失败时可用服务、部分线程与借用状态，再设计任何失败保存或回滚。当前失败启动只复制内存，未新增启动独立落盘/自身save结果sidecar、回滚、自动重试或实机入口。真实DMA、join、停止延迟、运行成本、文件持久性与来源认证仍未验证，不能由本候选的拒绝或seq0推断首次SDK burst根因。
