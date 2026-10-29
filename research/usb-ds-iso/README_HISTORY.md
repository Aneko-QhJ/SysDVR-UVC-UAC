# USB 等时传输实验

> **历史时间线（2026-10-09 → 2026-10-29）。** 当前状态见 [docs/CURRENT.md](docs/CURRENT.md)，
> 入口见 [START_HERE.md](START_HERE.md)。本文只追加，不覆盖。

当前工作以 [研究规则](docs/RESEARCH_RULES.md)、[当前状态](docs/STATUS.md) 和
[进度交接](docs/PROGRESS_HANDOFF.md) 的当前说明为入口。
2026-10-27 用户要求先不用虚拟机，并简化研究约束：使用现有 Mac，按具体问题推进有限诊断，
区分探索观察和严格验收；原有 I/O 所有权、证据和适用硬件授权边界保留。
旧工具的固定门禁尚未改写，当前没有新实测额度。

本轮已完成[短包配套包与驻留入口](docs/A23_SHORT24_PACKAGE_AND_ENTRY.md)：NSP/IPS、入口、
独占写盘和失败保留均完成离线检查。[一次问题卡](docs/A23_SHORT24_ONCE_PLAN.md)已备，
下一步涉及实际部署/测试，尚无新授权。此前[SDK组件和设备关系](docs/A23_SHORT24_SDK_AND_RELATION.md)
等结果仍为离线检查，真实SDK短包能力和持续PCM未验证。
此前[控制器和完整设备ELF](docs/A23_SHORT24_OFFLINE_CANDIDATE.md)及15项检查保持。
选择依据见[PCM速率与调度缺口](docs/A23_AUDIO_CADENCE_GAP.md)。

## 历史阶段记录

以下保留各阶段的事实、限制和当时计划。其中“下一项仅……”不再自动决定当前研究路线，
后续约束以 [研究规则](docs/RESEARCH_RULES.md) 为准。

最新整轮额度租约离线候选（2026-10-27）：[单段预留与停止门](docs/A23_Q2C_EPOCH_LEASE_MODEL.md)完成，r1的38项测试通过。容量8481组合以独立186/25阈值核对，4862组形成条件符号租约；121种延迟claim中89种满足deadline100/epoch10/stop2假设，10个有界额外事件位置均完成shape。已有216条trace的情况在预留时拒绝，未模拟ISO提交或轮中半准入。
租约绑定段/snapshot/source/recipe/shape/generation，先锁完整69条/6身份加extra/stop，再复核计数和模型时间；失序、漂移、超额或未知条件停新准入，异常观察使计数不再可信，不将旧水位冒充当前计数。额度不退还、不创建第二段；模型shape回执不证明native I/O、真实commit或下一段许可。
新增3研究来源、总679；此前676与冻结Q1 receiver672保持。一个Python模型审计进程，无编译/原生fixture/SDK/USB/SD/新范围/授权。Q1 actual465/namespace465及旧actual417/九namespace、138快照保持，remaining0、acquisition_enabled=false、日志pending=false，SD最后已弹出。
真实设备grant来源/全局互斥/持久化账本/原生交还/硬截止/无损滚动均未建立，两个独立模型控制器能对相同快照各自预留，不能把hash当设备权限。下一项仅电脑定义最小设备额度回执协议与快照一致性、单次消费/拒绝失效/丢回执分类，重算新增握手本身的trace/身份/时间成本；先限单个有界段，不接设备或真实复用，不直接第四轮。封存private/analysis/A23-q2c-epoch-lease-model-closeout-20261027。以下为此前阶段历史。

最新Q2c证据预算合同（2026-10-27）：[整轮预留、停止与交接](docs/A23_Q2C_EVIDENCE_BUDGET_CONTRACT.md)完成静态核对。30项部署来源锚点、257个逐请求边界重放、514个容量算例通过，Q1 execution从138快照原件重解码与旧结果一致。区分实测66条/轮、正确9组形状且17条上界成立时的条件69、通用9×17=153；非请求/停止总量和整轮时间预算仍未建立，容量fit不授予准入。
条件追加第四轮形状时，逐请求门可先完成before STATUS到239、再处理BURST/interface0到242，随后在interface1处理前拒绝；按主机来源顺序ISO可能已pending。这只是CPU反例，原host仍三轮、没有发送第四轮。30s窗口在USB ready前启动，只在同步owner调用之间检查，不提供硬中断或调用耗时上界。
当前owner/window/build/sink一次性，freeze不排空USB，正常交接须真实join、无fault/pending及保存回读/commit后才cleanup；诊断retain不授权下一段。10条整轮/证据交接合同已保存，预留和无损滚动尚未实现。新增1研究来源、总676；此前675及冻结Q1 receiver672保持，无编译/原生fixture/SDK/USB/SD/新范围/授权。
Q1 actual465/namespace465、旧actual417/九namespace、138快照保持，remaining0、acquisition_enabled=false、日志pending=false、SD最后已弹出，现场未刷新。下一项仅电脑设计最小整轮额度租约和停止门，显式形状/段身份/额度/失效条件，未知额外流量或时间/所有权条件拒绝新准入；只支持有界证据段，不自动滚动/真实复用或改设备，不重复Q2b排列。封存private/analysis/A23-q2c-evidence-budget-closeout-20261027。以下为此前阶段历史。

最新Q2b离线模型（2026-10-26）：[有限slot/generation归属与准入](docs/A23_Q2B_GENERATION_MODEL.md)完成，最终r2的34项测试、5760种有限事件安排通过。显式交还假设下5040种排列仅42种符合独立依赖DAG并允许符号复用；交还未知的720种全部保留。旧ISO/control/handler/交还事件及同指针异代不会操作新代记录，补充的新Token搭配旧交还输入也拒绝。
模型保留有限旧代元数据、不GC/不退还历史credit，slot/元数据/证据额度耗尽即停；保存失败、队列/reader未交还、interest/stop均不释放。指针比较会误归属的逻辑反例留证，不能推成真实DMA安全。新增3研究来源，总675；冻结Q1 receiver672及build保持。r1的33项先通过，补反例后r2通过，两版各一个Python审计进程；无编译或原生fixture。
模型交还与证据提交仅是条件输入，非SDK/真实存储证明；并发交错、源关闭、自动GC、wire回绕、实际复用均未证明，未接真实入口。Q1 actual465/namespace465及旧actual417/九namespace、138快照保持；SDK/USB/SD/新范围/授权0，remaining0、acquisition_enabled=false、日志pending=false，SD最后已弹出。下一项仅离线Q2c完整请求的trace/身份/窗口预算、停止与无损证据交接合同，不继续相同成功排列、不直接第四轮或真实复用。封存private/analysis/A23-q2b-generation-model-closeout-20261026。以下为此前阶段历史。

最新Q2a交还能力表（2026-10-26）：[SDK保证、队列与复用边界](docs/A23_Q2A_SDK_HANDOFF_CAPABILITIES.md)完成本轮资料核对。11份Apple官方页面、4份当前SDK头文件、22项来源锚点形成14路径能力表；精确transactionList selector独立绑定，旧frameList/control的错误返回不回调条款不跨API推广。同步abort仅按所取消I/O范围记录保证，不视为所有closure/interest/本地队列排空；owner queue内同步调用安全性未建立。
网页工具的新页面JS/Markdown限制已记录，11份官方Markdown通过只读GET保存并校验symbol metadata及摘要。能力表明确文档保证、当前代码和局部推断；原生backing完整交还、全域drain和实际复用许可仍false，不认证Q1编译SDK。本轮无编译/fixture/SDK对象或调用/USB/SD/新范围/授权，672来源及全部actual/十namespace保持。
remaining0、acquisition_enabled=false、日志pending=false、138快照最后已弹出，现场未刷新。下一步仅离线Q2b有限slot/generation与旧回调元数据候选：交还事件必须显式标模型假设，未知交还retained并停新准入，覆盖旧/重复回调、指针别名、证据写入失败、未交还队列、满池及停止；不把模型通过当SDK证明，不直接第四轮或重测。封存private/analysis/A23-q2a-sdk-handoff-closeout-20261026。以下为此前阶段历史。

最新Q2离线合同（2026-10-26）：[所有权、复用与证据容量](docs/A23_Q2_OWNERSHIP_CONTRACT.md)完成首版来源核对。23项静态锚点、10条要求；按Q1实际生成代码确认保存后owner清自己的引用，但driver/lease仍持有三组存储，固定三轮且无rearm/复用协议。generation只能隔离逻辑身份，不能证明旧DMA访问结束；异步abort返回不等于I/O完成或回调排空。
本次原件重算trace=18+3×66=216，剩余40，同形四轮282超过256；设备19/32身份均终态但不回收槽位。当前本地macosx27.0头文件仅提供异步/同步abort及队列/销毁的局部说明，不认证Q1编译SDK或完整buffer/closure交还；首版因SDK Headers别名被严格读取器拒绝，保留后r2规范路径核对通过。
合同尚未实现或模型验证。672来源、Q1 actual465/namespace465、旧actual417/九namespace和138快照保持；本轮编译/fixture/SDK对象/USB/SD/新范围/授权均0。remaining0、acquisition_enabled=false、日志pending=false、SD最后已弹出。下一步仅电脑完成Q2a的正常完成/拒绝/异步与同步取消/destroy交还能力表；未知交还继续retained并停新准入，再决定最小slot-generation候选及反例。不直接第四轮或重测。封存private/analysis/A23-q2-ownership-contract-closeout-20261026。以下为此前阶段历史。

最新Q1实测与读卡（2026-10-26）：[新增末轮合同的首次真实结果](docs/A23_LIVE132_Q1_FIRST_RESULT.md)闭合。672来源、465/481/497三轮共9216正确字节，独立主机复算一致；253个窗口记录点覆盖250.843375ms、最大间隔1.186500ms，一次owner queue终结采样通过。轮间worker返回/复核/恢复poll各2；末轮worker返回/复核各1，completion pending=false。原生与外层exit0、前台创建者直接wait，session17544已结束。
设备唯一新增匹配216条trace，无丢失/无效，关联27条生命周期main_return/result0，窗口30.000326秒正常到期。138原件已只读回收/校验/安全弹出，四部署匹配、131旧非log不变、无新增ERPT，配置/boot2清单保持。另一个新增零trace上下文30.205337秒正常返回，具体启动归属未知，不分配给三轮。
本次新范围授权、当次关机/装卡/USB确认、实际WAITING后HOME反馈及读卡前完全关机均有直接人类回复。465..512整段耗尽，不重试/补轮/写卡；旧actual417及九namespace保持，新465 namespace17件留证。672来源未改；138成为最新基线后原132 build只能归档、current检查按current132 required拒绝。remaining0、acquisition_enabled=false、日志pending=false、SD最后已弹出，现场未刷新。
本次只证明有界历史合同；253点不是SDK回调数，窗口后的315.306ms完整检查及导出不在窗口覆盖内。持续流/drain/复用/未来无事件/旧根因仍未证，故障和人工ack路径未实测。下一项仅离线建立Q2资源所有权/取消交还/generation复用/背压恢复/证据容量合同，不直接加第四轮或重复相同实测。封存private/analysis/A23-live132-q1-first-recovered-closeout-20261026。以下为此前阶段历史。

最新Q1一次性计划（2026-10-26）：[启动计划及只读上下文](docs/A23_LIVE132_Q1_LAUNCH_PLAN.md)已完成离线审查，采用r1。launcher→Q1 workflow→generated→原生scope及成功/失败consumer一致；review exit0、缺新回执exit2，10项旧版本/范围/consumer/错误回执均在outer claim前拒绝。计划与脚本一同封存，实际执行分支未运行；异常不推断未启动或已回收，禁止重试。
默认沙箱内自检标志1/policy false；自动审批的沙箱外只读自检标志0/errno0、系统26A434/框架UUID/receiver摘要匹配，policy true；USB打开权限仍未知，未来capture必须重新前检。2个context及3个文件scope原生进程、2个CLI均创建者wait，无新编译/fixture/模型namespace。
672来源、132归档/49..464历史、旧actual417与九namespace保持。465..512仍未正式保留，新人工/actual槽及正式namespace不存在；USB/SD/真实SDK/新授权/消费0，remaining0、acquisition_enabled=false，日志pending=false、SD最后已弹出、现场未刷新。电脑准备闭合；新的Q1实测须人类明确单次最多三轮授权及当次关机/装卡/USB确认，实际WAITING后才提示开机，失败即停不重试。持续流/drain/复用仍未证。封存private/analysis/A23-live132-q1-plan-closeout-20261026。以下为此前阶段历史。

最新Q1真实入口软件准备（2026-10-26）：[新末轮合同的真实入口/消费者/失败回收](docs/A23_LIVE132_Q1_SOFTWARE_READY.md)已接线，最终选r4。新main在begin前配置完成队列，组合退出门等待worker及completion，最终状态明确历史采样而非实时健康；workflow保持先消费后Popen/前台直接wait，并新增非零退出回收。模型/SDK模式同时绑定verifier、时钟、terminal标记和SDK来源，模拟材料不能冒充实测。
新增4来源、总672，旧668及actual417/九namespace保持，132归档和49..464历史绑定。最终10原生/13模式许可拒绝/8失败语义拒绝通过，两个模型正向链各9216正确字节，五类失败独立回收。较密点暴露旧16KB通用终态编码缺口，Q1仅为2..512点终态使用有界262KB编码/读取，其他小消息上限保持；原18KB失败件确定性回放与最终19.5KB完整链通过。四版8编译/27fixture/16显式文件模式加4内部preview检查均创建者wait，两个开发断言失败及原件保留。
能力标志true仅指软件路径实现；实际采集acquisition_enabled=false、remaining0，正式465 namespace/新人工回执/actual槽均不存在，USB/SD/真实SDK/新授权范围0。没有当前沙箱外上下文、USB权限证明、一次性launcher/plan或新实测；最后真实运行仍651来源417..464，日志pending=false、SD最后已弹出、现场未刷新。下一项只离线准备并审查一次性计划及launcher→workflow→generated→native scope/consumer绑定，再按需只读核对自身上下文；不签发/消费或启动采集。封存private/analysis/A23-live132-q1-preparation-closeout-20261026。以下为此前阶段历史。

当前结论入口（2026-10-26）：[合同、证据结论与剩余问题](docs/A23_EVIDENCE_CONCLUSIONS.md)。最后真实运行为651来源的417..464三轮，主机/设备链及正常返回一致；冻结接收器为666来源，新增服务窗口/终结合同仅离线通过；研究及视图为668来源。不能混写版本或把历史通过当作现场健康/持续流/SDK drain。
本轮只核对既有sealed evidence并整理机器合同账本，无新增来源、编译、fixture、SDK、USB/SD、范围或授权。Q1为新末轮合同的真实SDK证据问题，但真实入口/消费者/一次计划尚未准备，非启动计划或许可；Q2须先建立所有权/复用/连续流合同，不直接加第四轮。actual417/九namespace及原build保持，465..512未保留，remaining0、日志pending=false、SD最后已弹出、现场未刷新。后续电脑工作优先Q1独立软件接线；不重跑已闭合通用语义模型、不自动实测。封存private/analysis/A23-evidence-conclusions-20261026。以下为此前阶段历史。

最新最终采样后语义核对（2026-10-26）：[历史采样与后续观察状态视图](docs/A23_POSTCOMPLETION_STATUS_VIEW.md)完成。只读视图要求完整归档验收，分列历史采样、后来提供的模型观察和当前设备未验证；不把裸loop.success或fact中的current字段当作实时健康。仅归档显示未提供后续观察；绑定同一记录且晚于采样的模型观察可显示已停止/完整，但is_current与硬件保证仍false。
新增2研究来源、总668，旧666和冻结receiver保持，无新候选。6原生场景、13拒绝检查及2种CLI通过，1编译/6fixture/2CLI均创建者wait；采样前故障拒绝，4个采样后的故障保留历史通过、后续模型停止，视图仍标当前设备未验证。这验证既有切点限制，不重判旧实测或取消上轮采样前四反例的修补。
原132件和49..464历史、actual417/九namespace保持；6临时模型namespace，USB/SD/真实SDK/正式范围/授权0。硬件入口关闭，465..512未正式保留，remaining0、日志pending=false、SD最后已弹出、现场未刷新。SDK drain/存储复用/持续流/生产者认证/未来无事件仍未证明。
本阶段离线语义核对闭合，后续优先整理现有合同与证据结论，或有明确需求时接入只读视图；不为追求未来无事件增添重复采样或通用模型，不准备/自动实测。最终交接private/analysis/A23-postcompletion-status-closeout-20261026。以下为此前阶段历史。

最新末端成功判定离线修补（2026-10-26）：[队列续接与终结证据](docs/A23_LIVE132_COMPLETION_OFFLINE.md)完成。接受回执后先pending且不成功，单次owner queue续接重读磁盘并采样真实entry→driver健康/最终快照，再追加绑定旧payload/接受回执摘要的终结事实；采样失败写accepted=false，不覆盖旧回执，写入失败也不授予成功。pending退出/模型关机确认不能越过新退出门。
新增3来源、总666，旧663及actual417/九namespace保持。最终r2的11原生场景、23消费者拒绝通过，旧4个晚到/排队故障反例均拒绝，正常模拟链9216正确字节；缺终结事实的旧历史接受副本不能满足新合同。来源在最后完整检查后变化仍仅有历史保证，不能称作现场新鲜。两版4编译/22fixture/8文件模式均创建者wait；r1只因receipt-tamper提前拒绝却被脚本误要求续接而失败，原样保留，接收器/消费者修补与r2相同。
新结果只说明最后采样切点和该队列前缀的一致性；采样之后、事实写入期间、其他队列或未交付入口仍可能有事件，非SDK drain/存储复用/持续流或生产者历史认证。当前132件及49..464历史绑定，硬件入口仍关闭，465..512未正式保留/授权；USB/SD/真实SDK/正式新范围/授权0，remaining0、日志pending=false、SD最后已弹出、现场未刷新。
下一项仅离线核对最终采样之后的故障在终结事实、loop状态、调用者展示和归档消费者中的表述，明确历史切点与现场状态之别；不扩张通用模型、不重开观察、不重复实测或准备硬件。最终交接private/analysis/A23-live132-completion-closeout-20261026。以下为此前阶段历史。

最新末端故障边界审查（2026-10-26）：[导出后检测切点](docs/A23_POSTEXPORT_BOUNDARY.md)完成。冻结132件接收器的最后live比较后没有再次健康读取，回执写完即置success/finished；finished后的tick不再poll。8个离线阶段注入完成：2个提前故障拒绝，4个晚到/排队SDK故障可出现loop success但后续entry stopped；返回瞬间历史副本仍可验收，探测追加停止日志后才拒绝。最后文件检查后的模型来源改写也不影响历史材料验收，不能证明现场新鲜度。
旧662及原receiver/build保持，新增1研究来源、总663；未修补或重建接收器。1次ASan/UBSan编译、8个原生诊断和16次消费者结果已封存，创建者wait；8临时模型namespace，正式新范围/授权、USB/SD/真实SDK0。既有正常样本在服务窗口后还有5次完整检查合计2280.833ms，最后检查结束距窗口2307.841ms，非连续服务/排空证据。
下一项仅离线修补已可见故障仍授予成功的末端缺口：回执后最终健康/快照采样、明确一次队列续接及pending退出门、绑定旧回执的终结/失败事实与新消费者；不改写已封存回执，不声称未来无事件/SDK drain。不扩张通用模型、不重复实测或准备硬件。actual417/九namespace保持，465..512未正式保留，remaining0、日志pending=false、SD最后已弹出、现场未刷新。最终交接private/analysis/A23-postexport-boundary-closeout-20261026。以下为此前阶段历史。

最新132件离线接收器适配（2026-10-26）：[末轮服务窗口与原导出接线](docs/A23_LIVE132_TERMINAL_OFFLINE.md)完成。实际生成driver关闭elapsed-only自动完成，worker实际返回/复核后由entry→driver健康检查完成点采样，窗口通过后再运行原完整final guard及原finalize/双边checked export。失败导出新增当时边界，worker返回后另留终态；模型关机确认不绕过busy退出门。
新增3来源、总662，旧659及actual417/九namespace保持。最终r4的9原生场景、7额外拒绝检查通过；正常模拟三轮9216正确字节，178点/251.397ms/最大间隔1.657ms，尾部86.587ms空档、interest/旧ISO、来源变化及导出篡改停止。四版7编译/19fixture/12文件模式均创建者wait；r1声明编译失败、r2合成时钟验收失败、r3通过及额外验证初版脚本错误均封存，最终选r4与验证r2。
当前132件和49..464历史已绑定，但只开放文件检查；acquire入口exit2、workflow关闭、正式permit/issuer拒绝，465..512只是未保留软件模型范围。真实IOKit/SDK操作仍由fixture模拟，USB/SD/真实SDK/正式范围/授权0，remaining0、日志pending=false、SD最后已弹出，现场未刷新。服务窗口后terminal_final同步检查463.069ms及后续导出不受窗口覆盖，SDK drain/复用/持续流/历史认证仍未证。
下一项仅离线审查窗口结束至导出后的故障检测边界及证据可支持的结论，不重复三轮、不扩张通用模型或准备硬件。最终交接private/analysis/A23-live132-terminal-closeout-20261026。以下为此前阶段历史。

最新离线末轮模型接线（2026-10-26）：[末轮观察接线与独立消费者](docs/A23_TERMINAL_OBSERVATION_WIRING.md)完成。worker完整文件校验实际返回/归还verifier后复核，再记录模型轻量poll完成点；唯一250ms窗口及32ms候选间隔由独立消费者重算，最终检查回调和通过通知后的停止仍能使接受失效。busy期间不能接受或退出，失败不重开。
新增5来源、总659，旧654及actual417/九namespace保持。最终r2的15个原生场景与35项消费者拒绝检查通过，末尾86.015ms空档拒绝。r1末尾注入组合断言失败而未留完整终态，原因未知、原样封存；r2增加断言前留证和时长反例，不能反推r1根因。两版2编译/27fixture/23文件guard调用均创建者wait，含r1一个失败进程。
这只是离线模型接线，poll/复核/最终检查仍是模型回调，未接真实接收器/SDK/原导出，非132件build；生产者历史认证、SDK drain、复用及持续流均未证明。下一项仅离线适配当前132件与真正轻量poll完成点，替换旧elapsed-only终态并接回原导出/退出门，不重复三轮或准备硬件。USB/SD/真实SDK/新范围/授权0，remaining0、日志pending=false、SD最后已弹出，现场未刷新。最终交接private/analysis/A23-terminal-observation-closeout-20261026。以下为此前阶段历史。

最新离线观察候选（2026-10-25）：[末轮队列服务证据](docs/A23_SERVICE_OBSERVATION_OFFLINE.md)完成。实际两次worker检查时长约占轮间97.8%，搬队列不移除串行成本；末轮278.471ms同步校验约占已记录282.410ms观察时长98.6%，旧日志无逐tick历史，不重判旧三轮结果。
新增3来源、总654，旧651保持。固定250ms/最大间隔32ms/最多512点的本地候选先查间隔再查elapsed，首尾长阻塞/故障/时钟/容量失败不自动重开；32ms只是实验阈值，非USB或OS保证。8个原生策略安排通过，后台两布局可完成窗口，串行长guard及尾部阻塞即使elapsed达标仍拒绝。r2仅修正本地pass输出为JSON boolean，新增正反2检查；2编译/10进程均创建者wait，真实文件guard6次（归档126临时根），无IOKit/IOUSBHost链接、USB/SD/SDK/新许可。
接收器尚未采用，非132件新build；timer服务点不等于SDK回调或排空，passed不授权释放/复用，窗口后收尾仍有同步IO。下一项仅离线实现末轮专属worker返回/复核后启动唯一窗口，记录实际poll完成点并由独立消费者重算；检查故障/退出/篡改，不重复三轮实测。actual417和九namespace保持，132快照已弹出、日志pending=false、remaining0。最终交接private/analysis/A23-service-observation-closeout-20261025。以下为此前阶段历史。

最新实测与读卡（2026-10-25）：[126件候选worker三轮结果](docs/A23_LIVE126_INTEREPOCH_FIRST_RESULT.md)闭合。417/433/449三轮共9216正确字节，URB387/403/419；独立主机验收及唯一216条device trace/STATUS/序号/URB一致，无丢失/无效，关联27条生命周期main_return/result0，30.000383秒正常到期返回。两次worker检查/返回/job复核/恢复poll均2，verifier回串行；主机和外层exit0，创建者直接wait，session18021结束。
ISO回调47.629/47.453/47.273 ms，轮间saved空档287.538/288.684 ms；不证明提速或持续流，末轮观察前guard278.471 ms仍超过250 ms。真实故障交错和operator-ack退出门本次未触发，不追认排空/复用。132原件已只读回收弹出，四部署匹配、125旧非日志不变，无新增ERPT；配置/boot2清单不变。另一个新增零trace上下文自身正常返回30.041秒，启动归属未知，不分配给本次三轮。
人类本次新授权且确认启动前关机/装卡/USB；实际WAITING后报告HOME，主机结束后明确完全关机并插卡读日志。一次三轮及整段417..464已耗尽、不重试；651来源、旧actual369/321/273与八旧namespace保持，新417 namespace17文件留证。日志pending=false、SD已弹出、remaining0，当前现场不推定。旧126 build只能归档，未来测试须132件基线及新范围/授权；下一项仅离线评估证据增量与持续采集约束，不重复相同三轮。最终交接private/analysis/A23-live126-interepoch-first-recovered-closeout-20261025。以下为此前阶段历史。

最新离线启动计划（2026-10-25）：[126件候选一次性计划](docs/A23_LIVE126_INTEREPOCH_LAUNCH_PLAN.md)已审查，使用r2。launcher→专用workflow→generated workflow→原生scope一致，review exit0，缺授权exit2；旧外层/旧generated builder、旧scope和临时错误回执4反例均在outer claim前拒绝。r1拒绝本已生效、仅准备脚本文案断言错误，原样封存；r2明确缺新回执并使用新r2人工/actual槽。
本次自进程上下文：沙箱内标志1/policy false，自动审批的沙箱外只读查询标志0/errno0、系统26A434和框架/receiver摘要匹配，policy true；USB打开权限仍未证明，未来capture须重做上下文。首次脚本名遮蔽标准inspect在import时退出，native0，改名后完成。无USB/SD/模型/编译/新授权。含r1共4个CLI子进程、6个native freshness及2个context native，均wait。
651来源、候选build、旧actual369/321/273和八namespace保持，两个计划版本人工/actual槽及正式417 namespace均不存在。417..464尚未授权/保留，日志pending=false、SD最后已弹出、remaining0。离线准备闭合；下一步须人类新单次最多三轮授权与当前完全关机/装卡/USB确认，再执行r2且实际WAITING后才提示开机。失败即停不重试；持续流/排空/复用仍未证。最终交接private/analysis/A23-live126-interepoch-plan-closeout-20261025。以下为此前阶段历史。

最新软件候选（2026-10-25）：[126件基线轮间后台校验](docs/A23_LIVE126_INTEREPOCH_READY.md)已独立编译封存。新增4来源、总651，旧647保持；126件当前快照、完整49..416历史和spent369绑定，新范围仅软件描述417..464，未保留/授权。固定三轮128项/lead32/原传输期限与任意interest停止保持，worker独占交回后复核job/permit再恢复一次poll。
新增退出门：模型关机确认使loop finished时，worker未返回仍不能退出；busy期间导出只报pending，finalize拒绝，不读verifier可变状态。12原生场景和6专项检查通过：新三轮9216正确字节独立模型接受；spent369/新来源/旧scope/错误计数/冻结入口变化拒绝，第三轮前变化停止；模型退出在worker返回后才允许。2编译、12fixture、4文件模式及Python进程均创建者wait；12临时模型授权，正式新增/USB/SD/真实SDK0。
尚未核对本轮沙箱外执行上下文或USB打开权限，持续流/排空/复用/最后检查至SDK调用竞态未证。下一项只离线准备并审查一次性计划与launcher→新工作流→新scope；实际采集需新单次最多三轮授权及就绪确认，先WAITING后开机，不自动实测。旧actual369/321/273和八namespace保持，日志pending=false、SD最后已弹出、remaining0。最终交接private/analysis/A23-live126-interepoch-preparation-closeout-20261025。以下为此前阶段历史。

最新离线接线（2026-10-25）：[两次轮间后台校验](docs/A23_INTEREPOCH_GUARD_WIRING.md)已实现隔离控制器并接入冻结三轮entry/driver的临时fixture。固定epoch1/2、单worker、group实际返回后交回verifier，复核原job/permit和边界再最多恢复一次poll；提前/重复/错误回执、退出、期限及复核后故障按预期。saved不等于存储可复用。
新增3来源，旧644保持、研究来源647；2次ASan/UBSan编译、15原生场景全部创建者wait，共51次native完整检查。正常三轮9216正确字节独立模型验收通过，来源变化和interest均只提交两轮、无第三轮。15临时模型namespace/授权；正式新增0，真实SDK/USB/SD0。首版来源集合合并脚本错误在编译前封存，r2通过。
当前仅归档120件临时接线，尚无126件正式构建/scope/硬件入口；最后检查至SDK调用竞态、同步IO、末轮观察/排空、持续流及复用未证。下一项仅固化独立生成器，绑定126件基线、49..416历史和spent369，核对必要来源/基线/scope拒绝；不重复相同三轮模型，不自动实测。旧actual369/321/273和八namespace保持，日志pending=false、SD最后已弹出、remaining0。最终交接private/analysis/A23-interepoch-guard-wiring-closeout-20261025。以下为此前阶段历史。

最新离线设计（2026-10-25）：[完整校验与回调的最小队列设计](docs/A23_GUARD_QUEUE_DESIGN.md)已形成具体状态/时序/停止条件。范围仅两次saved至下一arm边界：校验期间禁止自动tick/arm，verifier独占交出并在worker实际返回后交回，再作job/permit复核及一次性恢复；原同步STATUS/journal/保存和末轮观察边界保持，非持续流。
一个真实文件guard的原生dispatch探针完成8场景：1编译/8进程全部创建者直接wait，7次文件检查接受/1次改文件拒绝。后台校验中本地通知可处理，串行对照延后；故障/退出/旧代/重复回执/就绪后故障按预期。固定hook与握手是本地指定交错，非真实SDK延迟或性能比较。
生产entry/permit、verifier交回、最后原子检查到SDK调用窗口与缓冲区复用均未认证；saved不等于排空，lease保留六块store。下一项仅离线实现轮间worker返回后恢复一次poll的最小接线，核对独占权/错误回执/退出，不扩展通用框架，不申请硬件。644来源、actual369/321/273与八namespace保持；126件回收已弹出、日志pending=false、remaining0。封存private/analysis/A23-guard-queue-design-closeout-20261025。以下为此前阶段历史。

最新离线研究（2026-10-25）：[lstat后剩余校验与持续采集约束](docs/A23_LIVE120_RESIDUAL_GUARD.md)完成。冻结120件build在临时11根重放，2编译/2文件进程共6次完整检查通过，全部创建者直接wait；无USB/SD/真实SDK。每次4105次readFile、1861唯一路径，分组/manifest/目录重复读；canonical均值166.127 ms、SHA15.675 ms、显式lstat4.811 ms（计时重叠不可相加），不重开此前读取复用候选。
真实348次完整检查耗时合计93.938秒，非独立墙钟或设备时长；末轮观察前guard292.996 ms，超过250 ms但不证明持续处理或排空。主队列串行逐轮查后arm；固定三组/逐轮BURST/设备trace256和owner32仍限制持续流，同形四轮估算282条超容量，非第四轮实测。
644来源、actual369/321/273与八namespace保持；126回收已弹出、日志pending=false、remaining0，当前现场不重新推定。下一项仅离线设计完整校验与回调处理时序、故障传播和缓冲区复用条件，不增加轮数或自动实测。未来仍需126件基线、新范围与新授权；旧120 build归档用。封存private/analysis/A23-live120-residual-guard-closeout-20261025-r2。以下为此前阶段历史。

最新实测与读卡（2026-10-25）：[120件lstat三轮结果](docs/A23_LIVE120_LSTAT_FIRST_RESULT.md)设备核对完成。369..416共9216正确字节，与唯一216条trace/STATUS/序号/URB一致，无丢失/无效；关联27条生命周期末条main_return/result0，expired、30.000453750秒，确认本次sysmodule正常到期返回。主机exit0并直接wait，轮间saved至下一before为262/329 ms，仍非持续流或回调排空。
126原件已只读回收、哈希并安全弹出，四项部署匹配、119旧非日志不变，无新增ERPT；启动配置/boot2清单不变。另有trace0/ready_tick未记的新增上下文正常返回，但窗口elapsed68.688秒，启动归属及超时原因未知；名义30秒不保证抢占式硬截止，不补造与本次三轮的关联。旧9份ERPT和旧四条前缀保持。
r1预检查误将旧封存失败owner当成活动作业，在新卡命令前停止；核对旧终态及8条命令退出后r2只修正该判断并成功，旧owner/旧作业原样保留，无强制卸载、旧修复重试、写卡或追加USB。644来源、旧actual321/273及八个namespace保持。日志pending=false、remaining0，SD已弹出；当前设备现场状态不推定。
下一项仅离线评估剩余轮间校验与持续采集约束，不自动实测；未来需126件新基线、新范围及新授权。旧120 build只可归档验证，最终回收交接private/analysis/A23-live120-lstat-first-recovered-closeout-20261025。以下为此前阶段历史。

最新实测（2026-10-25）：[120件lstat三轮主机结果](docs/A23_LIVE120_LSTAT_FIRST_RESULT.md)通过。369..416三轮各3072正确字节，共9216，URB387/403/419；ISO回调47.501/47.042/47.224 ms，无abort、interest空前缀。真实SDK双边接受回执与独立重读一致，接收器及外层exit0、创建者直接wait，session94945已结束。
两次saved至下一before从上次492.663/438.798降到262.108/328.678 ms；BURST间隔317.456/385.854 ms，完整轮前检查258.663/325.169 ms。与lstat本地改善相容，非随机化且基线/来源/负载不同，不唯一归因；仍非持续流或回调排空。644来源、旧actual321/273与七个旧namespace保持，新369 namespace17文件留证。
本次单次许可与整段369..416已耗尽、remaining0，不重试。用户实际WAITING后报告CFW/HOME，未另重复入口名称；当前未报告测试后关机。设备日志pending=true，下一项完全关机后另行只读回收execution/生命周期/部署和报告并安全弹出，不追加USB测试。最终交接private/analysis/A23-live120-lstat-first-result-closeout-20261025。以下为此前阶段历史。

最新候选准备（2026-10-25）：[120件基线lstat三轮入口](docs/A23_LIVE120_LSTAT_READY.md)已编译封存。新增4来源、总644，旧640保持；120原件、完整49..368消费历史及七旧namespace绑定，spent321与actual321纳入保护。新范围369..416尚未保留/授权。只改目录节点类型查询，保留所有内容哈希与每轮guard；固定128项/lead32/三轮/期限/任意interest停止不变，owner/evidence未改，adapter/driver仅首序号保护更新。
16个原生场景、7专项检查通过；含正常9216字节、spent321/来源/基线/旧scope/错误许可、第三轮前变化、interest及文件节点异常拒绝。2编译、16fixture、4文件模式、1环境及2计划native检查均创建者wait。沙箱外只读context通过，但不证明USB打开权限。新description三项maximum由继承的2修正为实际3；早期binding助手层级探测失败封存，无编译/发行。
一次性计划review/缺新授权拒绝及旧workflow反例通过，actual record/新授权/正式namespace/USB/SD/真实SDK均0，remaining0。新软件候选就绪；下一项等待新一次最多三轮369..416授权与当前完全关机/SD装回/USB连接确认，再实际WAITING后提示开机CFW。旧321..368耗尽，SD最后已弹出；本地628→341 ms不是新实机结果，不追加通用框架或重跑旧入口。最终交接private/analysis/A23-live120-lstat-preparation-closeout-20261025。以下为此前阶段历史。

最新离线性能核对（2026-10-25）：[完整校验的文件属性开销](docs/A23_LIVE112_GUARD_METADATA.md)已定位并形成隔离候选。当前112件冻结build的归档目录遍历本地约352 ms，其中attributesOfItemAtPath约242 ms；SHA计算只占约4 ms。只改文件类型查询为lstat、保留全部内容/路径/manifest和每轮guard，交错ABBAAB对照完整检查均值628.042→340.839 ms（约减少45.7%），每次仍3948次readFile。
正常6进程通过；额外文件/空目录/符号链接/FIFO及基线/旧namespace额外项共6种安排、10进程按预期拒绝。三次剖析加候选合计6编译、20文件进程，18次完整检查接受/10次拒绝，全部创建者wait；没有USB/SD/真实SDK/新许可。640来源、实际321/旧273、七namespace保持，剩余0、SD最后已弹出。
这是冻结112件的临时根重放；尚无120件新build，不证明实机提速或所有并发交错等价，持续流/回调排空仍未证。下一项把lstat替换固化为独立来源并绑定120件快照、spent321，做必要接线核对；旧入口不改、不自动重测，未来硬件仍需新范围/授权/就绪。最终交接private/analysis/A23-live112-guard-metadata-closeout-20261025。以下为此前阶段历史。

最新离线核对（2026-10-25）：[ERPT与未闭合前缀](docs/A23_ERPT_PREFIX_CORRELATION.md)完成。120件快照9份ERPT（8旧1新）均2162-0004，官方符号ForcedShutdownDetected；无进程/boot/session身份，不能指认为本次sysmodule崩溃。四条quiet_enter前缀位于worker启动之前，运行窗口刻意defer记账，缺尾亦可与写失败等情况相容，不能定位中断原因。另37条上下文仅两个SET_INTERFACE的分发、无ISO，44项启动结果正常、自身27条生命周期正常到期。
本次321..368三轮216条trace/27条正常返回结论保持。固定上游提交源码已保存，但尚未认证实际Atmosphere二进制版本；不跨启动排序tick，不以随机nonce/重复线程号代替boot身份。640来源、实际321/旧273与七namespace保持；本轮USB/SD/编译/新增实测0，remaining0、SD最后已弹出。
额外记录关联到证据边界；下一项转向持续采集约束和轮间完整校验开销的离线研究，不自动重复已通过的相同三轮。未来实测需120件基线、新范围和新授权。最终证据private/analysis/A23-erpt-prefix-correlation-20261025-r3；两版分析假设失败原样保留。以下为此前阶段历史。

最新实测与读卡（2026-10-25）：[112件基线128项三轮结果](docs/A23_LIVE112_SHORT128_FIRST_RESULT.md)已完成设备核对。321..368三轮共9216正确字节；唯一新增216条trace无丢失/无效，与STATUS/序号/URB387/403/419一致。关联27条生命周期末条main_return/result0，窗口expired、30.000295573秒，确认本次sysmodule正常到期返回。主机exit0并直接wait；ISO回调47–48 ms，仍非持续流。
SD120原件只读回收并安全弹出，四项部署匹配、111旧非日志不变；640来源、旧actual273及七个namespace保持。新增一份ERPT 2162-0004未有进程/模块身份，另有37条无本次序号上下文及quiet_enter四条未闭合生命周期，归属与原因未知；不能把新增ERPT直接归为本次崩溃。启动配置/boot2清单与上次相同，不证明实际执行或入口。
日志pending=false、remaining0，本次许可耗尽，不重试、不追加USB测试。下一项仅离线核对额外记录；未来测试需120件新基线与新授权。持续流、回调排空和旧卡logo/interest根因保持未证。最终封存见private/analysis/A23-live112-short128-first-recovered-closeout-20261025。以下为此前阶段历史。

最新实测（2026-10-25）：[112件基线的128项三轮结果](docs/A23_LIVE112_SHORT128_FIRST_RESULT.md)主机核对通过。321..368三轮各3072正确字节，共9216字节，URB387/403/419；ISO提交至回调47.176/47.736/47.389 ms，原960项约152 ms，符合缩短窗口预测，但非随机化A/B。无abort、interest空前缀，真实SDK双边回执与独立重读通过，接收器exit0且创建者直接wait。
每轮raw24576/transaction3584保存完整，lead32/期限/每轮完整检查保持，轮间saved至下一before仍约493/439 ms，尚非持续流。640来源、112回收基线、完整49..320历史及旧六namespace绑定，新增321记录已消费；设备日志待只读回收。用户在WAITING后报告CFW/HOME；实际SD当前新增记录及设备生命周期仍未核对。
准备中r1启动脚本误导旧工作流，在issue前被拒绝、无job/receiver/USB；错误和失败记录保留。修正r2新增launcher/workflow/generated-workflow同版及native scope检查，旧工作流反例claim前拒绝；用户另行新授权后才启动本次唯一接收器。321..368已耗尽、remaining0，不重试。下一项完全关机后另行读卡，不追加采集。以下为此前阶段历史。

默认路径恢复与发送路径复核（2026-10-25）：用户补充默认启动路径也已不卡，并询问是否错发数据，见[首测排查](docs/A23_LIVE109_SHORT128_FIRST_RESULT.md)。此前No HOC特有改善的解释已下调，原因未知。实际run/receiver摘要与冻结源码复核一致：候选数0，未进入SDK打开、STATUS/BURST/ISO路径；等待绑定仅注册并接收IOKit通知，没有直接USB IO调用。
这不是完整总线抓包；设备trace有三次标准SET_INTERFACE，发送者未知，不能绝对排除macOS枚举/其他驱动/间接影响。新增审查见private/analysis/A23-short128-send-path-audit-default-recovered-20261025。本轮USB/SD访问0，636来源、actual273及六个namespace保持；273..320已耗尽，不自动恢复测试或改卡。以下为此前阶段历史。

No HOC观察补充（2026-10-25）：用户在No HOC建议后报告“不卡”，按上下文记录该入口不再卡logo，见[首测排查](docs/A23_LIVE109_SHORT128_FIRST_RESULT.md)。未另行提供HOME/时长/其他操作细节或新设备日志；该结果支持排查两条路径的差异，不能单归因HOC或外置secmon。原计划和“入口未知/尚未执行”等封存状态保持为历史，新增观察见private/analysis/A23-short128-nohoc-user-observation-20261025。助手本轮无USB/SD访问或配置修改，不自动恢复采集或追加启动；273..320已耗尽，128项传输仍未验证。以下为此前阶段历史。

启动入口补充确认（2026-10-25）：用户明确本次卡Nintendo Switch图标使用CFW emuMMC（默认项），见[首测排查](docs/A23_LIVE109_SHORT128_FIRST_RESULT.md)。现有No HOC入口同时省去hoc.kip与外置secmon；已备好一次无接收器、无写卡的启动路径观察计划（选择入口后最多120秒，HOME或未成功即停止，不重启补试），但尚未授权/执行，不能单归因HOC。旧封存中的“入口未知”保持为历史，补充证据见private/analysis/A23-short128-default-entry-confirmation-20261025。273..320已耗尽，零SDK/ISO，日志已回收、SD已安全弹出；卡logo根因和128项实测仍未知。以下为此前阶段历史。

最新实测与读卡（2026-10-25）：[128项首测与启动卡图标排查](docs/A23_LIVE109_SHORT128_FIRST_RESULT.md)已封存。273..320一次许可整段耗尽；实际WAITING后用户报告卡Nintendo Switch图标，主机约120.310611秒超时，未选中设备/打开SDK/提交ISO或BURST，0字节；接收器exit1且创建者直接wait，无未决资源、不重试。128项传输及48 ms预测未获验证。
SD112原件及启动配置/boot2标记已只读回收并安全弹出，四项部署匹配、108旧非日志不变，无新增crash/fatal/ERPT。唯一新增device context为56条trace，只有三次SET_INTERFACE广播、无ISO/序号；27条关联生命周期末条main_return/result0，30.000247秒正常到期返回。缺主机USB链和跨时钟对应，卡图标根因未知。
配置默认CFW emuMMC额外指定hoc.kip及外置exosphere.bin，现有No HOC入口同时省去两者；实际选择待用户确认，不能单归因HOC。下一项先排查启动路径，不自动写卡或开机对照。636来源、旧保护项及六个namespace保持，273新增15文件；日志已回收、remaining0，新112件使109件build仅可归档验证。以下为此前阶段历史。

最新实测候选（2026-10-25）：[当前109件的固定128项三轮入口](docs/A23_LIVE109_SHORT128_READY.md)已实现编译封存。636来源、109原件、49..272完整消费历史及五个旧namespace绑定，新范围仅273..320。独立owner/lease/driver/消费者固定128项，raw24576/transaction3584；lead32、原期限、每轮完整检查与任意interest停止保持。
最终34个原生场景、12专项检查及沙箱外只读context通过，含末槽127、127/129/960尺寸/计数拒绝、错误包数/回调、spent225及新增来源变化、interest失败留证。名义48 ms回调和104 ms减少仍待实测，不代表持续流。r1/r2/r3开发问题原样保留，最终选择r4；共7编译作业/102fixture均创建者wait。一次计划已review，缺授权execute拒绝；新授权/actual record/namespace/保留/USB/SD均0、remaining0。
下一项等待新一次最多三轮273..320（每轮128项）授权及当前完全关机/SD装回/USB连接确认，再先实际WAITING后提示开机CFW。225..272已耗尽、日志已回收、SD最后已弹出，不重试旧入口；当前现场状态未确认。以下为此前阶段历史。

最新离线审查（2026-10-25）：[三轮节奏与128项接收窗口](docs/A23_SHORT_WINDOW_SCOPE.md)已封存。225..272两次触发间隔586.035/671.113 ms，轮间完整检查按串行顺序推定421.497/501.355 ms；单轮ISO回调约152 ms。复核四次采集的9个已保存轮次，全部16包落在前128项，最晚槽52；32项会截掉旧113/129样本。旧177失败保持，不追认。
下一项实现独立固定128项候选（raw24576/transaction3584），同步owner/lease/driver/消费者/109件scope，保留三轮、lead32、原期限及每轮完整检查；名义回调约48 ms只是待测预测，仍非连续流。273..320仅设计，未授权/保留/实现。632来源、五个namespace及actual225保持；本轮USB/SD/SDK对象/原生编译0，225..272已耗尽、remaining0、SD已弹出。以下为此前阶段历史。

最新实测与读卡（2026-10-25）：[103件候选三轮结果](docs/A23_LIVE103_INTEREST_FIRST_RESULT.md)已完整回收核对。一次225..272三轮共9216正确字节，URB387/403/419；主机严格分析与真实SDK双边回执通过，接收器exit0并由创建者直接wait。唯一设备execution216条无丢失/无效，与三轮请求/状态/序号/URB一致；关联27条生命周期末条main_return/result0，窗口expired、30.006451秒，确认本次sysmodule正常到期返回。
SD109原件已只读回收并安全弹出，四项部署匹配、102旧非日志不变，无新增ERPT。首次卸载被loginwindow否决的r1保持；用户明确继续后r2成功，无强制卸载、写卡或追加USB测试。632来源、旧保护项和五个namespace保持。本次225..272整段耗尽、remaining0，日志不再待回收；旧103件build只可归档验证。旧177故障及interest类型未知，持续流/长期稳定/跨时钟/quiet drain尚未确认。下一项仅离线评估信息增量，未来实测需109件基线、新范围与新授权。以下为此前阶段历史。

最新实测（2026-10-25）：[103件基线的三轮结果](docs/A23_LIVE103_INTEREST_FIRST_RESULT.md)已完成主机核对。一次225..272三轮各3072正确字节，共9216字节，URB387/403/419；STATUS/ISO7、真实SDK导出前后检查与独立重读通过，接收器exit0且创建者直接wait。无abort，interest空前缀/未置故障；旧177失败及消息类型未知保持。
本次许可及整段225..272已耗尽、remaining0，不重试。632来源及四个旧namespace保持，新增225记录已留证。设备日志尚待只读回收，当前用户报告已进入CFW、无后续关机确认；下一项完全关机后读卡并核对execution/生命周期/部署，安全弹出，不追加USB测试。持续流、设备正常返回、quiet drain及整体严格成功尚未确认。以下为此前阶段历史。

最新实测候选（2026-10-24）：[当前103件的interest诊断入口](docs/A23_LIVE103_INTEREST_READY.md)已编译封存。632来源、103原件、49..224完整消费历史和四个旧namespace绑定，新范围仅225..272。任何interest仍先置故障并停止；首次失败及用户关机确认后的副本保留消息，独立收集器拒绝旧行改写/不完整成功声明。SDK准备期无driver的消息也能从provider_failure导出。
最终27个原生场景、9专项检查与沙箱外只读context通过，不代表真实SDK/USB成功。中断前r1的26/8结果保持，因准备期缺口新增r2；两版共53fixture/4编译作业均创建者wait。一次计划review/缺授权拒绝已封存，新授权/actual record/namespace/保留/USB/SD均0，remaining0。
下一项等待新单次最多三轮225..272授权及当前完全关机/SD装回/USB连接确认，再先实际WAITING后提示开机CFW；失败即停不重试，旧177..224失败不升级，SD最后已弹出。不继续扩大通用模拟框架。以下为此前阶段历史。

最新离线研究（2026-10-24）：[Interest路径与最小消息留证](docs/A23_INTEREST_TRACE.md)完成。SDK handler是generalInterest，provider对所有message立即置故障；入口只显式处理termination不能阻止其他通知触发paired_resource_fault，现有布尔值无法恢复具体类型。隔离候选先保持原故障标志，再固定保存8条原始uint32消息/入口tick，未知/零值不重标，pending/故障先于槽/overflow明确；原SDK参数仍未采集。
最终8原生场景、6专项检查通过，新增5来源，总628，旧623及actual177/四个namespace保持。4版共4编译作业/24fixture/27测试线程均wait/join，开发失败保持。USB/SD/真实SDK/新授权/保留0，177..224仍耗尽、SD已弹出，旧三轮失败不升级。
下一项仅将最小观察接入当前103件基线及新有界入口，保持任意interest停止，核对失败导出与收集器后再准备新授权；当前隔离版本没有103件scope，不可实测。以下为此前阶段历史。

最新实测与读卡（2026-10-24）：[固定三轮候选首测结果](docs/A23_LIVE97_THREE_FIRST_RESULT.md)已封存。一次许可177..224整段耗尽；前两轮177..192/193..208保存6144正确字节，第三轮未提交，因SDK interest_seen触发paired_resource_fault保护停止，整体失败、不补次。用户明确关机后接收器exit1且创建者直接wait。
SD103原件只读回收并安全弹出，四项部署匹配、96旧非日志不变。唯一关联execution169条无丢失/无效，stop_reason=expired、窗口30.003秒；27条生命周期末条main_return/result0，确认本次sysmodule正常到期退出。主机首次BURST至保护检测约1.007秒，通知类型未知，不能把30秒到期当作主机失败根因。
623来源、25保护项、旧81/113/145及新177四个namespace保持。下一项仅离线审查真实interest适配及最小消息留证；旧97件build只可归档验证，未来实测需103件基线/完整49..224历史/新范围和新授权。当前remaining0、日志不再待回收，不重试。以下为此前阶段历史。

最新实测候选（2026-10-23）：[当前97件基线的固定三轮入口](docs/A23_LIVE97_THREE_READY.md)已编译封存。623来源、97原件、49..176完整消费历史及三个旧namespace绑定，新范围仅177..224。原生48许可、三组失败owner快照、STATUS留证、双边checked export/接受回执及独立收集器均已接入；23个原生场景与7专项检查通过，沙箱外只读context通过，不代表USB打开权限。
两个构建版本共42fixture均创建者wait、4编译作业完成；旧619及保护项保持。一次启动计划已封存，缺授权execute拒绝且未创建记录；计划初版元数据保存错误原样保留。真实三轮SDK/设备窗口/持续流尚未验证，当前新授权/actual record/namespace/保留/USB/SD均0，remaining0。
下一项等待新的单次最多三轮授权及本次完全关机/SD装回/USB连接确认，再先实际WAITING后提示开机CFW；失败即停不补次，结束后另行只读回收日志。候选准备完成，不继续扩大通用模拟框架。以下为此前阶段历史。

最新离线核心（2026-10-23）：[固定三轮SDK资源与driver](docs/A23_THREE_EPOCH_OFFLINE.md)通过19个原生注入场景，正常保存9216正确字节；第三轮状态、任意旧URB复用、存储/回调/超时/保存边界按预期停止。5份重新封存坏归档拒绝，固定48模型及6单元检查通过，要求完整49..176消费历史。新增4来源，总619，旧615保持。
完整实测候选尚未就绪：当前97件scope、原生48序号许可、三组失败快照与checked export接线仍待完成。开发r1生成失败/r2原生失败均保留，最终r4通过；合计3编译作业/39原生进程均创建者wait（1失败、38 exit0）。USB/SD/真实SDK/正式保留/新授权0，177..224未保留，旧145..176耗尽/remaining0。
下一项只完成上述真实入口和证据链接线，形成可审查build后再申请新单次最多三轮授权，不扩展通用框架。以下为此前阶段历史。

最新范围审查（2026-10-23）：[固定三轮串行方案](docs/A23_THREE_EPOCH_SCOPE.md)完成静态核对。实际部署为256条trace/32累计身份/17条单请求预留/30秒窗口；同形三轮估算216条、19身份，四轮282条超trace。615来源、25保护项、三个各17文件namespace、actual145及四组155项封存材料复核一致。
主机capability/driver/失败快照/许可/验收均固定两轮；实际生成driver两处`_after[0]`第三轮必须改为前轮状态比较及全历史URB唯一性。拟177..224仅设计，未保留或授权；三轮候选尚未实现/编译，USB/SD/SDK0，旧145..176耗尽/remaining0。
下一项实现当前97件基线的独立固定三轮主机接线，只做必要新增故障检查，再申请一次最多三轮实测授权。读取复用候选保持暂停，不扩展通用框架。以下为此前阶段历史。

最新隔离候选（2026-10-23）：[单次归档读取复用](docs/A23_ARCHIVE_READ_VIEW.md)通过26个原生场景。新增4来源，总615，原611不变；每次归档新建view，保留现场来源/基线/索引/历史/job检查，结束比元数据并清空缓存。持久改写、恢复字节、换inode、增加项和跨次变化按边界拒绝；最后校验之后变化仍可能本次通过，非原子快照。
正常内容读取从3305降到1757次，但三次本地均值原版354.530 ms、候选362.857 ms，未见可确认加速，暂停此版本、不准备实机。最终26进程均wait；含URL枚举漏`._`的两版失败，共30重放进程/6编译作业全部wait，失败保持。USB/SD/真实SDK/新授权/保留0，actual145及旧证据保持。
下一项转回固定三轮串行采集范围审查：当前设备trace256条，本次150条，同形三轮估算216条、四轮282条；需核对实际部署容量、前置流量及主机固定双轮限制，再定新候选。145..176保持耗尽、SD已弹出，不扩展通用框架。以下为此前阶段历史。

最新离线分析（2026-10-23）：[双轮间隔的关键路径](docs/A23_LIVE91_CRITICAL_PATH.md)已封存。按串行调用顺序推定轮间完整检查为271号、耗时287.661 ms，与293.376 ms间隔接近；268 ms属于最终导出检查。末轮观察poll前也执行288 ms检查，250 ms窗口不证明事件队列已排空。
两个仅文件验证的原生进程共完成六次完整检查并直接wait；临时副本分段约84%花在封存build，每次共3305次readFile调用、32.1 MB返回字节。模型耗时不等于实测分段；未访问USB/SD/真实SDK、未改611来源或actual145记录，三个17文件namespace及25旧保护项保持。
下一项仅审查单次完整检查内重复读取的隔离优化，保留每轮现场变化拒绝，先明确合并读取的语义边界，再评估新实机对照。无新许可/范围，145..176保持耗尽、SD已弹出。以下为此前阶段历史。

最新实测与回收（2026-10-23）：[当前91件候选的两轮及接受回执](docs/A23_LIVE91_FIRST_RESULT.md)已核对。一次采集完成145..160和161..176，新URB387/403合计6144正确字节；四次STATUS、ISO7和真实SDK双边检查/回执通过，接收器exit0且创建者直接wait。唯一150条设备trace关联27条正常返回生命周期；SD97原件只读回收并安全弹出，四项部署匹配。
首轮保存至第二轮STATUS意图293.376 ms，上次1476.301 ms；两次触发间隔453.402 ms，上次1638.889 ms。非随机A/B，不归为唯一去重因果；持续流、长期稳定、跨时钟、quiet drain和旧81失败根因仍未验证。611来源、25旧保护项、旧81/113和新145三个17文件namespace保持。
本次许可及145..176整段已耗尽、remaining0；当前91件build只可归档验证，不能重启。下一项先从封存计时界定轮间关键路径；若实机有更多信息，再准备97件基线/新范围的有界候选和新授权，不扩大通用模拟矩阵。以下“稍后再测/尚未授权/尚未消费”等均为此前阶段历史。

用户选择（2026-10-22）：**稍后再测。** 91件/611来源候选和证据已保留；145..176未保留、人工授权和actual record未创建，remaining0。恢复测试前需新的明确授权及当前设备就绪确认，不自动启动。以下为此前准备记录。

最新实测候选（2026-10-22）：[当前91件基线的双边校验CLI](docs/A23_LIVE91_CHECKED_READY.md)已编译封存。611来源全部进入现场核对，原607保持；91原件、49..144完整消费历史和旧81/113两个namespace绑定，新范围仅145..176。正常路径导出前后完整检查及接受回执已接入真实入口，模拟/实机SDK时钟明确区分。
14原生接线+6归档拒绝场景及10项专项测试通过，沙箱外只读context通过，一次启动计划已封存。新namespace、人工授权、actual record、保留和消费均未创建；等待新的一次最多两轮授权及当前完全关机/SD装回/USB连接确认。先保持关机，接收器实际WAITING后再提示开机CFW；失败即停、不补次。
真实SDK路径及真实轮间节奏仍未验证，回执不证明最后检查后的永久新鲜度或quiet drain。当前USB/SD/真实SDK/新固件/正式消费0，旧113..144仍耗尽、日志已回收/SD已弹出。本阶段不再扩大模拟矩阵。以下为此前阶段历史。

最新离线接线（2026-10-22）：[导出双边校验与接受回执](docs/A23_CHECKED_EXPORT.md)已接入独立控制器模型。正常发布先校验并写候选载荷，再复核文件与快照后写接受回执；独立收集器同时核对两者。15个原生场景、8份坏归档及10项专项测试通过，新增6来源，总607，原601保持。
已复现getter在文件变化后仍返回旧complete，显式复核拒绝；也复现控制器成功后载荷变化，由收集器拒绝。最后一次检查后的来源变化仍可保留历史证据，但不证明当前来源新鲜、原子快照、实际SDK、wait或排空。本轮USB/SD/真实SDK/新许可或范围操作均0，113..144仍耗尽、remaining0。
当前只是历史75件描述符的临时模型：静态607来源绑定已核对，现场文件检查仍为597来源；尚未绑定当前91件和新真实scope。下一步只准备新的有界真实两轮候选及必要拒绝接线，审查完成后再取得新单次授权测真实节奏；不继续扩大通用发布框架或模拟矩阵。以下为此前阶段历史。

最新离线候选（2026-10-22）：[显式校验边界与计时](docs/A23_GUARD_CADENCE.md)完成隔离原生验证。轮间完整校验从6次降为1次；26候选+6归档+2前提+1对照共35个fixture进程通过，最终10项专项测试通过。来源、基线、历史、job及native context变化仍在下一ISO前拒绝，pending时不做完整哈希，状态getter只读内存快照。新增4来源，总601，原597保持。
每次完整校验已保存主机起止/耗时；ASan模型单次仍约0.4秒，不作为实机速度或连续流证明。真实controller的导出前后显式校验及计时凭据尚未接入，候选不可实测；下一项先完成该调用方模型与来源绑定，再准备当前91件基线下的新有界实测候选。本轮USB/SD/真实SDK/新发行保留消费均0，113..144仍耗尽、remaining0。
r1原生矩阵虽通过，但归档计数不能代表完整现场校验；r2用独立标记并补拒绝对照。专项初版1项断言误把permit stale拒绝要求为verifier失败，修正后10通过；原始版本与失败日志保留。以下为此前阶段历史。

最新实测结果（2026-10-22）：[同接口两轮成功及时间线](docs/A23_LIVE75_FIRST_RESULT.md)已核对。一次采集完成113..128和129..144，两个新URB387/403共6144正确字节，STATUS/ISO7通过，接收器exit0并由创建者直接wait。唯一150条设备trace与两轮状态/序号/URB一致，关联27条生命周期报告正常返回；SD91原件已只读回收并安全弹出。
本次许可与113..144整段耗尽、remaining0，不补次。另有一份生命周期仅4条有效记录、末条quiet_enter，无明确上下文，保留为未归因；此前81失败字段仍未知。已确认有限串行复用观察，持续流、长期稳定、跨时钟及quiet drain仍未验证。
电脑时间线显示两次触发相隔1.639秒，首轮保存至第二轮STATUS意图1.476秒；冻结调用链在轮间至少执行六次完整校验，尚无单次哈希独立计时。下一项在电脑上设计校验去重与计时，保留每轮提交前变化拒绝；以后真实节奏需新有界实验及新授权。本次旧75件候选只可归档验证，不能重启。以下未执行/未保留/待授权表述均为此前阶段历史。

最新实测候选（2026-10-22）：[当前75件基线的两轮CLI](docs/A23_LIVE75_TWO_EPOCH_READY.md)已编译封存。STATUS修正已接入真实入口，绑定597来源、75原件及旧81..112完整消费记录；只允许新范围113..144。19原生场景、6归档拒绝场景、10项专项测试通过；沙箱外context通过，USB打开及真实两轮尚未验证。
新后继namespace、正式记录、保留和消费均未创建；旧592来源和既有证据保持。一次启动脚本已准备，等待新的单次最多两轮授权及当前完全关机/装卡/USB确认，再先WAITING后提示开机。失败即停、不补次、不复用81..112；不继续扩展通用框架或模拟矩阵。以下为此前阶段历史。

最新软件修正（2026-10-22）：[STATUS计数语义与判断前留证](docs/A23_STATUS_CAPTURE_REVISION.md)的独立候选通过37个原生注入场景、3个历史成功STATUS原件回放及8项专项测试。允许终态report_count0/1和第二轮前该字段双向变化；其他URB/STATUS/ISO7及字节保持条件不变。每次STATUS先封存raw、SDK观察和失败字段，保存失败不继续。新5来源，总592，原587及实测包保持。
本轮USB/SD/真实SDK/正式发行消费均0；81..112仍耗尽，实际首轮具体失败字段仍未知，第二轮未实测。下一步将修正接入当前75件基线和新范围候选的独立实测build，完成审查后再取得新一次授权；113..144尚未保留。以下为此前阶段历史。

最新实测与回收（2026-10-22）：[首轮结果、验收缺陷和证据缺口](docs/A23_LIVE_TWO_EPOCH_FIRST_RESULT.md)已封存。一次许可及81..112整段已消费，第一轮收到81..96共3072正确字节、设备COMPLETE/URB387 status3；新入口在STATUS/URB/ISO7谓词处失败，第二轮未提交。用户确认关机后接收器exit1并由创建者直接wait；SD75原件只读回收、安全弹出，日志不再待回收，remaining0。
发现新验收要求report_count1与旧65成功STATUS原件count0不兼容；仅改该字段的合成副本通过其余冻结谓词。本次完整after STATUS未保存，具体失败字段和唯一根因未知，整体失败不追认通过。下一步电脑核对报告条数语义并补失败原件留证，再评估新的实机实验；不补测、不复用81..112，旧587来源和旧证据保持。以下准备完成/未授权/未保留描述均为该次实测前历史。

真实两轮入口准备完成（2026-10-22）：[专用CLI、一次许可与失败留证](docs/A23_LIVE_TWO_EPOCH_CLI.md)已编译封存，587来源中原579保持。新程序支持受消费回执约束的acquire-once，接现有被动等待、真实SDK provider和两轮驱动；新live scope区分旧文件检查模式，整段81..112只可发行/消费一次。
25项检查通过，含10个控制器和5个scope/许可注入场景；实际原生关机确认解析器另有6个跨语言检查。正常两轮导出通过旧严格分析器，首轮失败不提交第二轮；失败保存owner已有快照，不重读SDK活跃缓冲区。未决失败保持进程和资源，只有用户明确确认Switch完全关机后，创建者通过保留对象通知正常失败退出，不宣称排空或自动重试。
当前沙箱外只读context检查通过（OS26A434、指定框架UUID、sandbox=0），不是USB打开权限或实机成功证明。开发六版记录分别封存；最终原生/模拟检查均无真实SDK对象、USB、SD、新固件、正式发行/保留/消费。23保护项、旧账本/失败owner/state保持；65已回收/remaining0，81..112未保留。下一步取得本次最多两轮的新授权及当前设备确认，先WAITING再提示开机；不再扩展通用进程工具。以下为历史。

最新离线进度（2026-10-22）：[子进程信号恢复与就绪门槛](docs/A23_CHILD_SIGNAL_POLICY.md)完成。
新增隔离bootstrap/owner/审计/测试4来源，总计579，原575保持。child在Python启动后、导入旧取样器前恢复原父thread mask并设置INT默认Python处理/TERM默认终止；独立有界通道报告本次token+policy hash+实际mask/handler，父复核通过后才发送原取样请求。普通child不再持续继承临时SIGINT屏蔽；原已屏蔽INT/TERM保持，pending INT按原mask保留或在解除时递送。继承的TERM忽略状态在就绪前重置。
每轮20实际child均由保留Popen直接wait，含恢复前/后/就绪后信号、坏绑定/mask/handler/半写/超限/提前退出/reset失败/就绪超时/取样超时。TERM被原mask屏蔽时，超时TERM无效后KILL并wait。最终两轮40child/40wait、标准流和policy FD全关，3允许安排历史字节一致；新26+两组回归52共78测试通过，579来源搬移归一语义一致，CLI0/2/2，只读无launch/trace/mask/wait。
开发另24child：r1在第4例发生EOF与cleanup TERM竞争导致固定130期望失败（前3完整row，第4wait/close断言已通过但原始退出码未保存）；r2共20完整row、进程检查通过，因验证器重复换行失败。失败不追认通过，均封存；合计64创建者wait，其中63份原始退出码记录，1份仅有失败前断言证据。
恢复发生在解释器启动之后，不是pre-exec原子政策；同步构造异常/PID登记缺口、任意FD保存前中断及创建者整进程死亡仍未解决。23保护项、实际49/65账本及失败owner/state保持，旧228actor/14孤儿不升级；USB/SD/SDK/原生编译/部署/正式记录/保留/消费/claim全0，65已回收/remaining0，81..112未保留，生产关闭，SDK根因未知。下一步离线评估当前macOS原生spawn在执行解释器前设置mask且保持FD关闭政策的可行性，停在来源绑定的能力表与明确缺口。以下为历史。

最新离线进度（2026-10-22）：[原生PID窗口与SIGINT暂缓对照](docs/A23_SIGINT_GUARD.md)完成。
新增独立SIGINT候选/审计/测试3来源，总计575，原572来源保持。当前CPython3.13.16真实_fork_exec返回及STORE_ATTR pid处注入SIGINT：限定默认handler、单Python主线程，在构造器区域暂屏蔽SIGINT后，信号待PID登记才递送，owner可直接wait；保留并精确恢复原mask，原已屏蔽SIGINT的pending不丢弃。同步Python异常仍穿过屏蔽；原异常不被恢复mask时第二次SIGINT替换。
每轮9安排/9实际child，6由候选Popen直接wait，3真实未登记child仅由审计持有的本次_fork_exec直接返回token wait，候选仍creation_unresolved；不是从文件/消息取PID，也未向这些child PID发信号。两轮18child均创建者wait，另2直接构造probe均wait：guarded child继承SIGINT屏蔽，父mask恢复不恢复child，这是当前候选尚未修正的行为差异。全轮共20child/20wait（候选12+审计原生6+probe2）。
新26+预保留回归26+保存窗口回归26共78测试通过，575来源搬移归一语义一致，Python源码/字节码和_posixsubprocess原生镜像固定，CLI0/2/2且只读无launch/trace/mask/wait。暂缓仅覆盖指定SIGINT安排，未认证同步异常、其他原生线程/信号、任意指令或创建者整进程死亡，不是原子spawn或生产process manager。
23保护项、实际49/65账本及失败owner/state保持；旧228 actor和14孤儿回收未升级，USB/SD/SDK/原生编译/部署/正式记录/保留/消费/claim全0，65已回收/remaining0，81..112未保留，生产关闭，SDK超时根因未知。下一步离线定义并验证child初始信号mask及终止政策，不能只恢复父mask便接入生产，不接硬件。以下为历史。

最新离线进度（2026-10-22）：[启动前预保留进程对象](docs/A23_PRERETAINED_OWNER.md)完成。
新增独立候选/审计/测试3来源，总计572，原569来源保持。先Popen.__new__分配并保存到slot，再进入__init__；capture仅替换创建调用并复用原截止时间/分类/错误策略，继续从保留对象发现管道。构造器返回前后、外层STORE_ATTR child/streams及_execute_child返回后中断时，同一个对象仍可直接清理；PID已登记但_child_created标志尚false的真实opcode中断也完成wait。未进入初始化时可确认未启动；初始化已进入而PID未知时固定creation_unresolved，不调用terminate/kill/wait、不声称无child或已回收，交接暂拒绝以免降级旧类。
每轮12安排、实际8child均由owner直接wait，外层救援0；两轮16child/16wait、全部已登记管道关闭。另每轮2个无PID控制均未调用原生创建，却仍保守保留未知状态，不能说已恢复真实未登记child。新26+保存窗口回归26+owner回归26共78测试通过，572来源搬移归一语义相同，normal历史anchor/字节保持，CLI0/2/2且只读无launch/trace。
该拆分绑定当前CPython3.13.16，不是生产process manager；原生创建后到self.pid赋值之间、任意指令/信号时序、未登记原始FD、创建者或外层监督者整进程退出仍未验证。预留Python对象不能解决整进程死亡。23保护项、实际49/65账本和失败owner/state保持；旧228 actor和14孤儿wait未升级，USB/SD/SDK/原生编译/部署/正式记录/保留/消费/claim全0，65已回收/remaining0，81..112未保留，生产关闭，SDK超时根因未知。
下一步离线核对原生_fork_exec返回到PID登记与信号递送边界，或评估独立创建者；未知初始化不得恢复PID清理权限，不接生产或硬件。以下为历史。

最新离线进度（2026-10-22）：[Popen保存窗口与外层直接归属对照](docs/A23_SPAWN_BOUNDARY.md)完成。
新增隔离管道修正、双角色fixture、审计与测试4来源，总计569，原565来源保持。固定当前Python3.13.16的subprocess源码与owner字节码：构造器返回/STORE_ATTR child前中断均复现已创建child但slot为空；由外层保留的真实句柄救援wait，不把旧closed观察算已回收。STORE_ATTR streams前中断复现child已wait但2管道仍开、旧报告pending0；隔离子类从已保留child补齐管道后关闭通过。句柄保存前窗口仍未关闭。
每轮16安排=7保存窗口+9外层归属；22个child均直接wait。请求者os._exit79可发生在无owner记录/半记录/完整记录、读取中、最终校验后或worker已wait后；外层直接保留两句柄，sampler在lifeline可读时拒绝，完整wire/exit0也不提升死亡请求者。该请求者不是原sampler创建者，外层自身退出与实际创建者崩溃仍未验证；不是完整broker。
最终新26+owner回归26+deadline回归26共78测试通过，最终两轮16安排归一语义相同；CLI0/2/2且只读无launch/trace。开发另3份版本66child均wait（r2半长度测试期望写错、1项失败原样封存，不追认测试通过）；含最终两轮共110child/110wait，无新增孤儿。只复用normal历史anchor/字节；inode/时间造成的wire哈希仅在各自报告核验。
23保护项、实际49/65账本及失败owner/state保持，65已回收/remaining0，81..112未保留，USB/SD/SDK/原生编译/部署/正式记录/保留/消费/claim全0；旧228 actor和14孤儿回收未升级，生产采集关闭，SDK超时根因未知。下一步离线评估预保留进程对象/独立创建者以缩小保存前窗口，并单独验证外层监督者失联，不接生产或硬件。以下为历史。

最新离线进度（2026-10-22）：[调用者中断与运行时句柄交接](docs/A23_TERMINAL_OWNER.md)完成。
新增独立owner/审计/测试3来源，总计565，原562来源保持。调用者在capture前持有owner，共享slot保留实际Popen及未关闭管道；原始KeyboardInterrupt/SystemExit继续传播，清理各步骤的第二次异常独立记录，仍可显式finish。交接用同进程的单个holder赋值提交，实际句柄不搬出slot；提交前中断原owner有效，提交后中断可由原owner.successor找回新owner，原owner不能再清理/交接/采集。没有PID/磁盘恢复入口，清理或交接不升级失败。
每轮74安排=58历史快照+13中断+3交接；before_spawn不创建child，另73个新取样子进程均由实际创建者wait，两轮146进程/146wait。真实定时信号打断exchange两次；七个capture点、TERM/wait/close中断、双中断、SystemExit、交接前后中断均通过。交接故障仪器跳过一次实际TERM/KILL并注入wait EIO，恢复原方法后由后继owner清理；不声称真实OS无法wait。新26+deadline回归26+intake回归30共82测试通过，565来源搬移归一语义一致、历史58UUID/nonce/字节保持，CLI0/2/2且只读不launch。
证据限于句柄已保存后的指定Python检查点与一次timer；Popen创建到slot赋值的窗口、任意指令中断、owner整进程崩溃、多线程/跨进程交接、硬实时及来源/OS隔离仍未认证。旧228 actor和14孤儿wait未升级，USB/SD/SDK/部署/正式记录/保留/消费/claim全0；23保护项、实际49/65账本及失败owner/state保持，65已回收/remaining0，81..112未保留，生产采集关闭，首次SDK burst根因未知。
下一步离线核对Popen创建至句柄保存的窗口，以及owner整进程退出时的外层归属，不从journal PID恢复清理权限，不接硬件卷或生产入口。以下为历史。

最新离线进度（2026-10-22）：[取样独立期限与子进程直接wait](docs/A23_TERMINAL_DEADLINE.md)完成。
新增监督器、固定worker、故障fixture、审计与测试5来源，总计562，原557来源保持。输入/输出为非阻塞管道，共用绝对monotonic截止时间；响应≤262144字节，完整缓存仍须在期限内取得直接wait和exit0，再由父进程复核。超时/半写/超限/坏JSON/非零退出/伪造历史声明均无缓存；TERM与KILL调用、期限到期、实际wait分开记录，清理不升级失败。两次wait失败时返回实际Popen句柄供调用者继续持有（mock验证），不按journal PID处理。
每轮67安排=58历史快照+9故障；两轮134个新Python取样子进程均由创建者直接wait，10次期限失败、2次KILL升级。真实阻塞read、忽略TERM及完整响应/EOF后仍不退出均按预期拒绝。新26+取样回归30+恢复回归26共82测试通过。562来源搬移归一语义一致，58历史UUID/nonce/字节保持，CLI0/2/2；只读verify不launch、不重采样。
独立IO期限不是整个函数的硬实时返回保证：Popen创建、调度、父解析与清理仍有边界；调用者中断未验证。父审计hook不继承到子进程，来源/OS隔离/原子exec/断电/全局nonce/目录原子快照/真实SDK与时钟未认证；旧228 actor和14孤儿回收未升级。USB/SD/SDK/部署/正式记录/保留/消费/claim均0，23保护项及实际49/65账本、失败owner/state保持；65已回收/remaining0，81..112未保留，生产采集关闭。
下一步离线覆盖调用者中断及清理失败后仍持有子进程句柄的交接，不接硬件卷或生产入口。以下为历史。

最新离线进度（2026-10-21）：[临时目录只读取样入口](docs/A23_TERMINAL_INTAKE.md)完成。
新取样器/审计/测试3来源，总计557，原554来源保持。仅允许规范/private/tmp子目录，逐级O_NOFOLLOW目录句柄、固定18文件白名单；lstat普通文件后用只读/NOFOLLOW/NONBLOCK打开并fstat复核。每文件≤8192字节、每轮≤131072字节、每正文读取最多32次API调用；每文件两读，两轮cache/元数据相等，再核对目录身份链。atime排除，mode/owner/nlink/size/mtime/ctime/dev/ino纳入观察。
83安排=58历史快照+5可取样对照+20拒绝安排；63返回缓存（9关联完整/52不完整/1无残留/1冲突），20因特殊节点、symlink、替换、读内/跨轮变化、大小/预算或读错误拒绝，拒绝无部分缓存。两轮83安排均通过；新30+恢复回归26+发布回归26共82测试通过。只读flags/无write-link-unlink-fsync、读错误FD清理、短读/EINTR及真实close后抛错均测试；只读verify不重采样、不launch。
557来源搬移保留58历史UUID/nonce/输入字节，83安排归一语义一致，真实inode/时间仅作为各自报告不跨位置比较；CLI0/2/2且只读。两次166个离线目录case上下文，另4单元目录；新fixture进程/现场job/进程查询0。audit fault hook只改临时测试目录，特殊节点不进入封存包。
最后校验后的变更反例两次均成立：返回的旧缓存仍可关联，而现场target随后已不同；atomic_directory_snapshot_verified始终false。取样成功不等于分类无冲突，当前元数据不恢复历史硬链接/同步/实际退出/wait，所有任务/清理/重启/物理权限false。调用次数上限不是独立时间期限；OS隔离、来源、原子exec、断电及全局nonce未认证，旧228 actor和旧14孤儿回收未升级。
原554来源、23保护项、实际49/65账本及失败owner/state保持；65已回收/remaining0，81..112未正式保留。USB/SD/context刷新/driver时钟/原生编译/真实SDK/部署/正式记录/保留/消费/claim均0，生产采集关闭。
下一步离线覆盖取样阻塞与独立期限；如用子进程，调用者必须直接持有句柄并分别记录期限到期、终止与wait，不能按journal PID清理或把超时升级为成功/已回收。不接硬件卷或生产入口。以下为历史。

最新离线进度（2026-10-21）：[纯磁盘缓存只读恢复分类](docs/A23_TERMINAL_RECOVERY.md)完成。
新纯消费者/审计/测试3来源，总计554，原551来源保持。本轮只复用58份封存快照；外部anchor绑定job/nonce/terminal/failure/owned-plan摘要与两actor PID声明，输入仅允许18个本地发布文件，不接收场景、事件、退出通知或内层观察。不创建新fixture/job，不查询/清理/重启进程；publisher/recover拒绝入口、actor/guardian及生产代码保持。
87安排=58历史快照+5边界对照+24冲突坏件，结果1无残留/56不完整/6commit字节关联完整/24冲突。原始58快照为6关联完整、52不完整；角色级64关联/52不完整。所有结果task_complete和权限false，目录同步/实际退出/wait/硬链接身份均unknown，normal原wait历史也不从磁盘恢复。无法解析part仅记opaque未核实，不把不完整分类当作合法发布前缀认证。
新26+commit回归30+发布回归26共82测试通过；纯消费者在open/io.open/os.open/stat/waitpid/kill/Popen阻断下完成。554来源搬移输入锚点/文件逐字节相同，历史UUID/nonce保持，87安排语义一致，verify/exercise阻断Popen，CLI0/2/2且只读。回归另5个文件IO单元目录，无新fixture进程、现场job、进程查询、原生或SDK执行。
来源仍未认证：协调改写anchor PID声明与use/exit/commit再重pin，可归为commit关联完整，但来源/任务/wait/所有物理权限不升级。外部pin是调用方信任输入，缓存不是原子现场目录快照；旧228 actor和旧14孤儿的未认证回收结论保持。
原551来源、23保护项、实际49/65账本及失败owner/state保持；65已回收/remaining0，81..112未正式保留。USB/SD/context刷新/driver时钟/原生编译/真实SDK/部署/正式记录/保留/消费/claim均0，生产采集关闭。
下一步离线设计固定白名单的只读目录取样入口，拒绝symlink/非普通文件，限制读取并检测前后身份/内容变化；仍不声称原子目录快照，不读取硬件卷，不重发布、清理、重启或创建现场票据。以下为历史。

最新离线进度（2026-10-21）：[局部终态目录同步与最终commit候选](docs/A23_TERMINAL_COMMIT.md)完成。
新actor+发布IO+纯消费者+审计+测试5来源，总计551，原546来源保持。协议独占use标记并同步文件/目录→记录.part分段写/file fsync→不可覆盖link发布→目录fsync→最后commit清单同协议发布；commit绑定job/nonce/plan/role/PID和记录摘要，process_wait_verified固定false。冻结状态writer AST、requester/worker/guardian仪器与生产入口均保持。
82安排=58进程（2对照+2角色×28窗口）+24坏件，仅normal完成。use窗口created/half/file_sync/dir_sync；3记录及commit窗口before/created/half/file_sync/link/dir_sync。新30+发布回归26+状态回归26共82测试通过；5单元目录用mock覆盖文件/目录同步错误、真实已有final的link拒绝、短写/非法进展；非EPIPE IO错误未做真实进程注入。独立事件管道在等待guardian时并行读取，纯消费open/io.open/waitpid观察0，551来源搬移独立UUID/nonce/PID语义一致，CLI0/2/2且只读不launch。
两次348进程：116guardian均wait、232actor有NOTE_EXIT/ECHILD，仅4actor由创建者已wait，228终止但回收未认证。112中断/1832事件；选中commit12份有效，8份有目录同步观察，4份仅link可见，另4次commit目录同步后仍中断，所有故障拒绝。73/91均不冒认未wait的实际OS状态；旧14孤儿回收保持未认证，全局orphan_reaping_verified=false。
116guardian-use/attempt/单次accept保持，guardian重试/恢复各拒绝116；232local-use（4空/4半写/224完整）仍拒绝本地重试/恢复各232。648对本地part/final和2对receipt/part核对真实同inode/nlink2，封存普通副本；actor PID信号0，harness失败0，另5仅单元目录无额外进程。
目录fsync调用顺序和进程退出后文件视图不等于断电认证；完整commit不证明wait、来源、完整进程树或生产许可。witness仍假定存活，外层guardian PID声明协调伪造仍可模型完成，所有物理授权false；原子exec/OS隔离/全局nonce/SDK/时钟域/quiet drain/permit未认证。
原546来源、23保护项、实际49/65账本及失败owner/state保持；65已回收/remaining0，81..112未正式保留。USB/SD/context刷新/driver时钟/原生编译/真实SDK/部署/正式记录/保留/消费/claim均0，生产采集关闭。
下一步离线设计纯磁盘缓存的只读恢复分类，区分残留不完整/commit关联完整/冲突；没有独立事件时，历史目录同步与wait必须保持未知，不重新发布、清理、重启或创建现场票据。以下为历史。

最新离线进度（2026-10-21）：[局部终态发布中断对照](docs/A23_TERMINAL_PUBLICATION.md)完成。
新增actor/guardian仪器、纯消费者、审计和测试共5来源，总计546，原541来源不变。新仪器保持状态writer算法AST，独立事件管道报告目标字节/写入窗口，仅actor固定点os._exit(73)，无actor PID信号；原状态候选/requester/worker/guardian仪器/生产入口均未改。
50安排=26进程（normal、guardian-loss、2角色×3文件×4窗口）+24坏件，仅normal完成；原始frame/transport/exit文件在创建前、空文件、半写、文件fsync后中断。纯消费者核对独立事件和实际文件前缀，未来文件缺失保持，不用事件中目标字节补造终态。新26+状态回归26+guardian-failure回归22共74测试通过，纯消费open/io.open/waitpid观察0，546来源搬移独立UUID/nonce/PID语义一致，CLI0/2/2且只读不launch。
两次完整回放共156进程：52guardian均wait、104actor有NOTE_EXIT/ECHILD，4actor由创建者已wait，100仅确认终止/回收未认证。48次发布中断、344事件；选中exit文件36缺失/4空/4半写/8完整，其中4完整exit已fsync后仍中断，局部91声明不等于实际wait码；73仅为源码与事件声明，未认证中断actor实际wait码。
前两次仅normal的harness错误r1(bytes解析)/r2(事件变量覆盖)已封存，另6进程完整记账：含两次失败运行本轮共162进程、54guardian wait、8actor创建者wait、保存106份actor退出观察，100actor回收未认证。失败事件流未保留，不追认其50安排通过；r1/r2 normal文件快照另存，未改原失败包。两次成功回放52use/attempt/accept保持，重试/恢复各拒绝52，2硬链接receipt对；失败normal另2对。
旧14孤儿回收仍未认证，orphan_reaping_verified=false。完整本地终态不是wait/来源/生产许可；尚无目录fsync、最后提交标记、断电持久性、完整进程树或witness故障证明。外层guardian PID声明协调伪造仍可模型完成，物理授权全false。
原541来源、23保护项、实际49/65账本与失败owner/state保持；65已回收/remaining0，81..112未正式保留。USB/SD/context刷新/driver时钟/原生编译/真实SDK/部署/正式记录/保留/消费/claim均0，生产采集关闭。
下一步离线设计局部终态发布协议候选，补充目录同步与最后提交标记的失败窗口；完整记录仍不能代替wait，不从journal PID清理、不自动重启、不接生产。以下为历史。

最新离线进度（2026-10-21）：[状态管道显式失败候选](docs/A23_STATUS_TRANSPORT.md)完成。
新Python包装仅拦截actor状态FD写入：有界补齐短写，EINTR最多16次总调用，EPIPE一次失败即停；保存原始失败frame及绑定transport记录，以91/StatusTransportFailure记录局部终态，不再次向断管回报。冻结requester/worker/guardian/原观察包装、原537来源均保持；临时副本actor槽位明确替换为新候选，并记录摘要别名，不改生产入口。
53安排=13进程+40坏件，仅normal完成；18次/轮EPIPE均写1次、提交0，正常actor不带失败材料。新26+guardian-failure回归22+guardian-owned回归22共70测试通过；短写/EINTR/零或BOOL/越界进展/其他IO错误/预算用mock验证。541来源搬移独立UUID/nonce/PID语义一致，CLI0/2/2且只读不launch，纯消费open/io.open/waitpid观察0。
两次共26guardian+46actor=72进程；26guardian被witness直接wait。46actor有NOTE_EXIT/ECHILD，10由创建者已wait，36只确认终止/回收未认证，局部记录36次91/10次0。36原始frame区分request/rejected/ready/end，最早窗口不必等到end即失败。原始候选记录先严格校验，再仅把91/StatusTransportFailure机械投影为旧1/BrokenPipeError复用旧消费者；不改证据、不提升任务、不改变wait结论。
26use/22attempt保持，重试/恢复各拒绝26次，16单次accept，10实际receipt/part同inode；actor PID信号0。旧14孤儿回收仍未认证，全局orphan_reaping_verified=false；来源、完整进程树、witness故障、原子exec/OS隔离/断电/全局nonce/真实SDK/时钟域/quiet drain/生产permit未认证，协调伪造外层guardian PID声明仍可模型完成，所有物理授权false。
原537来源与23保护项、实际49/65账本和失败owner/state保持；65已回收/remaining0，81..112未正式保留，USB/SD/context刷新/driver时钟/原生编译/真实SDK/部署/正式记录/保留/消费/claim均0，生产采集关闭。
下一步离线覆盖局部终态文件缺失、半写及发布时actor中断；候选文件逐个fsync但未同步目录，尚无中断发布/断电持久性证明。继续保留失败证据并拒绝恢复，不把本地报告/NOTE_EXIT视为wait，不按journal PID清理或接生产。以下为历史。

最新离线进度（2026-10-21）：[guardian自身中断与管道失效对照](docs/A23_GUARDIAN_FAILURE.md)完成。
外层witness只直接创建/持有guardian句柄；冻结guardian仍直接创建requester和worker。witness在固定暂停点注册macOS NOTE_EXIT后终止guardian，不持有actor控制/状态管道端，不按actor/journal PID发信号；独立包装只记录actor局部异常与退出码。
33安排=13进程场景+20缓存坏件，仅normal允许完成；Popen前后、owner缺失/半写/同步、gate放行前、4个child检查点、worker已wait及双方已wait均覆盖。guardian死后actor向断开的状态管道回报触发BrokenPipeError；冻结actor原字节未修复。完整receipt或双方已wait仍不升级失败任务。
新22+guardian-owned回归22+父中断回归20共64测试通过。537来源搬移独立UUID/nonce/PID语义一致，CLI0/2/2且只读不launch，纯消费open/io.open/waitpid观察0。两次26guardian均被witness直接wait，46actor有NOTE_EXIT/ECHILD；其中10由原guardian已wait，36仅确认终止/未认证回收，actor报告10次0/36次1，guardian24次SIGKILL/2次0。旧14孤儿回收仍未认证，全局orphan_reaping_verified=false。
26guardian-use/22attempt保持，重试/恢复各拒绝26次，16单次accept，10实际receipt/part同inode双链接；actor PID信号0。witness PID协调伪造仍可模型完成，来源/OS隔离/原子exec/断电/全局nonce/真实SDK/时钟域/quiet drain/生产permit未认证。外层witness仍假定存活；固定点SIGKILL不等于任意崩溃或完整进程树回收。
原532来源、生产collector/permit/原launcher/driver/桥/C及23保护项、实际49/65账本和失败owner/state保持；65已回收/remaining0，81..112未正式保留。USB/SD/context刷新/driver时钟/原生编译/真实SDK/部署/正式记录/保留/消费/claim均0，生产采集关闭。
下一步离线设计断管回报的显式失败路径，对比保留原始故障证据与候选本地终态；不得把本地退出/NOTE_EXIT当作wait，也不从journal PID恢复清理权限或接入生产。以下为历史。

最新离线进度（2026-10-21）：[guardian直接拥有worker的离线对照](docs/A23_GUARDIAN_OWNED.md)完成。
新guardian直接Popen并保留requester和worker句柄，worker句柄早于owner发布；parent仅核对job/nonce/plan/launch/integrated-plan/PID绑定的一次handoff，不创建或wait worker。复用冻结worker包装/内部fixture/发布IO原字节；owned-plan提供同字节crash-plan兼容别名。
36安排=16进程/协议+20坏件，仅normal允许模型完成；无请求/已退出请求不启动worker，owner缺失/半写/父中断时仍由guardian直接wait，坏job/nonce/重复handoff拒绝，清理不提升失败资格。新22+父中断回归20+集成回归22共64测试无跳过通过，纯消费open/io.open/waitpid观察0，parent AST无worker创建/wait/signal。
532来源搬移独立UUID/nonce/PID语义一致，CLI0/2/2且只读不launch。两次32requester+28worker共60进程均guardian实际wait；4份owner缺失/半写也已wait，18份accept均单次。32guardian-use/28attempt保持，重试/恢复各拒绝32次，8实际receipt/part同inode核对，封存普通文件，journal PID信号0；另4单元目录/2模拟争用线程无额外实际worker。
这是新拓扑新进程的直接wait证据，不能追认旧14个worker已回收；orphan_reaping_verified保持false，guardian_worker_wait_model_valid仅当前模型。guardian自身中断尚未测，审计小报告communicate(timeout3)不是生产broker；来源/原子exec输入/OS隔离/断电/全局nonce/真实SDK/时钟域/quiet drain/生产permit未认证，协调重pin外层伪造仍可模型完成、授权全false。
原528来源、生产collector/permit/原launcher/driver/桥/C及23保护项、实际49/65账本和失败owner/state保持；65已回收/remaining0，81..112未正式保留，USB/SD/context刷新/driver时钟/原生编译/真实SDK/部署/正式记录保留/消费/claim均0，生产采集关闭。
下一步离线覆盖guardian自身中断的管道失效与恢复拒绝，明确外层生命周期依赖；继续区分终止/wait，不重建journal PID清理权限，不接生产broker或硬件。以下为历史。

最新离线进度（2026-10-21）：[父进程中断、worker归属与退出观察](docs/A23_PARENT_CRASH.md)完成。
冻结launcher/worker在新副本中用固定Popen包装与record hook注入父中断；guardian直接拥有parent，worker仍由parent创建，先管道ready/gate再运行，parent lifeline EOF→86中止，guardian gate EOF→87拒绝；macOS kqueue NOTE_EXIT只读观察，不按journal PID向worker发信号。
27安排=11父进程场景+16坏件，仅normal允许外层完成；复现Popen成功但owner缺失/半写时worker已存在，两份回放共4次。内层完整报告且原parent已wait的after-parent-report，仍因外层退出79拒绝。新20+集成回归22+发布回归22共64测试无跳过通过，纯消费者open/io.open/waitpid观察0。
528来源搬移以独立UUID/nonce/PID回放，确定性语义一致，CLI0/2/2且只读不launch。两次22parent均wait，20worker均有绑定end与NOTE_EXIT；其中6由原parent回收，14在parent中断后终止但不声明已回收，guardian waitpid均ECHILD/worker waits0，orphan_reaping_verified始终false。parent退出10x79/8xSIGKILL/4x0，worker报告14x86/2x87/4x0。
22use/attempt保持，重试/恢复各拒绝22次，8实际receipt/part同inode核对，封存普通副本；guardian worker PID信号0，另6单元目录/2模拟争用线程，无额外实际worker。固定gate/检查点不证明任意指令崩溃、所有后代/孤儿回收、来源/原子exec输入/断电/全局nonce/SDK/时钟域/quiet drain/生产permit；协调重pin外层伪造仍可模型完成，所有授权false。
原523来源、生产collector/permit/原launcher/driver/桥/C及23保护项、实际49/65账本和失败owner/state保持；65已回收/remaining0，81..112未正式保留，USB/SD/context刷新/driver时钟/原生编译/真实SDK/部署/正式发行保留/消费/claim均0，生产采集关闭。
下一步做guardian直接拥有并wait worker的离线对照，让parent只接受绑定交接；保留缺记录反例，拒绝journal PID清理和自动重启，不接生产broker或硬件。以下为历史。

最新离线进度（2026-10-21）：[同步发布接入新fixture launcher副本](docs/A23_INTEGRATED_FIXTURE.md)完成。
新父进程独占use并同步→检查plan/worker/库/输入→attempt文件/job/父目录同步→launch.ready→固定Popen；child验证父前缀和use，只发布材料/receipt；同一纯消费者联查父同步、绑定、supervisor和清理。旧launcher/生产collector/permit及driver/桥/C未改。
51安排=31launch+20坏件，仅normal允许集成模型完成；3前置同步失败不启动worker。10子中断/4子IO错误、退出7/超时/缺stdout/stderr、父read/close/wait及4组合失败拒绝。新22+发布回归22+绑定回归20共64测试无跳过通过，消费者open/io.open观察0，两个新调用者仅1次模拟spawn且trace不重复，空use不写trace。
523来源搬移以独立UUID/nonce回放，确定性准入/拒绝/恢复一致，CLI0/2/2且只读不launch；原始trace末端完整性另存、该调度字段不纳入语义相等。两次54真实Python worker，候选回收50/harness救援4，资源救援10，均不升级失败资格。62审计fixture目录/62use与attempt，重试和恢复各拒绝62次；32实际receipt/part同inode核对，封存复制普通文件。
仅接新离线副本，生产未集成；无fork后代/原生编译/完整driver/真实SDK。另7单元目录、共4模拟争用线程，无额外实际child。父自身Popen前后崩溃/孤儿归属未测，父同步IO无独立deadline；不认证来源/原子exec输入/OS隔离/断电/全局nonce/真实SDK/时钟域/quiet drain/生产permit。协调重pin外层cleanup伪造仍可模型完成，物理授权标志全false。
原517来源、23保护项、实际49/65账本及失败owner/state保持；65已回收/remaining0、81..112未正式保留，USB/SD/context刷新/driver时钟/部署/正式发行保留/消费/claim均0，生产采集关闭。
下一步离线覆盖父在Popen前后中断的worker归属和清理；保持失败票据及拒绝重启，不接生产或真实硬件。以下为历史。

最新离线进度（2026-10-21）：[fixture中断发布与恢复拒绝](docs/A23_FIXTURE_PUBLICATION.md)完成。
新发布候选独占attempt→分段写/fsync→job及父目录同步→payload屏障→历史材料文件/目录同步→receipt.part分段写/fsync→不可覆盖link发布→result目录同步→stdout。原launcher/生产collector/permit未改，候选尚未接入launcher。
43安排=normal+18步后os._exit(73)+8步前模拟OSError(74)+16缓存坏件，仅normal允许模型完成；完整stdout/receipt的末端中断仍拒绝。50保留marker的重建被O_EXCL拒绝，54次恢复入口均拒绝/证据保持，4份未创建marker也不自动重启。10实际receipt/part同inode双链接核对，封存副本为独立普通文件。
新22+fixture绑定回归20+job关联回归20共62测试无跳过通过；已有receipt不覆盖、fsync API报错不进payload、短写补全/零进展拒绝，消费者open/io.open观察0。517来源搬移以独立UUID/nonce回放语义/恢复一致，CLI0/2/2且只读不launch。
两次共54实际Python publication worker由审计harness回收（36中断/16注入失败/2正常），候选自身launch/reap0、救援0、无后代/原生编译/driver/SDK执行。54审计fixture目录+3单元目录，正式记录/保留/消费/claim0。
仅验证进程退出后文件视图和同步调用顺序，不证明断电、全局nonce防重放、trace持久性或上游launch发行持久性。重pin的内部一致外层伪造仍可模型完成；真实来源/原子exec输入/SDK/时钟域/quiet drain/生产permit保持未认证。
原512来源、driver/桥/C/生产collector与未应用diff、23保护项、实际49/65账本及失败owner/state保持；65已回收/remaining0、81..112未正式保留，USB/SD/context刷新/driver时钟/部署/正式发行保留与消费均0，生产采集关闭。
下一步在新离线fixture launcher副本接入发布协议，组合启动前同步失败、子进程异常退出、结果发布中断与父收集/清理；不接生产或硬件入口。以下为历史。

最新离线进度（2026-10-21）：[fixture启动前job绑定与退出后关联](docs/A23_FIXTURE_JOB_BINDING.md)完成。
新固定Python fixture携带自身UUID/随机nonce、外部launch pin及一次性目录标记，新report/receipt绑定launch/attempt/stdout/材料字节；SDK/epoch材料明确为历史缓存，未执行新SDK，不继承shared32授权。
34安排=10启动/4启动前失败/20拼接或类型坏件，仅normal允许fixture完成；退出7/超时/stderr即使receipt一致仍拒绝。全部同目录重试拒绝，失败保留标记；新20+job关联回归20+统一回归20共60测试无跳过通过，纯消费open/io.open观察0，2线程模拟争用仅1次模拟spawn。
512来源搬移以独立UUID/nonce回放，语义一致，CLI0/2/2且只读不launch；原位置与搬移共18真实Python fixture子进程均候选回收，harness救援0，原生编译/完整driver/SDK执行0。28审计fixture目录，另3个mock-only目录；正式job/保留/发行/消费/claim均0。
独占只约束保留标记的单目录；同launch/nonce跨两副本可各进入模拟spawn（2次mock、实际child0），不证明全局防重放/断电持久性。内部一致伪造外层退出观察仍可模型完成，来源/原子exec输入绑定/真实SDK/时钟域/quiet drain/生产permit均未认证。
原507来源、driver/桥/C/生产collector与未应用diff、23保护项、实际49/65账本及失败owner/state保持；65已回收/remaining0、81..112未保留，USB/SD/context刷新/driver时钟/部署/正式记录保留与授权消费均0，生产采集关闭。
下一步离线覆盖fixture标记和receipt中断发布窗口，明确单目录单次使用持久性协议与恢复拒绝边界；保留跨目录复制负对照，不升级为全局防重放或生产许可。以下为历史。

最新离线进度（2026-10-20）：[supervisor与job/receipt只读关联候选](docs/A23_SUPERVISOR_JOB_LINK.md)完成。
确认entry/permit的build/receiver/consumed绑定与SDK receipt的session/identity/descriptor绑定不同；统一缓存无直接job绑定，不以序号/完成状态认定同次现场运行。9来源16源码锚点形成静态接入计划及未应用只读adapter diff。
复用已封存模拟job18成员与统一37缓存，显式declared_cross_model_correspondence及外部anchor；57场景含20种重声明anchor后的job/receipt/关系坏件均拒绝，33关联一致，仅2份保留模型完成，所有现场/许可标志false。
新20、统一回归20及历史permit/context16共56测试无跳过通过；18缺job成员/11声明字段/BOOL remaining/重算封存的SDK session拼接拒绝，消费者open/io.open观察0。507来源搬移语义/计划/diff一致，CLI0/2/2且只读不launch。
历史job UUID复用、remaining0保持；没有新建/保留/发行/消费/claim，未启动新worker/driver/broker/SDK、原生编译0。只读包装未安装/执行，既有生产collector/permit未改。外层一致伪造仍可能模型准入的负对照保留，不认证同次job运行/来源/exec绑定/时钟域/生产permit。
原503来源、driver/桥/C/生成模型、23保护项、实际49/65账本及失败owner/state保持；65已回收/remaining0，81..112未正式保留，USB/SD/真实SDK/driver时钟/context刷新/部署/正式发行与保留均0，生产采集关闭。
下一步准备fixture-only launch前job绑定与launch后结果关联，让新隔离回放携带自身上下文，明确单次使用/失败保留/外部信任输入；真实来源/SDK/quiet drain仍未认证。以下为历史。

最新离线进度（2026-10-20）：[统一supervisor收集、清理与关闭候选](docs/A23_SUPERVISOR_UNIFIED.md)完成。
旧18收集与15清理安排normal去重后32种，补5种close错误，共37场景；同一函数/33字段schema/纯字节准入，仅normal与EINTR继续完成允许，其余35拒绝。
关闭错误逐资源记录，不跳过后续close或cleanup wait；子进程退出0且driver有效仍会因close失败拒绝，harness救援不升级资格。统一stdout64KiB/stderr8KiB与0.5秒supervisor deadline，not_found不标sent，组信号前保留leader。
503来源搬移语义/观察一致；新20、旧cleanup20及collection20共60测试无跳过通过，33字段类型/48缺成员/23截断及重算清单后的内部健康伪造拒绝，消费者open/io.open观察0，CLI0/2/2且只读不launch。
原位置与搬移共72直系worker+6holder=78进程，候选直接回收64/harness救援8，父资源救援12；组尝试36(sent30/error4/not_found2)，候选close尝试216/完成204。2次spawn错误无进程；不认证后代wait回收/整个进程树。
伪造内部一致close成功观察的纯消费负对照仍可通过；实际来源/exec绑定/OS隔离/生产permit未认证。首轮通过，正确搬移脚本与摘要封存；旧498来源、driver/桥/C/生成模型及23保护项保持，本轮原生编译/完整driver执行0。
实际49/65账本及失败owner/state保持；65已回收/remaining0，81..112未保留，USB/SD/真实SDK/driver时钟/context刷新/部署/正式发行与保留均0，生产采集关闭。
下一步梳理既有waiting/job/receipt/permit只读消费接入点，关联job绑定和receipt、列清未认证条件并准备静态接入差异；现场时钟域/SDK/quiet drain仍未认证。以下为历史。

最新离线进度（2026-10-20）：[supervisor管道、退出与清理边界](docs/A23_SUPERVISOR_CLEANUP.md)完成。
新增15种Python固定安排，覆盖直系退出0但后代持stdout/stderr、两路/一路EOF但worker活、EINTR/读取/selector错误、组终止失败/不存在/直系后备、wait错误/超时及组合失败。
仅normal和EINTR继续完成准入，13种失败拒绝；EOF与退出分开，组信号前保留未回收leader，sent/not_found/error与attempted分别记录；回收失败后harness救援不升级候选资格。
498来源搬移语义/观察一致；新20、旧supervisor20及完整driver回归20项共60测试无跳过通过，25字段错误类型/23缺成员/23截断拒绝，消费者open/io.open观察0，CLI0/2/2且只读不launch。
原位置与搬移共30直系worker+6fork holder=36进程，候选直接回收24/harness救援6；组尝试26(sent20/模拟error4/not_found2)，直系后备6(sent4/模拟error2)，不认证后代wait回收或整个进程树。
内部一致伪造观察仍可获纯消费准入的负对照保持；实际来源/exec绑定/OS隔离/生产permit未认证。首轮通过，旧493来源、driver/桥/C/生成模型及23保护项保持，本轮原生编译/完整driver执行0。
实际49/65账本及失败owner/state保持；65已回收/remaining0，81..112未保留，USB/SD/真实SDK/driver时钟/context刷新/部署/正式发行与保留均0，生产采集关闭。
下一步在新隔离副本统一旧18收集与新15清理场景的schema/限额/终止/准入，补流关闭异常；现场时钟域/SDK/quiet drain仍未认证。以下为历史。

最新离线进度（2026-10-20）：[独立supervisor收集候选](docs/A23_SUPERVISOR_CANDIDATE.md)完成。
纯Python固定worker18种安排，覆盖缺stdout/非法或部分stdout/缺材料/退出7/SIGTERM/前后输出超时/输出超限/stderr/绑定错误/嵌套worker失败及注入spawn错误；每套实际17子进程均回收，不重试。
区分process_healthy、driver_complete、worker_healthy与完成准入，仅normal允许；退出0且driver完成但缓存worker失败仍拒绝。selector有界读取，超时/超限终止本次进程组并wait；supervisor独立monotonic不映射driver域。
493来源搬移回放语义/观察一致；新20、完整driver回归20及独立worker20项共60测试无跳过通过，48次缺成员/23次逐文件截断/21字段错误类型及重算清单后的worker健康伪造拒绝，消费者open/io.open观察0，CLI0/2/2且只读不launch。
退出观察7伪造0的纯消费负对照仍可通过，明确不认证外层观察来源/exec原子绑定/进程树回收或生产许可；此前3份种子复用封存缓存，driver/桥/C/生成模型保持，本轮原生编译和完整driver执行0。
原位置与搬移共34个Python假worker、2次模拟spawn失败、34直系回收、8次超时/超限组终止；使用supervisor deadline，driver clock/timebase/context刷新0。首轮通过，证据封存。
原488来源、23保护项、实际49/65账本及失败owner/state保持；65已回收/remaining0，81..112未保留，USB/SD/真实SDK/部署/正式发行与保留均0，生产采集关闭。
下一步离线覆盖直系退出但后代持管道、流已EOF但worker仍活、读取/终止/回收错误；实际来源/时钟域/SDK/quiet drain/permit仍未认证。以下为历史。

最新离线进度（2026-10-20）：[完整隔离driver的worker故障与收集边界](docs/A23_DRIVER_WORKER_FAILURE_MODEL.md)完成。
15种worker安排接入Capture/返回/持提交票据/释放后/receipt后，与旧72共87场景；优化/UBSan及488来源搬移重建一致，driver/桥/C/diff与受保护片段保持，仅生成model_main变化。
12种由driver拒绝；3种无有效时钟变化的worker失败仍让driver完成，纯字节收集器保留反例并拒绝15种的完成声明。对象替换仍释放原owner票据；receipt后故障核对stale旧快照。
新20、旧并发20及独立worker20项共60测试无跳过通过；795次更新export/清单后的字段篡改、375次缺成员及25次截断拒绝，消费者open/io.open观察0，CLI0/2/2。
r1修正stop清除epochs_saved_complete的校验预期；r2撞4096节点封存上限，新audit限定8192且其他字节/路径/类型约束保持；r3换行截断未拒绝，r4补外层逐文件字节清单，失败及中间搬移封存。
含失败和中间搬移共11模型/33 compiler jobs/11有效进程/10无参数拒绝/319线程；最终r4原位置与搬移共4模型/12jobs/4有效进程/116线程，不认证来源/全部交错/cancel/崩溃或自动恢复。
原483来源、23保护项、实际49/65账本和失败owner/state保持；65已回收/remaining0，81..112未保留，USB/SD/真实SDK/context刷新/部署/正式发行与保留均0，生产采集关闭。
下一步离线准备独立supervisor收集候选，覆盖无stdout、缺材料、异常退出与超时；实际时钟域/SDK/quiet drain/生产permit仍未认证。以下为历史。

最新离线进度（2026-10-20）：[独立worker失败与材料完整性模型](docs/A23_WORKER_FAILURE_MODEL.md)完成。
13种C pthread安排覆盖异常返回/pthread_exit、未完成写入、错误票据、显式Abort、无效Finish、耗尽及替换store；每fixture13线程，优化/UBSan与483来源搬移重编译一致。
未完成写入保持Busy且采样清零，显式Abort推进版本不恢复旧样本，耗尽毒化不回绕；异常worker即使时钟有效也无完成资格，仅readonly正常场景可声明模型完成。
纯字节消费者核对5成员精确清单/摘要/schema/case/类型/全部指定字段；299次字段篡改后重封存、65次缺成员及5次截断均拒绝，消费者open/io.open观察0。
新增20、旧并发20及旧C20项共60测试无跳过通过；三种只读CLI返回0/2/2。含搬移4份独立C fixture/4 compiler jobs/4有效进程/4未知参数拒绝/52线程。
此前479来源、driver/Obj-C桥/C helper、23保护项、实际49/65账本及失败owner/state保持；本轮未构建/执行完整driver，故障接入完整driver尚未完成，不认证pthread_cancel/崩溃/全部交错/来源或自动恢复。
65已回收/remaining0，81..112未保留；USB/SD/真实SDK/context刷新/正式发行与保留均0，生产采集关闭。
下一步离线将worker故障/耗尽/替换安排接入完整driver Capture/BeginCommit/post-guard窗口，明确外层收集不完整材料的终止行为；现场时钟域/SDK/quiet drain/permit仍未认证。以下为历史。

最新离线进度（2026-10-20）：[提交期间指定并发与缓存诊断关联](docs/A23_COMMIT_CONCURRENCY_MODEL.md)完成。
新增13种pthread安排，含持票据发布/ABA/no-op、两发布者、ISO/control前后顺序、journal失败、Capture返回/释放/receipt后的写入；每fixture14 worker。
72场景优化/UBSan与479来源搬移重建一致；新20、旧driver21及旧C20项共61测试无跳过通过，三种只读CLI返回0/2/2。
持票据发布均Busy，callback撤销完成仍释放票据；释放后ABA或receipt后no-op推进版本并按保存时点区分失败receipt与stale receipt，不认证全部线程交错。
字节缓存消费者关联72场景的17 version/18 facts/各owner4字段及receipt快照；41次更新副本或重算receipt摘要的内存坏件均拒绝，消费者open/io.open观察0，外层收集仍读review。
只更换生成model_main，driver/桥/C/diff原字节不变；原非参与ABA负对照保持。首轮通过，原位置/搬移共4份模型、12 compiler jobs、4次有效/4次无参数拒绝、56 worker线程。
原474来源、23保护项、真实49/65、账本及失败修复owner保持；65已回收/remaining0，81..112未保留，USB/SD/真实SDK/context刷新/发行/保留均0，生产采集关闭。
下一步离线补worker异常/未完成写入、票据耗尽及对象替换失败安排，定义不完整并发材料的收集拒绝规则；现场时钟/域映射/SDK runtime/quiet drain及生产permit仍未认证。以下为历史。

最新离线进度（2026-10-20）：[版本快照接入现有macOS主机隔离模型](docs/A23_VERSIONED_DRIVER_MODEL.md)完成。
纯C候选原字节保持，Obj-C适配层持有store并转接；mock profile setter全走C Begin/Finish，driver强引用固定owner。Switch固件与原driver源码未改，生产集成false。
59场景优化/UBSan与474来源搬移重建一致；新21、旧C20及旧driver故障20项共61测试无跳过通过，三种只读CLI返回0/2/2。
起止/两次采样间/采样后ABA拒绝；提交期间持奇数票据覆盖append→post-guard→settled，参与发布Busy不改字段；释放后版本变化由guard撤销，receipt变stale。
append失败、旧callback或clock替换仍释放原owner票据；非参与字段ABA仍可通过，所有写入方参与及真实时钟来源未认证。sidecar增加版本/绑定声明，事件与receipt schema保持。
deadline、emit/stop、receipt/result字节保持；guard明确增加对象/版本检查，整段旧emit/stop/guard不再相同，完整差异在work/driver-versioned.diff。
首次导入占位错误未构建；r1整数1/BOOL sidecar被拒绝，r2仅修fixture；r3加持票据clock替换并固定owner释放。含搬移7份模型、21个compiler jobs、7次有效/6次无参数拒绝，失败封存。
原467来源、C候选、23保护项、真实49/65、账本及失败修复owner保持；65已回收/remaining0，81..112未保留，USB/SD/真实SDK/context刷新/发行/保留均0，生产采集关闭。
下一步继续离线加入持票据期间的指定并发发布/callback交错并增强sidecar诊断和receipt失效关联；真实域映射、SDK runtime、现场quiet/drain及生产permit仍未认证。以下为历史。

最新离线进度（2026-10-20）：[参与式版本时钟快照候选](docs/A23_VERSIONED_CLOCK_CANDIDATE.md)完成独立C验证。
43场景优化/UBSan及467来源搬移重编译一致；新增20、旧driver故障20及旧算术18项共58测试无跳过通过，三种只读CLI返回0/2/2。
顺序一致原子字段、Begin奇数/Finish偶数版本、Abort/no-op推进、耗尽毒化不回绕；采样只调用一次reader且无显式自旋/自动重试，端点绑定store/声明incarnation/同版本。
5个参与式ABA位置/线程场景拒绝；2个绕过版本的ABA负对照仍通过，要求所有写入方参与且维持store生命周期，不认证时钟或强制写入契约。
结束采样后发布新profile不撤销历史样本；完整driver的提交/post-guard版本窗口尚未适配，旧driver ABA反例保持，Objective-C桥及driver集成均未实现。
原位置/搬移共4份独立C fixture、4个compiler jobs、4次有效/4次未知模式拒绝、12个指定安排的线程；未执行driver/SDK模型，也未证明全部线程调度或OS能力隔离。
原462来源、冻结driver/桥/fixture、23保护项、真实49/65、账本及失败修复owner保持；65已回收/remaining0，81..112未保留，USB/SD/真实SDK/context刷新/发行/保留均0，生产采集关闭。
下一步离线准备拥有store生命周期的Objective-C桥及全mock写入适配，再定义隔离driver的结束采样→append/post-guard版本检查与sidecar表达。以下为历史。

最新离线进度（2026-10-20）：[driver callback/deadline/profile故障回放](docs/A23_DRIVER_FAULT_MODEL.md)完成。
46场景含24个deadline边界、10个profile采样内部变化及12个callback/提交故障，优化/UBSan与462来源搬移重建一致；新增20及旧完整模型20/副本20项共60测试无跳过通过。
arrival等号允许、poll等号超时；2/3比例poll提前ceil超时的保守策略保持。排队25ms按原arrival判断，ISO缺失仅abort一次，abort后晚callback仍终止并保留未确认存储。
可见profile变化8项拒绝，ABA恢复2项仍通过，明确保留非原子读取反例；sidecar为注入声明，原始payload/STATUS、事件/receipt与类型边界核对不认证来源。
新renderer仅改模型main并插入FaultClock，其他生成实现及driver候选不变；真实factory/Mach/context实现排除，执行前检查链接库/符号，非OS能力隔离证明。
r1 unused pairZero被-Werror拒绝且无模型执行，r2恢复映射零值检查；含搬移10个compiler jobs（9成功/1失败）、4份模型、4次模型进程及4次无参数拒绝，失败封存。
原457来源、冻结driver、23保护项、真实49/65、账本及失败修复owner保持；65已回收/remaining0，81..112未保留，USB/SD/真实SDK/context刷新/发行/保留均0，生产采集关闭。
下一步离线设计profile/ticks一次性快照或版本协议，以ABA反例检验，并增强sidecar诊断关联；实际域映射、SDK runtime、现场quiet/drain及生产permit仍未认证。以下为历史。

最新离线进度（2026-10-20）：[完整driver隔离数值时钟回放](docs/A23_ISOLATED_DRIVER_MODEL.md)完成。
相同driver候选在裁剪后的SDK-shaped provider/lease、budget、owner及journal中链接执行；真实factory/Mach clock/session执行器被排除，执行前检查符号与链接库。
19场景优化/UBSan与457来源搬移重建一致；新增20及旧副本20/quiet20项共60测试无跳过通过，三种只读CLI返回0/2/2。
2/3比例差1 tick仍等待，再加1 tick精确达标；profile变化/对象替换/tick0/倒退/溢出拒绝；append或post-guard失败不settled，晚回调撤销完成及receipt。
profile sidecar仅为fixture声明；owner独立计数器无driver域映射，profile读取原子性/ABA、真实SDK runtime、现场quiet/drain与生产permit仍未认证。
r1队列外读取lease.result触发断言，r2仅修fixture；r2测试下标错19通过/1失败，r3修正测试并格式化pin表，生成实现不变，失败均封存。
含失败及搬移共7份隔离模型、14个compiler jobs、7次模型进程及6次无参数拒绝；这不构成OS能力隔离证明。
原452来源、冻结driver、23保护项、真实49/65、账本及失败修复owner保持；65已回收/remaining0，81..112未保留，USB/SD/真实SDK/context刷新/发行/保留均0，生产采集关闭。
下一步继续离线扩充完整driver的callback/deadline故障和profile读取中途变化回放，核对sidecar与事件消费边界。以下为历史。

最新离线进度（2026-10-20）：[driver隔离副本与时钟桥验证](docs/A23_QUIET_DRIVER_COPY.md)完成。
生成完整driver候选及unified diff，原版/候选仅编译对象；deadline、emit/stop/guard及receipt/result片段保持原字节。
构造前检查injected协议/实例/ratio；quiet起止捕获profile并绑定进程内对象，精确minimum后仍先append再guard才settled；完整driver未链接/执行。
Foundation-only桥27场景、优化/UBSan和452来源搬移重编译一致；新20及旧quiet20/算术18项共58测试无跳过通过，三种只读CLI一致。
未标注/缺selector/可见profile变化/对象替换被拒绝；ABA变化后恢复仍可通过，profile读取不具原子性，也不认证真实来源。
旧TwoClock使用Mach时钟，broker读取实际context，native列表含真实factory；完整SDK回放未启动，work/replay-plan.json列明四项缺口。
r1整数1/BOOL序列化失败封存，r2仅修正fixture；合计6个driver对象、5份Foundation fixture、16个compiler jobs、9次fixture进程执行。
原447来源、冻结driver、23保护项、真实49/65、账本及失败修复owner保持；65已回收/remaining0，81..112未保留，USB/SD/真实SDK/context刷新/发行/保留均0，采集关闭。
下一步离线替换旧fixture的TwoClock并裁剪真实factory构建输入，确定profile证据导出方式，再定义隔离回放范围。以下为历史。

最新离线进度（2026-10-20）：[独立quiet轮询与deadline适配候选](docs/A23_QUIET_POLL_CANDIDATE.md)完成验证。
精确最短等待后按guard→完成事件append→post-guard→settled顺序；失败撤销资格且不重试，历史settled_at仅作诊断保留。
保留quiet的tick0未开始sentinel；quiet只接受injected-driver域。arrival等号允许、poll等号超时及分数ceil的保守最大时限策略均保留。
604场景/1720次轮询、166个deadline边界在优化/UBSan及447来源搬移重编译中一致；新20及旧算术18/时钟16项共54测试无跳过通过。
r1仅数量断言误写，19通过/1失败日志保留；修正后r2全通过，C源码未改。三处合计6份离线fixture构建、90次fixture执行。
原442来源、冻结driver和时钟helper、23保护项、真实49/65、账本及失败修复owner保持；65已回收/remaining0，81..112未保留。
guard/append为mock返回，未认证日志持久化、完整driver或callback drain；未构建/启动生产receiver，USB/SD/真实SDK/context刷新/发行/保留均0，采集关闭。
下一步离线准备Objective-C driver隔离副本补丁与回放方案，先核对mock/build输入、quiet起点clock实例/timebase快照及生产域适配要求。以下为历史。

最新离线进度（2026-10-20）：[原生精确等待与显式时钟域候选](docs/A23_NATIVE_CLOCK_CANDIDATE.md)完成独立验证。
新增C helper以128位整数精确比较minimum/maximum，ceil仅用于报告；不足250ms的2/3 timebase反例不再被提升为达标，溢出/倒退/域/实例/timebase变化均拒绝。
2333向量与Python Fraction oracle一致；优化/UBSan两版无警告或sanitizer输出，442来源搬移后重新编译结果一致。
新增18及旧时钟16/外层18项共52测试无跳过通过；只读CLI三种pin返回0/2/2，不执行C二进制。
原位置及搬移合计构建4份离线C fixture、执行40次fixture进程；未构建或启动生产receiver，USB/SD/真实SDK/context刷新/发行/保留均0。
原437来源、冻结runtime guard/driver、23保护项、真实49/65、账本及失败修复owner保持；65已回收/remaining0，81..112未保留，生产采集关闭。
候选尚未接入driver，域/实例仍是声明，实际时钟/现场quiet/drain/SDK链/生产许可未认证。下一步独立适配quiet轮询及sentinel，保留arrival/poll最大时限区别。以下为历史。

最新离线进度（2026-10-20）：[缓存外层取证与完整文件清单边界](docs/A23_CACHED_OUTER_FORENSICS.md)完成。
从原first capture恢复4份外层材料，与92份raw缓存精确覆盖同一96成员清单；核对COMMITTED、capture/worker job、stat声明及保存的bootstrap/journal摘要。
历史空scratch与detached缓存的empty分别处理；worker PID84237与模型child81936分属不同角色。stat/PID变化可内部一致，均不认证真实来源。
成功profile额外要求观察到的worker退出声明为整数0；旧schema仅限-255..255，退出7的重算封存模型被拒绝；旧worker/完整分析器未重跑。
47场景中4种声明一致、43坏件拒绝；新增18及旧收集17/时钟16项共51测试无跳过通过；437来源搬移及三种CLI一致，消费者文件打开0。
完整文件字节覆盖不代表完整运行语义；实际时限/时钟、live source、原子快照、目录/worker来源、SDK链及生产permit仍未认证。
原434来源、23保护项、真实49/65、账本及失败修复owner保持；65已回收/remaining0，81..112未保留，本轮USB/SD/真实SDK/原生执行/context刷新/发行/保留均0。
下一步离线准备原生精确minimum与显式时钟域候选，复现分数timebase反例并验证整数/溢出边界，候选独立于冻结构建。生产采集关闭。以下为历史。

最新离线进度（2026-10-20）：[缓存来源准入、verifier与静态收集关联](docs/A23_CACHED_COLLECTION_LINKS.md)完成。
历史392来源准入/expected scope与已验证构建对应；verifier报告、52份inputs/463257字节/8目录声明、report摘要和监督流副本逐项关联。
保存的shared/entry/SDK摘要与既有包/6144有效字节/quiet子集对应；外层退出/完整链仍只是声明，静态收集不继承退出认证。
45场景中4种一致、41坏件拒绝；新增17及旧时钟16/permit16项共49测试无跳过通过；434来源搬移及三种CLI一致，消费者文件打开0。
verifier检查33次仅为报告声明，34次模型亦可一致；未运行verifier或认证调用次数，保存的原分析器也未独立重跑。
原431来源、23保护项、真实49/65、账本及失败修复owner保持；65已回收/remaining0，81..112未保留，本轮USB/SD/真实SDK/原生执行/context刷新/发行/保留均0。
下一步离线审查raw之外的外层取证/worker结果与整体缓存边界；另行准备原生精确minimum/显式时钟域候选。现场来源、实际时限、完整SDK链及生产许可仍false，生产采集关闭。以下为历史。

最新离线进度（2026-10-20）：[缓存时钟域与模型时限算术](docs/A23_CACHED_CLOCK_DOMAINS.md)完成。
固定driver注入1/1、owner未知timebase及supervisor-ns独立域；拒绝跨域减法、假mapping、来源/ratio/权限漂移。
driver域内重算帧/入队/触发预算、16ms/2s入口到达、因果顺序及250ms quiet；队列日志延迟不替代入口到达，owner不换算时长。
30场景中7种算术一致、23坏件拒绝；新16及旧permit16/session15项共47测试无跳过通过；431来源搬移及三种CLI一致，消费者文件打开0。
新增分数最小等待反例：2/3基准下不足250ms可被ceil补到阈值；离线minimum改为精确交叉乘法。当前1/1 profile不受影响，原生代码未修改/执行。
r1保留为初始1/1原型、r2为最终审查；正常模型ISO800ns/control200ns、quiet250000101ns仅为注入算术，不是设备性能或wall-clock证明。
原428来源、23保护项、真实49/65、账本及失败修复owner保持；65已回收/remaining0，81..112未保留，本轮USB/SD/真实SDK/原生执行/context刷新/发行/保留均0。
时钟来源、现场时限/观察窗口、完整SDK链和生产许可仍false；下一步离线补齐来源准入/verifier/最终收集关联，并单独准备原生最小等待规则候选。生产采集仍关闭。以下为历史。

最新离线进度（2026-10-20）：[缓存中的模拟发行、原生许可与context关联](docs/A23_CACHED_PERMIT_CONTEXT.md)完成。
从缓存核对共享模型job/authorization/reservation/issue/consumed、历史49/65成员摘要、原生process/selection claim及entry回执/context/PID。
外层hello/handoff/nonce/命令/监督/collection PID关联，实际context仅按声明替换三项sandbox字段；历史实际策略不通过，注入执行context通过。
33场景中3种模拟关联一致、30个重算清单/封存后的坏件拒绝；新16及旧session15/构建15项共46测试无跳过通过。
完整内部PID拼接和额外context字段替换先通过内部关联，再由外层拒绝；428来源搬移及三种CLI一致，消费者文件打开0。
保留host斜杠转义/无换行与native规范JSON原字节及各自摘要；r1兼容拒绝封存，r2为最终审查。
原425来源、23保护项、真实49/65、账本及失败修复owner保持；65已回收/remaining0，81..112未保留，本轮USB/SD/真实SDK/原生执行/context刷新/发行/保留均0。
生产许可、真实进程来源、完整SDK链、时限和现场认证仍false；下一步明确注入driver与真实owner时钟域及可验证时限规则，再补齐剩余准入/收集关联。生产采集仍关闭。以下为历史。

最新离线进度（2026-10-20）：[缓存中的entry、receipt与SDK session关联](docs/A23_CACHED_SESSION_LINKS.md)完成。
从缓存关联entry/current/final、driver副本、SDK receipt/snapshot、25条SDK事件、12条entry事件与两轮epoch绑定/字节摘要。
30场景中3种关联一致、27个重算清单/封存后的坏件拒绝；新15及旧构建15/日志15项共45测试无跳过通过。
搬移425来源后全场景及三种CLI重放一致，消费者文件打开0；r1坏件路径构造错误保留，r2为最终审查。
确认历史模型driver/journal用注入时钟、owner用真实mach_absolute_time；两类ticks无已验证映射，owner偏移仍可满足数据关联。
完整SDK链、原生许可/context策略、时限/250ms观察窗口和现场认证仍false，不能把关联一致升级为时序认证。
原422来源、23保护项、真实49/65、账本及失败修复owner保持；65已回收/remaining0，81..112未保留，本轮USB/SD/真实SDK/原生执行/发行/保留均0。
下一步从缓存核对发行/消费、authorization receipt与原生permit/context，再明确注入/真实时钟独立域或有界映射；生产采集仍关闭。以下为历史。

最新离线进度（2026-10-20）：[缓存构建结构与日志引用关联](docs/A23_CACHED_BUILD_RELATIONS.md)完成。
从既有4+4组缓存核对两份构建的392来源、绑定头、binary、基线71成员/69份card内容及完整文件覆盖；两角色来源/模型二进制一致。
关联worker、marker/envelope/final/handoff、namespace scope及config/current/final的entry构建引用，全程从缓存核验。
29场景中正常1、重算字节清单/封存后的28坏件拒绝；新15项及旧分组14/日志15项共44测试无跳过通过。
搬移422来源后全场景及三种CLI重放一致，消费者文件打开0；r1/r2失败诊断独立封存，r3为最终审查。
entry构建绑定与epoch SDK session绑定是不同schema，二者尚未通过session/receipt关联；完整SDK链、编译来源和现场认证仍false。
原419来源、23保护项、真实49/65、账本及失败修复owner保持；65已回收/remaining0，81..112未保留。
本轮USB/SD/真实SDK/原生执行/正式发行/保留均0。下一步从缓存建立entry→driver/receipt→SDK session关联，再核对许可/context、时限和观察窗口；生产采集仍关闭。以下为历史。

最新离线进度（2026-10-20）：[构建字节分组与有界分片](docs/A23_GROUPED_BUILD_BYTES.md)完成。
两份历史构建486/395文件、6409413/4976609字节分成各4组、488/397片；原文件摘要从缓存逐片重算一致。
每片512 KiB、每组128片及8 MiB内容上限，旧视图限制保持；大文件不提供无界整读。
新增14项及旧日志15/视图16项共45测试无跳过通过；419来源搬移后重新分组、三种CLI一致，消费者文件打开0。
初次搬移的Python字节码污染副本已保留拒绝诊断，禁写字节码后复核通过；最终采用审查r3。
原416来源、23保护项、真实49/65、账本及失败修复owner保持；65已回收/remaining0，81..112未保留。
本轮USB/SD/真实SDK/原生执行/正式发行/保留均0；构建语义、完整SDK链、时限/观察窗口和现场认证仍false。
下一步从缓存核对descriptor/来源/绑定头/binary和worker构建引用，再关联session、receipt及原生许可；生产采集仍关闭。以下为历史。

最新离线进度（2026-10-19）：[缓存中的完整日志与两轮事务子集](docs/A23_CACHED_JOURNAL_EPOCHS.md)完成。
精确固定92份原始材料/516080字节，另绑定同一清单的worker声明；八层封存、七事件链、job关系与两轮事务/STATUS从内存检查。
18场景中16坏件拒绝，正常及未传输填充变化通过；4范围拒绝、3种加载后变更、新15项/旧消费者14项测试通过。
搬移416来源重放及七种CLI一致，2115次缓存读取文件打开0。r1原生JSON无末尾换行兼容失败保留，r2为最终审查。
两份外部构建486/395文件且最大1435312字节，超出单视图限制，未缓存或执行；完整SDK链、时限/观察窗口和现场认证仍false。
本轮USB/SD/真实SDK/原生执行/正式发行/保留均0；原413及23保护项、49/65、失败修复owner保持，65已回收/remaining0，81..112未保留。
下一步离线设计构建分组/大文件约束，并接入session、receipt及剩余关联；生产采集仍关闭。以下为历史。

最新离线进度（2026-10-19）：[固定字节视图的只读语义消费者](docs/A23_PINNED_SEMANTIC_CONSUMER.md)完成。
外部清单摘要、内容合同和缓存字节逐项关联；检查标记副本、首事件、声明结构及raw长度，全程从缓存消费。
22场景中19个摘要有效的语义坏件拒绝；3个仅部分关系一致，始终不认证完整日志、构建、job关联、事务或载荷。
7组范围拒绝、3种加载后磁盘变更、新14项/旧视图16项测试通过。搬移413来源重放及六种CLI一致；162次缓存读取，文件打开0。
仅离线文件分析，USB/SD/真实SDK/原生执行/正式发行/保留均0；原410及23保护项、真实49/65与失败修复owner保持。
65已回收/remaining0，81..112未保留。下一步离线明确完整日志、事务/STATUS与外部关联的材料范围，生产采集仍关闭。以下为历史。

最新离线进度（2026-10-19）：[独立字节视图与硬链接模型](docs/A23_PINNED_BYTE_VIEW_MODEL.md)完成。
以外部合同固定6份封存材料和模型空目录，排他字节复制后一次性校验并加载只读内存；后续缓存读取不重开可变路径。
16场景、3发布进程退出、双进程竞争、7坏视图及新16项/旧window16项测试通过。搬移410项来源重放一致，126次缓存读取文件打开0。
输入/读取期间/输出硬链接策略拒绝；加载后磁盘改写、别名写入或替换不改变缓存，磁盘重新验证失败。接口不提供OS不可变或现场认证。
仅运行文件worker；USB/SD/真实SDK/正式发行/保留均0，原406及23保护项、真实49/65、失败修复owner保持。
65已回收/remaining0，81..112未保留。生产视图/采集仍关闭；下一步离线接入只读语义消费者，明确外部合同与失败路径。以下为历史。

最新离线进度（2026-10-19）：[封存前复读与观察边界模型](docs/A23_CAPTURE_WINDOW_MODEL.md)完成。
新增两次描述符复读，比较首份证据、内容摘要、目录清单及身份；3个首份完整但来源已变的反例由后续观察拒绝。
15场景、7篡改归档检查、新16项测试及旧bootstrap21项回归通过；搬移406项来源和六种只读CLI复核一致。
明确保留最后观察后变更的反例：观察集合仍一致，却不证明提交期间来源未变；原子快照/当前来源认证字段始终false，不授予现场许可。
仅运行文件worker；原生构建392项不执行/编译，USB/SD/真实SDK/正式发行/保留均0。原402及23保护项、49/65与失败修复owner保持。
65已回收/remaining0，81..112未保留。生产采集与OS隔离仍关闭；下一步离线研究固定来源视图、硬链接及取证写入中断。以下为历史。

最新离线进度（2026-10-19）：[日志建立前中断与描述符取证模型](docs/A23_BOOTSTRAP_CAPTURE_MODEL.md)完成。
日志未建立、空/半截源标记、初始副本和首事件损坏时均可只读封存，不修复、释放或重试原尝试。
26场景（1完整/25不完整），19文件worker退出场景、3描述符替换模型、7篡改归档检查及26次重试拒绝通过。
新增21项测试与旧journal17项回归通过；搬移402项来源全场景/六种只读CLI复核一致，27次取证调用源execution打开0。
原生构建仍为392项且本轮不执行/编译；USB/SD/真实SDK/正式发行/保留均0。原397及23保护项、真实49/65和失败修复owner保持。
65已回收/remaining0，81..112未保留。生产恢复、采集和OS级隔离未开放；组件分别观察，仍需研究读取后的后续变更和取证自身中断。以下为历史。

最新离线进度（2026-10-19）：[收集中断日志与只读取证模型](docs/A23_COLLECTION_JOURNAL_MODEL.md)完成。
源尝试标记先于执行树扫描；写入失败、源变化和进程中断保留现场，拒绝自动重试。取证副本封存不改变原事务状态。
14场景（3收集事务完成/11部分），5进程中断点、8篡改归档检查、14次重试拒绝、双进程竞争仅一成功。
新17项测试与旧异常收集17项回归通过；搬移397项来源后文件worker全场景及只读CLI五模式重放一致。
只运行文件收集worker，原生构建继续绑定392项且本轮不执行/重编译；USB/SD/真实SDK/正式发行/保留均0。
新增5项共397，原392及23保护项、真实49/65账本、失败修复owner保持；65已回收/remaining0，81..112未保留。
生产采集、生产故障收集与OS级隔离未开放。下一项继续离线检查标记到日志建立的中断窗口、路径竞争和启动后来源变化。以下为历史。

最新离线进度（2026-10-19）：[启动前复核与异常退出收集模型](docs/A23_FAILURE_COLLECTION_MODEL.md)完成。
补上子进程已退出但报告缺失/空白/损坏/非对象时的封存路径，原始字节、退出码及模型消费保留，不完整证据不能冒充成功。
启动前重新核对当前392项来源与两种冻结构建，来源/构建漂移在创建子进程和模型消费之前拒绝。
12场景（1注入完整/11不完整）、2启动前拒绝、1启动失败、7篡改归档检查、新17项测试与旧broker16项回归通过；搬移重编译重绑后重放一致。
收集API不接收进程或发行器，但尚未实现OS级能力隔离；当前来源检查仅保证检查时点。实际模型沙箱结果仍1，真实采集关闭。
新增7项共392，原385项与23保护项、真实49/65账本、失败修复owner保持；USB/SD/真实SDK/正式发行/保留均0。
65已回收/remaining0，81..112未实际保留，生产32目录未创建。下一项继续离线隔离、启动后来源变化及收集途中失败审查。以下为历史。

最新离线实现（2026-10-19）：[监督、消费许可与退出收集闭环模型](docs/A23_BROKER_MODEL.md)完成。
同一模型子进程串联真实context→绑定命令→一次性模型消费→原生permit/WAITING→假SDK两轮→退出收集。
实际沙箱结果仍1，默认环境拒绝在发行/WAITING/SDK之前；正向模型显式注入三项策略字段，始终不授权真实采集。
12闭环场景（2注入完整/10不完整）、1启动失败、7坏联合归档及16项测试通过；搬移重编译重绑两种构建scope后重放一致。
接收链单独有效的PID替换被外层真实context关联拒绝；消费后失败保留模型占用，未退出不提交、超时不重试。
交接最多5秒/整项模型最多30秒固定分开，旧监督器和SDK预算原字节保持；迟到交接不能使用剩余执行预算。
新增7项共385，378旧来源与23保护项、真实账本、49/65及失败修复owner保持；USB/SD/真实SDK/正式发行/保留均0。
65已回收/remaining0，81..112未实际保留、生产32目录未创建。生产broker/acquire仍关闭，下一项继续离线入口能力与异常收集审查。以下为历史。

最新离线实现（2026-10-19）：[父子进程监督与环境交接模型](docs/A23_MODEL_SUPERVISOR.md)完成。
原生辅助程序只读取真实自身context；父进程绑定nonce、PID/PPID、身份、二进制与显式环境，不继承Python/DYLD设置。
有界非阻塞管道；超时锁定失败并保留子进程/管道引用，不自动kill/释放/重试；退出前不提交最终归档。
22监督模型（2完整/20失败）、5启动准入、9坏归档及15项测试通过ASan/UBSan；搬移重编译/重放一致。
正常模型交接完整但实际sandbox结果1、执行策略不通过；监督完整不授予采集许可，现场acquire仍关闭。
新增6项共378，372旧来源和23保护项保持；旧账本、49/65、失败修复owner保持，USB/SD/真实SDK/正式发行/保留均0。
65已回收/remaining0，81..112未保留、生产32目录未创建。下一项离线连接消费许可/context与退出收集，尚无生产监督器。以下为历史。

最新离线实现（2026-10-19）：[异常模型最终收集与独立复核](docs/A23_FINAL_MODEL_COLLECTION.md)完成。
已退出的受监督模型才扫描收集；运行中/未知生产者拒绝，静态模式不声称观察到退出。
排他目录与ATTEMPT阻止覆盖/续写；失败和来源变化保留不提交，原件/空目录/部分stdout及stderr均保存。
28场景全部生成有效归档（2模型完整/26不完整）；3拼接材料、13坏归档和18项测试通过，收集竞争仅一成功。
搬移后重编译原生模型、重放全部场景与生命周期检查；独立CLI区分完整/不完整/损坏，原仓库/Volumes文件打开0。
新增5项共372，367旧来源和23保护项保持；原生构建仍绑定原367项，新收集来源单独冻结。
本轮USB/SD/真实SDK/固件构建/正式发行/保留均0；65已回收/remaining0，81..112未保留、生产32目录未创建。
现场故障收集与acquire仍关闭；归档不授权清理/重试、不证明回调排空。下一项继续离线监督/context交接审查。以下为历史。

最新离线实现（2026-10-19）：[只读来源复核器、独立构建与联合回执](docs/A23_READONLY_SCOPE_VERIFIER.md)完成。
冻结367来源、最新69原件、旧49/65账本记录和12份恢复快照索引；复核当前/冻结来源与全共享作业见证。
在启动前、轮次之间与最终导出前后核验；已停止但请求状态不确定时继续推迟全包扫描，保留部分日志及资源。
28原生场景（2完整/26拒绝，含11构建坏件）、3份单独有效的拼接坏件及19项测试通过ASan/UBSan。
搬移后重新编译两个程序、重新绑定二进制/构建scope并重放全部场景，分类/计数一致；原仓库/Volumes文件打开0。
专用文件CLI可检查当前来源/独立归档/环境；现场acquire拒绝，正式scope继续false，失败最终收集器待实现。
359旧来源、23保护项、旧真实账本和失败修复owner保持；USB/SD/真实SDK/固件构建/正式发行/保留均0。
65仍已回收/remaining0；生产32目录未创建，81..112未保留。下一项继续离线最终收集和外部复核。以下为历史。

最新离线实现（2026-10-19）：[共享32账本与原生文件permit](docs/A23_SHARED_SEQUENCE32_NATIVE_PERMIT.md)完成编译与验证。
不同作业共用一个81..112占用；作业A失败后B不能接管，发行/消费必须明确commit，缺标记不续阶段。
原生许可绑定消费回执、scope、context和选择；排他标记阻止跨实例复用，已观察到的stale不可恢复。
23原生场景、11共享场景、12坏件、18项检查通过ASan/UBSan；搬移重编译/重放一致，两种跨进程竞争各一成功。
生产引擎/permit分支已实现；生产fresh verifier、专用新构建与采集CLI未接通，当前scope继续拒绝正式初始化。
351旧来源及23保护项保持，新增8项后359；旧真实账本含.lock、49/65记录、失败修复owner/状态不变。
本轮USB/SD/SDK/真实接收器/固件构建/正式发行/保留均0；新生产32目录未创建，81..112未实际保留。
下一项离线接入正式只读verifier、专用build/原生入口与最终收集；65仍已回收/remaining0，不发新实测。以下为历史。

最新离线实现（2026-10-19）：[69份基线与32序号一次流程模型](docs/A23_TWO_EPOCH_BASELINE69_WORKFLOW.md)完成。
只读采用确切69原件，重算63→69差异：新增6份、仅logfile变化、62旧原件及8ERPT保持；四部署项匹配。
一个排他记录整体保留81..112；部分/空写入也保留全部32；消费、进程和选择声明各一次，不补发、不恢复。
23文件模型、15坏件、17项检查通过；四组跨进程竞争均仅一成功，搬移后重建69清单并重放一致。
写入限原始/private/tmp模型根，副本只读分析；真实共享账本、生产permit和采集CLI尚未实现，预览固定不可正式发行。
345旧来源及23保护项保持，新增6项后351；真实49/65记录与账本含.lock、失败修复owner/状态保持。
本轮USB/SD/SDK/接收器/固件构建/正式发行/保留均0；65已回收/remaining0，81..112实际未保留。
下一项离线接入生产共享账本、预览/发行/消费与原生permit；模型成功不认证物理来源或设备双轮。以下为历史。

最新离线实现（2026-10-19）：[SDK等待入口、构建绑定与最终检查点](docs/A23_TWO_EPOCH_SDK_ENTRY.md)完成。
串联环境→进程许可/声明→WAITING→选择许可/声明→SDK准备→下一轮启动→最终检查点；许可回调退出也阻止继续。
专用构建冻结345来源并生成文件检查程序；只有describe/check-build/inspect-context，现场acquire模式未实现。
33原生注入场景、18坏件、13项检查通过ASan/UBSan；搬移后重编译两个程序、重新分类一致。
坏件逐项断言拒绝原因；旧r1/r2的清单排序/context重编码问题及构造事件顺序初稿均保留，以r3最终审查为准。
当前文件自检如实记录沙箱结果1、环境门禁不通过；未提权，SDK与IOKit后续路径仍由假operations验证。
336旧来源及23保护项保持，新增9项后345；真实USB/SD/SDK/等待器/固件构建/发行/保留均0。
65保持已回收/remaining0，81..112未保留；生产permit/69基线/原子32序号流程与真实现场CLI仍待实现。以下为历史。

最新离线实现（2026-10-18）：[两轮SDK驱动与联合回执](docs/A23_TWO_EPOCH_SDK_DRIVER.md)完成编译与模型验证。
独立SDK模式、未使用lease接管、原生回调时钟、逐轮持久保存及联合资源门禁；旧329来源保持。
两轮保存后需至少250ms观察；迟到回调、额外请求会撤销完整结果，已提交回执也会stale；不声称回调排空。
42原生场景、20坏归档、12项检查通过ASan/UBSan；搬移336来源后独立重建与分类一致。
仅正常及队列延迟25ms两个注入模型完整，其余40拒绝；SDK来源字段保留，模型标记不认证真实物理来源。
新增7项共336，23保护项及故障owner保持；USB/SD/真实SDK/固件构建/发行/序号保留均0。
65保持已回收/remaining0，81..112未保留；真实映射、设备双轮/trace及连续稳定性未验证。
下一项离线准备专用入口/build与进程环境、等待及最终回执，再接69基线与32序号流程；不能直接实测。以下为历史。

最新离线实现（2026-10-18）：[两轮SDK资源能力](docs/A23_PAIRED_SDK_RESOURCES.md)完成编译与模型验证。
独立模拟/休眠SDK provider：一次准备、三次身份核验、一个pipe、四次分配；部分失败安全清理，通知/不确定性保留。
进入运行后不destroy/release；拒绝额外ISO/BURST/STATUS，旧离线协调器继续拒绝SDK资源，未改开关。
40准备+23运行场景、12坏回执、11项检查通过ASan/UBSan；7个SDK accessor方法体绑定旧实现，搬移重建一致。
修正error=NULL漏错和BOOL编码；联合核验拒绝上层complete但资源已异常的第三次请求/额外STATUS。
323旧来源保持，新增6项后329，23保护项及故障owner保持；本轮USB/SD/真实SDK/发行/保留均0。
采用编译+注入模型替代现场操作，SDK实际映射与执行驱动尚未验证/实现；65已回收/remaining0，81..112未保留。
下一项离线实现独立SDK执行驱动/联合回执，再接专用build、69基线及32序号流程；不能直接实测。以下为历史。

最新离线实现（2026-10-18）：[有限两轮接收协调器与归档](docs/A23_TWO_EPOCH_RECEIVER.md)完成。
独立能力及两个one-shot owner，共享资源与4块存储保留；最多2次ISO/BURST、1次异步abort。
每轮重采样lead32，核对完整事务/载荷及STATUS/URB/ISO7；第一轮fsync/读回及日志保存后才准入第二轮。
原子回调入口拦截旧代/重复/错误指针；文件已提交而journal失败或旧回调到达，也不确认、不续第二轮。
47个原生场景、20份坏归档（11份重算哈希）及10项检查通过ASan/UBSan；搬移重建/重分析一致。
正常离线模型81..112共6144字节；仅1份完整，46份其他模型与20坏件拒绝，非真实设备链。
317旧来源保持，新增6项后323；23保护项及故障owner保持，本轮USB/SD/SDK/发行/保留均0。
本版仅接受offlineSimulation；SDK provider、完整设备trace/URB服务及正式69基线流程尚待实现。
65仍已回收/remaining0，81..112未保留；下一项离线接入独立SDK资源/执行驱动，不能直接实测。以下为历史。

最新离线研究（2026-10-18）：[第二次发布与事件代际](docs/A23_REARM_GENERATIONS.md)完成。
绑定最新69原件的同一905字节IPS，执行实际ARM64补丁；247起始槽双轮通过，16错误位置均保留拒绝。
第16轮注入第一轮旧ED可占9个完成位，再7个新事件即可到原完成入口；这是注入反例，未观察真实迟到。
6个原生owner/存储场景及9项检查通过ASan/UBSan；搬移后全部重放一致，正式重放未读原实验目录。
主机4块活跃Foundation存储分离、会话保留；未测试SDK映射分配或完整URB服务，当前lease仍一次。
313既有来源保持，新增3文件并纳入test_patch.py后317，23保护项及故障owner保持。
本轮USB/SD/真实SDK/固件构建/发行/序号保留均0；65保持已回收/remaining0，81..112未保留。
下一项离线实现独立两轮会话/回执/收集及69基线约束；设备包复用和连续流仍未验证。以下为历史。

最新离线研究（2026-10-18）：[多突发准入与两轮模型](docs/A23_MULTIBURST_ADMISSION.md)已完成。
确认当前部署V2为256条trace/32个身份槽；保留旧V1混用的拒绝材料，未修改既有候选。
273个原生服务模型、8个协调器模型及25项专项检查通过ASan/UBSan；搬移后独立重建20场景一致。
18条注入前缀下，两轮完整三步用150条，共享STATUS两轮用127条；共享五轮恰好256，第六轮拒绝。
主机仍全零首次STATUS且一次提交，不能直接循环旧65入口；终结失败可复用内存不表示上一轮成功。
先设计独立两轮串行协议：逐轮核对、保存后继续，独立存储；超时/错配/保存失败均停止保留。
310既有来源及23保护文件保持，新增3项后313；本轮USB/SD/真实SDK/发行/序号保留均0。
81..112仅模型数值，未保留或获实测授权；是否可复用现设备包及连续流仍待审查。以下为现场与历史状态。

最新实测与回收（2026-10-18）：[序号65成功与设备原件](docs/A23_CONTEXT65_FIRST_LIVE.md)已完成。
已授权的唯一一次在沙箱外通过父/native环境检查；SDK初始化成功，ISO/BURST各一次，
主机收到65..80共16×192=3072字节，960事务status均0、无abort、exit0。
只读保存69原件，14:41:59+08安全弹出，四部署项匹配；新增两组EXE3/primary及两份LCP1，
62旧原件保持，仅logfile变化；8份ERPT不变、无新增ERPT。11份EXE3仅新增806843与本次匹配，
9旧原件和另一新增原件均拒绝；五份收集移动重分析保持，完整链1份，错误/缺失对照不完整。
310代码来源、旧49及修复owner保持；65..80永久保留，remaining=0，device_log_pending=false/recovered=true。
下一项离线研究多突发/连续流及下一序号候选；不补次、不发新测试。根因、来源认证与持续稳定性未确认。
当前设备已关机、SD已安全弹出，无需新的现场操作。以下为历史状态。

最新离线基线（2026-10-18）：[63份基线与独立一次流程](docs/A23_CONTEXT65_BASELINE63.md)已验证。
保留两版logfile及旧59门禁，新版绑定确切63份原件、失败修复作业和仍保留的占用。
最终54项专项测试、15组静态收集及移动重分析通过；303既有来源保持，新增7项后310。
真实63份回执通过新版只读预览，旧发行器继续拒绝；接收器build8/receipt8、设备包与预算保持。
本轮SD/USB/真实SDK/正式发行均0，65..80未保留，remaining=0；旧49记录及故障owner未改。
SD沿用14:11:50+08已弹出状态，标记已存在且四项匹配，无需继续修复或为修复重新插卡。
下一步须明确新测试指令及现场装卡/关机/接线确认，才可重新预览、发行并先WAITING再开机。
当前仅完成离线准备，不证明SDK初始化成功、物理同次关联、根因或连续流。以下为历史状态。

最新现场核验（2026-10-18）：[标记已存在与63份新基线](docs/A23_CONTEXT65_FLAG_CARD_LIVE.md)。
用户明确实际修复及关机/接卡后，只读核验发现卡已变化，原作业按门禁失败，未写标记。
独立只读保存63份原件，14:11:50+08安全弹出；正确空boot2.flag已存在、四部署项匹配。
新增标记+一组EXE3/primary+一份LCP1；logfile变化，其余58原件及8份ERPT保持，未发新USB测试。
旧65发行器仍因旧59日志契约拒绝，不补次、不改旧49记录、不释放故障占用；无需继续修复标记。
只读检查器16项/10作业验证通过，301来源保持、总303；下一项离线重建63份基线绑定。
当前SD已弹出，65..80未保留或发行，根因与物理同次关联未认证。以下为历史状态。

最新物理卡适配器（2026-10-18）：[两阶段标记修复入口](docs/A23_CONTEXT65_FLAG_CARD.md)离线完成。
36项最终测试、8组假磁盘审计通过；298旧来源保持，新增3项后301，以r3审查/r1验证为准。
先只读备份并弹出，重新插卡确认后才排他创建空标记，再只读回收/弹出；支持磁盘重新编号。
跨作业介质锁与故障保留占用阻止并发和自动重试；超时/未知进程不杀、不续命令、不封存活跃日志。
正式修复作业仅已准备，未领取、未查磁盘；真实最新基线仍缺标记，65..80未保留或发行。
实际修复先待明确指令及完全关机/接卡确认，备份弹出后另待重新插卡确认；新测试另需指令。
本轮真实SD/USB/SDK均0，49次数及原拒绝回执保持；续接context65-pending和flag-card-ready。以下为历史状态。

最新离线修复方案（2026-10-18）：[boot2.flag有限修复及模型](docs/A23_CONTEXT65_FLAG_REPAIR.md)完成。
精确新增一个0字节标记，59原件（含._boot2.flag和旧临时材料）及其余三部署项必须逐字节保持。
26项专项测试、6组成功/故障审计及移动归档重分析通过；295既有来源保持，新增3项后298。
候选只有/private/tmp的DirectoryCard写入模型，没有物理卡写入入口；模型回执被正式预览拒绝。
真实最新快照仍缺标记，65..80未保留/发行，49次数0及原拒绝回执保持；本轮真实USB/SD/SDK均0。
下一项离线接入并审查实际单文件适配器与挂载/故障模型；实际修复和新测试各待明确指令。
续接private/analysis/A23-context65-pending.json及flag-repair计划/审查/验证。以下为历史状态。

最新一次流程（2026-10-18）：[序号65一次流程与最新基线](docs/A23_CONTEXT65_READINESS.md)已完成离线验证。
独立预览/发行/消费/只读恢复/收集入口绑定第8代材料；先持久保留再写新记录，启动前先消费，
永久排他锁与不可变调用摘要拒绝复制或补次；只容许本次材料新增，其他378份历史继续冻结核验。
37项最终测试、12组静态归档及移动重分析通过；287旧来源保持，新增8项后295，以r3审查/r1验证为准。
正式预览仍因15:49最新快照缺boot2.flag被拒绝，不能回退13:41成功回执；65..80未保留、未发行。
49记录仍次数0、原件已保存且已弹出，部署回执拒绝；无新真实SDK对象、USB请求、SD访问或写卡。
下一项离线准备有限标记修复与回读核验方案；实际修复及新测试各待明确指令。
续接private/analysis/A23-context65-pending.json。以下为历史状态。

最新离线候选（2026-10-17）：[序号65与执行环境证据](docs/A23_CONTEXT65_RECEIVER.md)完成。
378份历史材料含49失败run、正式保留及记录，支持下一候选65..80；尚未保留、发行或实测。
第8代接收器/第4版计划保持原设备包与lead32预算，创建通知端口前保存并检查进程环境，
上下文摘要绑定process claim及收集判读；同一代码的只读自检在默认沙箱返回1、沙箱外返回0。
12等待/34协调器模型、9回执、9上下文门禁、16组静态收集及18专项/旧序号测试通过。
旧工作流38项中37通过，1个签发前sequence_reserved=false断言与49已保留冲突；原结果保持，
当前状态补查确认预览不写记录、不改保留文件。272来源保持，新增15项后287；r3审查/r2验证为准。
下一项独立一次预览/发行/恢复入口及最新基线约束；boot2.flag仍缺失，本轮USB/SD/签发均0。
续接private/analysis/A23-context65-pending.json；49..64仍保留且次数0，设备回执仍拒绝。以下为历史状态。

最新离线研究（2026-10-17）：[SDK初始化与启动标记审查](docs/A23_SDK_INIT_ENVIRONMENT.md)完成。
原始命令证实两次lead32成功请求沙箱外执行，序号49使用默认沙箱；这是差异线索，尚未确认因果。
当前framework四种父类失败注入均被覆盖为0xE00002C9/Failed [super init]，底层NSError丢失；
ASan/UBSan通过，原父类调用0、真实SDK初始化对象0（模型分配4个实例）、USB/SD均0。
官方参考启动代码按确切boot2.flag路径检查，已审阅启动路径不消费标记；缺失来源仍未确认。
29文件审查封存、407条哈希/结构检查通过，272来源及旧保护项保持，49..64仍保留且次数0。
下一项离线准备新序号候选和执行环境证据；未来实测前须独立处理启动标记及四文件基线。
本轮未签发、写卡或重试；已取得59原件，部署核验仍失败，recovered=false不表示待读卡。以下为历史状态。

最新回收（2026-10-17）：[序号49首次测试](docs/A23_SEQUENCE_FIRST_LIVE.md)设备原件已只读保存并弹出。
保存59原件，15:49:12+08安全弹出；相对51原件新增三组EXE3/primary和三份LCP1，无新增ERPT，既有8份保持。
发现boot2.flag缺失，其余三项部署文件一致；回收门禁保留deployment_files_match=false，未标为全部通过。
新增三组日志均有保存及main_return，只见010b000001000000，未见序号49 BURST/ISO post；不唯一归属本次主机。
主机仍为SDK初始化失败/未提交ISO，49..64已保留、记录remaining0，不重试。记录card_snapshot_saved=true、
device_log_pending=false、recovered=false/recovery_receipt_accepted=false，表示原件已取得但部署核验未通过。
下一项离线核查SDK初始化的执行环境与启动标记变化；本次不改卡、不重新开机测试。以下为历史状态。

最新实测（2026-10-17）：[序号49首次测试](docs/A23_SEQUENCE_FIRST_LIVE.md)在SDK初始化阶段停止。
WAITING后收到新的HS接口并领取一次权限，但IOUSBHostInterface初始化报0xE00002C9/Failed [super init]。
没有进入SDK采集、没有提交ISO或发送BURST；这不是序号49载荷实测结果，不能评价新序号方案。
49..64已永久保留，记录failed_no_retry/remaining0，接收器结束、等待器关闭，无重试。
主机日志及272来源复核已封存；设备原件待读卡。下一步保持开机40秒后完全关机接卡，只读回收并弹出。
续接private/analysis/A23-sequence-pending.json及first-live-pending-recovery；此前“尚未保留”均为历史状态。

最新一次流程（2026-10-17）：[序号49的预览、发行和只读回收](docs/A23_SEQUENCE_READINESS.md)已完成离线验证。
新增全局持久保留及独立入口；先保留49..64，再排他写新记录，复制、重复、写入失败均不补次。
77项联合检查通过；29组静态收集及既有46份native模型完成复核，坏件/歧义保持失败。
266既有来源保持，新增6项后272；以r6审查、r4验证及ready-preview为准。
实际SDK对象、USB请求、SD访问均0；正式序号保留目录和新记录均不存在，候选仍0次。
新运行使用A-sequence-waiting-*并由全局保留跟踪；旧A-A23-*的364文件历史范围继续冻结核验。
设备包和lead32/4-2-2ms预算保持，无需重写卡；最新保存回执仍为51原件、13:41安全弹出。
下一步确认装卡接线且完全关机，再明确开始一次新测试；先WAITING再开机，不等SysDVR初始化。
当前实机状态仍repeat1_recovered；以下为历史语境，旧“尚未接入”不代表本段状态。

最新主机候选（2026-10-17）：[历史范围与序号绑定](docs/A23_SEQUENCE_RECEIVER.md)离线完成。
复核364历史文件见0..31，保守选择49..64；上一轮17仅模型建议。新第7代构建/第3版计划绑定49及历史摘要，
实际请求、日志、metadata、STATUS和载荷判读一致，同设备六材料及lead32/4-2-2ms预算保持。
12等待/34协调器模型、9回执、6收集场景及39项相关检查通过；两份已知旧成功原件拒绝。
临时持久保留模型覆盖锁、截断、锚点和写入失败；尚未接入正式发行，未分配项目序号或次数。
255旧来源保持，新增11项后266；r5审查/r2验证为准，r1..r4失败输出保留，无USB或读写卡。
下一项独立一次预览/发行/恢复流程及边界验证，不可用旧lead32发行器或旧次数。
当前repeat1已回收、SD仍13:41弹出；续接pending的独立候选引用。以下为历史语境。

最新离线研究（2026-10-17）：[跨端关联及起始序号可行性](docs/A23_SEQUENCE_WITNESS.md)完成。
2主机×5设备原件共10组，两个成功原件互换均通过有限比较，确认当前缺少独有的主机会话绑定。
冻结处理函数的14个注入服务场景及8项专项检查通过；现有设备C路径可传播wValue到trace/STATUS/16包。
优先准备不同起始序号的新主机候选，保留lead32及同设备包；模型提出17但未保留、未证明全历史唯一。
旧接收器/判读器仍固定1，不能直接复用或放宽；下一步补齐历史保留、版本绑定及旧成功原件拒绝。
251既有来源保持，新增4项后研究闭包255；无新接收器构建、发行、USB或读写卡，全部现有记录仍0次。
repeat1已回收，SD仍13:41已弹出；续接pending及研究引用。以下为历史语境。

最新回收（2026-10-17）：[lead32独立复现及设备原件](docs/A23_LEAD32_REPEAT1_LIVE.md)完成。
只读保存51原件，四部署文件匹配，13:41:16+08安全弹出；新增两组EXE3/primary及两份LCP1，
没有新增ERPT，既有8份全部字节保持。新增383d/4d7b组合所供链完整，保存和main_return有记录。
两次lead32均16×192字节准确、URB/ISO7报告完成；支持窗口覆盖，未认证根因或长时稳定。
额外静态旧成功原件对照也得到所供链完整，确认现有SETUP/状态比较不提供唯一跨端会话绑定；
旧原件从不当作本次证据。下一项优先离线审查会话绑定与旧记录误配，再设计持续流。
repeat1 remaining0、device_log_pending=false/recovered=true；pending=repeat1_recovered。
251来源及全部旧保护项保持，无新测试授权或现场操作需求。下方“待读卡”等均为历史状态。

最新独立复现（2026-10-17）：[lead32主机再次成功，设备原件待读卡](docs/A23_LEAD32_REPEAT1_LIVE.md)。
用户明确新开始后签发repeat1；WAITING先于开机，单次ISO/触发，16×192字节准确、连续索引8..23；
URB387/status3、ISO7 terminal1/FFFF/3072，控制0.504667ms、ISO151.421750ms，无重试。
这是第二个主机成功样本，本次EXE3/LCP1与保存/新增ERPT仍未核对；不复用前次设备文件。
记录captured_logs_pending/remaining0，device_log_pending=true/recovered=false。已请用户开机40秒后
完全关机接卡，收到“已接好”才只读回收并弹出。续接repeat1-live-pending-recovery.json；job仅脚本，
当前没有新快照，不再发USB测试。251来源及全部旧保护项保持。以下为历史语境。

最新研究准备（2026-10-17）：[同参数独立复现及ERPT比较](docs/A23_LEAD32_REPEAT_PREPARATION.md)完成。
8份ERPT含7份字节保持的旧报告及1份新增，均为870字节/28字段/2162-0004，缺少进程和会话关联；
该错误码并非本次首次出现，仍未归因。官方参考中的标志默认值及跨时钟限制已记录。
同固件/接收器/预算和最新45原件基线已核验，预览与离线dry-run保持0次；repeat1正式记录不存在。
下一项现场确认装卡接线且完全关机，明确开始后另签新记录，先WAITING再开机；本轮没有新采集或读写卡。
此前成功样本及旧记录均保持，续接pending的single_burst_recovered及新增准备引用。

最新实测及回收（2026-10-17）：[lead32首次有效实测](docs/A23_LEAD32_FIRST_LIVE.md)完成。
一次ISO收到16×192=3072字节，连续有效索引4..19、内容和序号全匹配；URB387/status3、
ISO7 terminal1/bitmapFFFF/actual3072。显式EXE3/primary/LCP1所供链完整，保存和main_return有记录。
首次等待超时且未开机/未提交ISO；另经明确授权的新记录才执行本次成功采集，不是自动重试。
只读回收45原件，四部署文件匹配，13:15:07+08安全弹出；全部新旧日志保留。
另有新增ErrorCode2162-0004报告，缺少进程及会话关联，来源未定；稳定性与独立根因未认证。
窗口覆盖假设获支持，优先设计同参数独立复现并查清错误报告；不直接扩展到连续UVC/UAC。
251来源及旧保护项保持；两条lead32记录均remaining0，无补次。有效记录recovered=true、
device_log_pending=false；续接 `private/analysis/A23-lead32-pending.json`，stage=single_burst_recovered。
任何新实测需新的明确开始指令及新记录。以下各段为当时历史状态，不覆盖本段。

最新离线入口（2026-10-17）：[lead32判读、收集与一次流程](docs/A23_LEAD32_READINESS.md)完成。
独立判读第2版计划/32帧/4-2-2ms预算，复核既有46份native模型并跑通28组静态收集场景；
缺件、坏CRC、多日志与旧/混合回执均保留失败或歧义，不提升物理认证。80项检查全过。
一次入口默认只预览，绑定新接收器、工作流251来源、同一设备包及部署/只读回收/弹出回执；
消费后才启动，失败不补次，未决进程不强杀。241既有来源及全部旧保护项保持。
预览及dry-run均0次；正式lead32记录不存在、未启动接收器、无读写卡或USB请求。
下一次明确开始指令后才能签发，并先主机WAITING再fresh开机CFW；本次主机改动无需重写设备包。
续接 `private/analysis/A23-lead32-pending.json`。以下为历史语境。

最新离线候选（2026-10-17）：[lead32接收器](docs/A23_LEAD32_RECEIVER.md)完成构建。
主机窗口提前为current+32；帧样本/入队/触发预算为4/2/2ms，触发年龄8ms、控制16ms、
名义reserve8ms。第6代record/receipt与第2版计划绑定同一path-span六设备材料，未改固件。
12等待流程、34SDK协调器、11精确边界、8回执场景及59项检查通过；旧64判读器拒绝新计划。
235既有来源保持，新增6项后241来源；构建265条/审查735条封存，正式次数仍0，无采集。
下一项独立lead32判读/收集器和一次预览入口，旧5代工具不可直接复用；还未安排实机验证。
续接 `private/analysis/A23-lead32-pending.json`，不补次、不重试，SD仍为上次已弹出状态。
以下为历史语境。

最新离线结论（2026-10-17）：[ISO错误保留与窗口审查](docs/A23_ISO_RETENTION_WINDOW.md)完成。
三次SDK样本均为首TD CC23、bitmap0/actual0；实际补丁会锁存错误并跳过正常completion，
可解释status2/active/pending1及RETAINED。全部22条IPS重建匹配回收卡，事件原始count192
不能当作已传输字节。条件帧号比较中，host首帧均比设备目标帧晚31帧，参考槽-248；
这是窗口错位假设，未独立对齐两端帧域、未确认设备CC23语义或总线根因。
47项离线检查全过，233既有来源保持，新增判读器/测试后235来源；记录仍零次数且已回收。
下一项准备host lead32独立候选及配套预算/绑定/边界验证，不直接复用旧64计划或放宽判读。
本轮无新接收器构建/签发、读写卡或USB请求，SD仍为上次已弹出状态。以下为历史语境。

最新回收（2026-10-17）：[路径缓冲候选首次测试](docs/A23_PATH_SPAN_FIRST_LIVE.md)设备原件已取得。
00:21:19+08只读回收38个原件并安全弹出；diagnostic4400字节、EXE3 5456字节均完整，
两次文件create返回0，保存报告成功，本次两处未再出现0xD401。接口2触发、ISO post和ACK
均有记录；ISO请求387在30秒窗口结束仍active/status2/pending1，主机960 actual仍全0。
四份LCP1全部保留；显式上下文关联的一份有27条，另一新文件仅启动4条，不能归入同次执行。
材料比较自洽但完整链标记仍false（host_observation_complete=false，静默轮询历史不完整），
不得据此认证物理同次执行、内核根因或USB成功。233来源及全部旧保护项保持。
记录failed_no_retry/remaining0，device_log_pending=false/recovered=true；不补次、不重试。
下一项离线检查ISO端点与完成报告路径，区分提交接受、状态报告与实际传输；当前无需再开机。
续接见 `private/analysis/A23-path-span-first-live-device-analysis-20261017` 及恢复状态JSON。
以下为历史语境；此前“待读卡/签发前”的段落不代表当前状态。

最新实测：[路径缓冲候选首次测试](docs/A23_PATH_SPAN_FIRST_LIVE.md)主机部分完成。
用户明确“开始测试”后签发/消费一次新记录，WAITING先于新HS到达。控制0.390292ms /
ISO183.346958ms完成，无超时/abort，但960 actual全0、184320字节全零；STATUS
seq0/state0→seq1/state4，仍failed_no_retry/remaining0，无重试，设备文件保存结果待读卡。
主机18条及独立分析封存；已请用户再开机40秒后完全关机取卡接Mac，尚待“已接好”。
续接读取 `private/analysis/A23-path-span-first-live-pending-recovery.json`：job只含未执行
只读回收脚本，不是已读卡回执。确认接卡后动态识别、只读回收全部原件并安全弹出；
保留两份旧LCP1，不自动挑选，不再发USB请求。以下为历史语境。

最新现场部署：[路径缓冲候选部署](docs/A23_PATH_SPAN_CARD_DEPLOYMENT.md)完成。
用户“已接好”后动态识别同一SD，备份/读回34个选取原件，再仅替换NSP为b54747… /
117024字节；四文件读回匹配，其他选取原件保持本次备份字节，22:54:35+08安全弹出。
新备份35条/部署9条/操作7条封存，第5代入口已核验真实新包和整盘弹出回执。
替换前已存在两份旧recipe的LCP1，全部保留，不认证新主机run；不可自动挑选或删除。
233来源/141项回归封存和旧记录重核保持；正式path-span一次记录仍不存在、次数0，
没有接收器启动/USB诊断或新候选执行。装卡后先保持关机，下一次明确开始诊断时先
签发新一次记录并主机WAITING，再提示开机。错误消失与ISO根因仍未验证。以下为历史语境。

最新离线入口：[新路径候选部署与一次诊断入口](docs/A23_PATH_SPAN_READINESS.md)完成。
独立卡工具/第5代签发与执行工作流绑定新包和四入口来源，默认仅预览；需新包读回/
同盘安全弹出回执才可签发，先消费再启动，不补次或重试。模型回执拒绝正式签发。
22个文件/失败/辅助文件场景及141相关回归全过，233来源含旧226保持；已知辅助文件仅放行本次确切
名称和完整封存样本，原件均保持。卡上旧LCP1保留，回收不得自动挑选多个候选。
审查521条封存，预览/dry-run均0次无采集；当前正式path-span一次记录不存在，两旧
现场记录仍failed_no_retry/remaining0。下一项关机接卡后新快照/基线核验，再按部署
指令写新包；取得真实回执后另开始唯一一次诊断。实机错误消失及ISO根因仍未验证。
以下为历史语境。

最新离线材料：[路径候选接收器、判读与部署包](docs/A23_PATH_SPAN_MATERIALS.md)完成。
第5代独立schema绑定同一372695… recipe / 9fe1e5… ELF及六材料，旧回执/材料拒绝；
31收集场景/12等待模型、22新专项及79相关回归通过。缺失/部分/多个原件保持，
内容自洽不认证物理链或自身提交。226来源含旧219保持，接收器构建243条/审查1564条封存。
新NSP b54747… /117024字节完成转换与核验；四文件新树及bca717…生命周期回退树22条
封存，基线匹配最近14:31只读快照。无新正式设备ELF、写卡、签发或USB诊断，离线0次，
两份现场记录仍failed_no_retry/remaining0。下一项绑定新材料的独立卡工具和一次入口；
旧生命周期工具仍指旧材料，不能直接用于本次新包。错误消失与ISO根因仍未确认。
以下为历史语境。

最新离线候选：[完整路径缓冲设备候选](docs/A23_PATH_SPAN_DEVICE_CANDIDATE.md)完成。
隔离修正五条诊断保存路径为独立、完整清零的769字节静态对象，最终ELF确认均在BSS；
BSS增加4096字节，main/NPDM栈请求保持，diagnostic帧656→544、EXE3帧496→400。
14单元ARM链接/严格格式检查、46个实际适配源码模型和57项相关回归通过；模型create/
open读取全部SDK跨度并核零尾。REL2保存入口未链接，不冒称实际机器路径已回放。
219来源含旧217保持，仅六生成文件变化；新recipe372695… / ELF9fe1e5…，审查193条封存。
设备错误消失与ISO根因尚未认证。本轮无新接收器绑定/NSP/部署/签发/USB诊断；两份
现场记录仍failed_no_retry/remaining0。下一项新材料接收器/判读绑定，再准备部署入口；
旧接收器、回执及次数不能复用。以下为历史语境。

最新离线研究：[文件创建路径缓冲审查](docs/A23_FS_PATH_SPAN.md)完成。
实际已部署 ELF 的 fsFsCreateFile 使用调用者路径地址提交 769 字节；两条失败路径
仅分配 96 字节，机器码输入范围均为 main 入口 SP 的 [-480,+289)。静态 LCP1 路径
也仅64字节，但后续 SDK 跨度落在 ELF RW 段；成功不能证明对象容量正确。
新增完整清零路径暂存原型，保护页模型及全部769种长度通过，ARM原型对象/48字节
帧核验；8专项及50相关回归全过，217来源含旧213保持。审查16条封存。
现场映射未测、未复现 Switch 内核错误，不能宣称已确认 0xD401 或 ISO 根因。
下一项隔离接入所有 SDK 路径、重核机器码/空间/持栈并绑定新材料；本轮无新设备
ELF/NSP、部署、签发或 USB 诊断，两份现场记录仍 failed_no_retry/remaining0。
以下为历史语境。

最新实测与回收：[生命周期首次实测](docs/A23_LIFECYCLE_FIRST_LIVE.md)完成。
一次新记录、主机 WAITING 先于新开机 HS 到达；控制 0.464875ms / ISO 183.1795ms
完成，无超时/abort，但 960 actual 全0、184320字节全零，仍 failed_no_retry/remaining0。
只读回收首次取得 3968 字节 LCP1：27 条连续有效记录，两个 join 返回0、SD打开0，
diagnostic/EXE3 创建均返回 0xD401（本机 SDK: InvalidMemoryState），无 EXE3/主结果。
内容自洽不认证完整物理链、自身提交或最后执行点；ISO 根因仍未知，未重试。
原件35条/缺证收集28条封存，14:31:48+08安全弹出，旧票据/记录保持。
下一步离线对比成功 LCP1 预创建与失败两路创建的实际 SDK/IPC、内存及调用条件，
先取得可区分证据，不直接改超时或再次实测。卡可装回但先保持关机。以下为历史语境。

最新现场结果：[生命周期候选部署](docs/A23_LIFECYCLE_CARD_DEPLOYMENT.md)完成。
首次写入因自动出现的辅助文件在替换前停止，原件和旧程序保持，现场已只读封存；
用户重新接卡后，独立修正版严格匹配本次辅助文件及封存样本，321 相关回归全过。
同一 SD 新备份 32 原件后，仅替换 NSP 为 bca717… / 116864 字节，四文件读回匹配，
其余选取原件（含上次失败临时文件）保持；14:25:46+08 安全弹出并确认挂载消失。
213 来源含旧 210 保持，58 旧材料 10086 条重核；新部署/备份/操作回执均已封存。
没有签发或启动实机，旧记录仍 failed_no_retry/remaining0，新正式一次记录不存在。
装卡后先保持关机；下一次明确开始诊断时先新记录及主机 WAITING，再提示开机。
本次只验证文件部署路径，设备执行、文件服务和 ISO 根因仍未知。以下为历史语境。

最新现场结果：[14:04 只读读卡](docs/A23_LIFECYCLE_CARD_READ.md)完成。
目标 UUID 核对后只读回收 30 个原件，四部署文件仍匹配旧 quiet，21 报告保持；
829 字节日志仅模块基地址变化，仍止于 UVC device initialized，无任何 ep0-*。
原件 32 条/操作 12 条封存，14:04:52+08 安全弹出并确认挂载消失。只读回收工具
首次实际跑通；无写卡、部署、签发或 USB 诊断，210 来源/生产/旧记录保持，当前
仍 failed_no_retry/remaining0。没有绑定成新的设备 run，原根因未知。若继续部署新
候选，须重新接卡核验并在部署授权范围执行；本次读卡任务已完成。以下为历史语境。

最新离线演练：[生命周期部署与原件回收工具](docs/A23_LIFECYCLE_CARD_FILES.md)完成。
新增显式卷/分区核验、原件快照、电脑副本/四文件备份读回、仅替换 NSP、读回/同盘
弹出后生成回执；写入失败不自动回滚或重试。只读回收保留缺失/部分/多个 LCP1 和
EXE3；副本可移动重核，摘要固定排序。模型回执用独立 schema，正式签发入口拒绝。
210 来源含旧 207 保持，16 场景/32 新增及 309 相关回归通过、0 跳过；342 条审查
封存，50 旧封存 9441 条重核。真实卷适配仅模拟系统返回值测试，无实际读卡、写卡、
部署、正式签发或采集；旧现场记录仍 failed_no_retry/remaining0，正式材料身份保持。
下一步现场完全关机/断电后接卡，先只读识别与原件回收，再核实际基线和备份；实际
部署按授权执行，取得新包读回/弹出回执后才签发一次测试。原根因仍未知。
以下为历史语境。

最新离线准备：[生命周期候选部署包与一次入口](docs/A23_LIFECYCLE_PREPARATION.md)完成。
同一 ELF 转换的新 NSP bca717…/116864 字节，段/BSS/build ID/NPDM/IPS 核验；四文件
部署树及最近回收的 quiet 回退树已封存。新入口绑定第 4 代接收器/六材料、验证与
工作流摘要，签发须新包读回/对应磁盘弹出回执；默认预览，消费先于启动，失败不退次。
207 来源含旧 202 保持，18 新增/277 相关回归通过，目标磁盘补查后 18 项再次通过；
17 组函数文件服务/持栈复核，真实服务、耗时和内核栈预算仍未知。包 22 条/最终准备
10 条封存，无实际卡访问、部署、正式签发、接收器采集或实机；旧现场记录仍
failed_no_retry/remaining0。下一项可离线演练的新包部署/原件回收工具及失败处理，
再进入现场配合；原根因未知。以下为历史语境。

最新离线研究：[生命周期候选接收器与回收判读](docs/A23_LIFECYCLE_RECEIVER.md)完成。
新第 4 代接收器绑定同一 39b109… recipe / 737ad5… ELF、NPDM、配置及六材料；旧
回执和变动材料拒绝。原件收集允许 EXE3 缺失，分开材料绑定、EXE3 链、LCP1 context
关联和完整条件；损坏前缀保留、多文件不自动选择，内容自洽不认证物理来源或自身提交。
202 来源含旧 195 保持，31 收集/12 等待模型、19 新增/259 相关回归通过、0 跳过；
审查 1540 条/接收器构建 219 条封存，44 旧封存 7840 条保持。无设备重编译、NSP、
签发、部署或实机；旧现场记录仍 failed_no_retry/remaining0。下一项独立第 4 代现场
记录/执行入口、部署包与回收顺序，以及设备栈/文件服务限制审查；原根因未知。
以下为历史语境。

最新离线研究：[生命周期记录设备候选](docs/A23_LIFECYCLE_DEVICE_CANDIDATE.md)已完成隔离接入。
USB 初始化前排他预创建并显式清零/读回 3968 字节文件，准备失败不启动 USB；main
循环内无新增写，退出后记录双 join、身份和两路保存阶段，保持原保留/清理决策。
195 来源含旧 189 保持，8 个生成文件变化；46 native 模型、12 新增/240 相关回归全过，
14 单元 ARM 链接及严格格式检查通过，新 ELF 737ad5… / recipe 39b109…；审查 195 条封存。
逐函数持栈已核，实际内核栈预算、完整调用链及真实文件服务/耗时仍未认证。无新 NSP、
接收器绑定、部署或实机，卡上旧 quiet 和 failed_no_retry/remaining0 记录保持。
下一项离线贯通新材料绑定、LCP1 回收及 EXE3 存在/缺失/损坏判读；最后有效槽不证明
实际最后执行点，原根因未知。以下为历史语境。

最新离线研究：[退出链与阶段记录原型](docs/A23_LIFECYCLE_CAPSULE_PROTOTYPE.md)完成。
同一quiet ELF六函数/十源码接入点重核；确认设备state4为RETAINED，g_running已是
atomic，无文件不定位具体原因。新增LCP1主线程记录原型：3968字节/40槽/24阶段，
静默运行循环内禁止附加写，双方join成功前拒绝context/owner保存阶段；失败后停写、
不补槽/重试，不授予清理或提交证明。35native模型/11新增及228相关回归全过、0跳过。
189来源含旧184保持，原型审查82条封存。未接入main/真实SDK适配，无新ARM/NSP/
接收器/部署或实机；卡上quiet版本与已消费记录failed_no_retry/remaining0不变。
下一项隔离接入USB初始化前的预创建、main循环退出后的阶段点及SD打开/创建适配，
验证真实函数回放、新ELF/持栈和服务生命周期，再另做新recipe/接收器绑定。不能把
最后有效槽当实际最后执行点，原根因仍未知。以下为历史语境。

最新回收：[quiet首次实测读卡结果](docs/A23_QUIET_FIRST_LIVE_RECOVERY.md)。同一SD只读
回收，四部署文件匹配，21报告不变；829字节日志止于UVC device initialized，但根
目录没有任何ep0-*，不能取得EXE3/trace或认证物理同run。卡原件34条/缺证收集32条
已封存；六材料/接收器/回执/进程及SDK claim绑定校验通过，完整设备链仍不成立。
10-16 02:29:23+08安全弹出并确认挂载消失，本轮写卡0/USB诊断0，无新程序或重试。
新记录仅补回收/收集路径，仍failed_no_retry/remaining0；旧三票据/三离线记录不改。
主机控制完成但ISO actual全0的失败保持。不能由缺文件断言某个join/FS失败或请求未到。
下一项优先设计window stop→双join→exporter/导出→SD打开/创建/提交的最小可观察证据，
保持静默与所有权约束，不重复实测或先改超时。原根因未知。以下为历史语境。

最新实测：[quiet首次实测主机结果](docs/A23_QUIET_FIRST_LIVE_HOST.md)。用户“开始”授权后
仅签发/消费一次新记录，主机WAITING先于唯一HS到达，交接与一次请求链完成。控制
约0.3565ms完成、ISO约183.294ms回调，无超时/abort；但960项actual全0、184320字节
缓冲全零，STATUS从seq0/state0到seq1/state4，设备requested3072/transferred0/urb_status2。
接收器退出0不等于载荷验收；结果failed_no_retry/remaining0，未重试。旧三票据/三
离线记录不改，已部署quiet身份不变。主机18条/独立分析6条封存，设备EXE3/trace待
回收，原根因未确认。run目录UTC标识20261015-181041，客户端为10-16 02:10:41。
已提示用户完全关机、确认断电后取卡插Mac，作为受控回收；主机结束不证明设备保存
或退出。下一步只读回收同nonce原文件/部分文件和日志，关联本次run，不再请求USB。
以下为历史语境。

最新续接：[quiet候选读卡与部署](docs/A23_QUIET_CARD_DEPLOYMENT.md)完成：按“读卡，部署
文件”核验预期SD UUID与旧A23四文件，先回收1143字节日志/21报告及原目录，再仅更新
exefs.nsp为111234字节候选813142…；四文件读回匹配，其余三文件/日志/报告不变。
10-16 01:55:52+08安全弹出disk4并确认挂载消失。读卡32条、部署/备份/推出7条封存；
latest-A23/latest-quiet指向本次实际quiet部署。新日志为旧A23启动/result0/record21及
接口1记录，无EXE3或接口2目标证据，不认证新run或原根因。184源/七生产/三票据/三
离线记录保持，正式新记录不存在、次数0，无接收器启动/USB诊断或ARM执行。
用户读卡部署要求已完成。装卡后先保持关机；下一次另行明确启动诊断时，签发独立
一次记录、先主机WAITING再提示开机。原超时根因仍未知。以下为历史语境。

最新续接：[一次quiet诊断签发入口与现场交接](docs/A23_QUIET_ONCE_READY.md)完成：用户确认
可以配合关机/取放SD/CFW启动；实际关机/插卡状态与本次执行授权尚未确认。新工具
默认只读预览，显式签发才排他新建独立记录，绑定部署包/接收器/六材料/原生验证；
拒绝覆盖、补次、部分文件和材料变化。8新增/217相关回归全过、0跳过，184来源摘要，
旧182源/七生产/三票据/三离线记录及29封存7383条保持。临时模型签发均清理，正式
预定记录不存在，旧次数仍0；未写卡/启动接收器/USB或设备执行。现场顺序已固定为
关机插卡→核验备份→部署弹出→主机WAITING→用户装卡启动→一次诊断→关机回收。
下一步请用户完成关机插卡并明确本次备份/部署/一次实测授权；先核卡，不直接发请求。
原超时根因仍未知。以下为历史语境。

最新续接：[quiet 候选部署包与回收判读](docs/A23_QUIET_DEPLOYMENT_REVIEW.md)完成：
封存 ELF 直接转换 NSO/PFS0，新 exefs.nsp 813142…，三个程序段/BSS/build ID、原 NPDM
程序 ID/权限范围及接收器六材料匹配；22 处控制器修改与原 IPS 相符。四文件候选与
历史 A23 回退树已备；包22条/回收模型10条封存，182来源摘要，12新增/209相关回归
全过、0跳过。主文件内容/提交回执/EXE3自身提交及退出分开；诊断保存成功仍保留，
无在线完成证明，不用固定倒数取卡。旧180源/七生产/三票据/三离线记录、26旧封存
7331条保持，次数仍0；仅电脑打包，无部署、USB/SD、设备执行或新实机结论。
下一项确认现场CFW新启动、受控关机与只读回收步骤，再另行授权/签发一次接口2诊断；
原超时根因仍未知。以下为历史语境。

最新电脑准备：[独立接口2诊断方案](docs/A23_QUIET_DIAGNOSTIC_PREPARATION.md)已形成，
24条/16来源快照封存；先预等待再fresh启动，分开设备30s窗口和主机120s等待，明确
一次请求、失败保留和分支/缺证判读。程序/零次数记录不改，197项既有回归保持。
下一项部署/启动/保存完成确认与Retained回收清单；无有效采集/USB/SD/设备执行或部署，
原根因未知。以下为历史语境。

最新电脑研究：[quiet ELF等待、静默与保存路径](docs/A23_QUIET_PATHS.md)。同一设备/
接收器新地址核对日志、文件名、等待与main交接，197相关回归通过、0跳过。条件组合
视频含包装1504/音频80/main4240非完整栈上界；静默帧832、当前owner无捕获递归。
180输入/214+12条封存，旧材料保持、次数0，无有效采集/SDK/USB/SD/设备执行或部署。
下一项一次独立接口2分支诊断的操作与判读准备，原根因未知。以下为历史语境。

最新电脑实现：[quiet候选接收器与六项材料收集](docs/A23_QUIET_RECEIVER.md)。设备不改，
新host将六文件与NPDM/配置/main请求8192纳入启动、交接、回执和收集，旧记录拒绝。
177输入、两套14单元链接、25收集及182项相关回归通过、0跳过；1546/194/12条封存。
新记录仍零次数，旧材料保持，无有效采集/真实IOKit/SDK/USB/SD/设备执行或部署。
下一项同一quiet ELF的新地址诊断等待和join后保存路径核验，原根因未知。
以下为历史语境。

最新电脑实现：[隔离捕获与文本日志的诊断候选](docs/A23_QUIET_WINDOW_CANDIDATE.md)。
30s窗口只处理USB，音频闲置；启动worker前静默至双join成功，保留trace与失败保存。
新recipe/ELF/NPDM及原配置六项绑定，二进制main请求8192，实际预算未知。13单元链接，
124次native模型及154项相关回归通过、0跳过；170输入、548/12条封存，旧材料保持。
下一项独立接收器/收集链改绑新候选并复验新ELF等待/保存路径；旧接收器拒绝新材料。
次数0，无有效采集/USB/SD/设备执行、打包部署，原根因未知。以下为历史语境。

最新电脑研究：[V3实际日志、文件名与等待栈剖面](docs/A23_V3_STACK_PROFILES.md)。当前
ELF重绑79日志调用/73格式；219日志/6文件名/40等待剖面及6边界对照、142项相关回归
全部通过，166输入、196/10条封存。logger2592、文件名1904及线程组合值不是整链上界。
下一项隔离诊断窗口生产捕获和同步文本日志的新最小候选，保留trace、双join、失败保存，
补新身份/NPDM关联；尚未实现。旧129源及封存保持，新旧次数0，无有效采集/USB/SD/
设备执行或部署，原超时根因未知。以下记录保留此前阶段语境。

最新电脑实现：[父输入、运行recipe与ELF的独立绑定候选](docs/A23_BOUND_RECEIVER.md)。
新构建/描述/记录/消费回执/核销与EXE3收集已使用正确运行值，并单列父输入和最终ELF。
129源冻结、两套14单元链接，12组循环/5次序列化/16组收集和128项相关回归通过、0跳过；
审查987/构建144条封存。下一项同一ELF诊断必需格式/logger与具体等待路径的整链栈
核验。旧122源及封存保持，新旧次数0，无有效采集/设备执行/USB/SD或部署，原根因未知。
以下记录保留此前阶段语境。

最新电脑研究：[V3线程运行路径、日志与身份](docs/A23_V3_RUNTIME.md)。正常静态TLS/
reent路径核对完成，栈数组扣SDK元数据及包装帧后用户入口剩19792/11600字节；整链
上界仍未知。16组日志注入不认证Switch服务语义；106项相关回归无跳过，122源/142条
审查封存。发现接收器采用父摘要a7ae…，窗口实际recipe为04e9…；下一项明确新隔离
构建的父输入/运行recipe/ELF与回执/EXE3关联，再核诊断必需栈。无设备执行/USB/SD
或部署，次数0，原超时根因未知。以下记录保留此前阶段语境。

最新电脑实现：[等待日志纳入EXE3收集主结果](docs/A23_WAITING_COLLECTION.md)。等待、
SDK快照与生命周期核对已进入主结果；部分/失败字节保留，匹配模型仍不认证实机来源。
5次原生模型、24组收集及94项相关回归通过，118源/13 header、审查720/验证9条封存。
下一项回到V3三线程的TLS/reent、日志重入/共享文件调用及完整栈/窗口成本审查。
未执行有效许可采集，新记录及三实时票据0，无真实IOKit/SDK/USB/SD或部署，原根因未知。
以下记录保留此前各阶段语境。

最新电脑实现：[等待接收器构建与启动门禁](docs/A23_WAITING_RECEIVER.md)。新接收器
绑定当前/冻结源码、构建及单次许可，选择后再复核，准备与start分轮次；未完成I/O保留。
114源冻结、12组循环注入及75项相关回归通过，审查220/构建120/验证9条封存。
下一项将等待核对纳入EXE3收集主结果，再核V3可达线程/TLS/栈成本。新构建记录0、旧
三票据0，未执行有效许可acquire，无真实IOKit/SDK/USB/SD或部署，原根因未知。
以下记录保留此前各阶段语境。

最新电脑实现：[隔离等待入口与SDK启动分离](docs/A23_WAITING_ENTRY.md)。已接等待、
持久日志与独立文件许可，SDK准备和start分离，关闭等待通知后才启动控制；32组注入
和58项相关回归通过，98源/334条审查及9条验证封存。下一项补完整构建校验/真实启动
门禁与EXE3新封装，再核V3可达线程/TLS/栈。旧采集入口保持，无真实IOKit/SDK/USB/SD
或部署，三票据0，原SDK超时根因未知。以下记录保留此前各阶段语境。

最新电脑实现：[主机通知适配与EXE3收集对接](docs/A23_HOST_EXECUTION_LINK.md)。真实绑定
只编译链接，113通知模型/230消息边界、六组材料收集及44项相关回归通过，五份释放失败
引用保持。下一项隔离入口准备/start分离及持久日志/新门禁；旧入口仍单次发现。无真实
IOKit/SDK、USB/SD或部署，三票据0，原SDK超时根因未知。

最新电脑实现：[执行V3候选](docs/A23_EXECUTION_V3_CANDIDATE.md)。隔离补前置过期检查、
正常/失败EXE3保存与等待C策略核心；87次native（等待含447场景）/29项相关回归通过。
两配置13对象完整ELF只链接，BSS各+16KiB。下一项真实通知适配和EXE3收集/比较；无USB/
SD或部署，三票据0，原SDK超时根因未知，旧主机入口仍无提前等待能力。

最新电脑研究：[窗口、主机等待与V2材料关联](docs/A23_EXECUTION_READINESS.md)。九组
native/16项检查通过；确认主机单次发现、休眠跨期先处理及正常/失败关联保存三个缺口。
下一项隔离实现前置过期检查、关联保存策略与被动等待，再核可达线程/TLS成本；无USB/
SD或部署，三票据0，原SDK超时根因未知。

最新电脑实现：[独立V2容量候选](docs/A23_CAPACITY_V2_CANDIDATE.md)。256条/32身份，
八次查询后仍完成目标三步；442次native/29项回归通过，两配置13对象完整ELF只链接。
下一步时间窗、V2材料关联和运行条件；无USB/SD或部署，remaining0，原根因未知。

最新电脑研究：[诊断候选会话容量与分支审查](docs/A23_DIAGNOSTIC_READINESS.md)。124组
native回放、14项回归通过，确认当前128条trace在3次接口查询后缺后置STATUS、4次后拒绝
BURST；这是候选自身限制。下一步独立V2容量256/身份32及配套导出，尚未实现或部署。

当前总览与优先级：[项目现状、结论与研究路径](docs/RESEARCH_DIRECTION.md)（2026-10-15）。
A23已有两次独立启动共32轮及两次回绕的有界验收；首次SDK burst失败根因仍未知。
下一步收敛接口2有界诊断候选，区分共享SETUP覆盖与早退/提交/ACK路径，再推进持续ISO与UAC。
以下技术记录保留各阶段语境，实际次数以实时票据为准，当前均为0。

最新电脑研究：[新ELF完整格式化与SDK内存指令连续回放](docs/A23_INTEGRATED_MEMORY.md)：4080完整回放、5808取参、24720真实helper指令模型调用与438类型化参考匹配，1282独立helper及184相关回归通过；strlen周边映射为前提。1664仅是含helper的样例SP观察，整线程栈/运行态/USB根因未知。无新ARM或USB/SD，remaining0。

上一阶段电脑研究：[GetSize保护完整ARM隔离候选](docs/A23_LOG_GUARD_ARM_CANDIDATE.md)：两配置各13对象、新recipe，最终ELF失败只Close、写入限长511；自身栈832不变，text各+64，data/BSS保持。两配置旧91项观察保持，638项native/168相关回归通过；旧formatter/helper尚未重绑新ELF，整线程栈与USB根因未知。ARM仅链接、USB/SD0，remaining0。

上一阶段电脑研究：[SDK内存函数与GetSize失败保护](docs/A23_SDK_MEMORY_LOG_GUARD.md)：1282组真实SDK指令模型、194项native与156相关回归通过；隔离GetSize失败Write0/Close1。两配置4个core.o核验实际分支，自身栈832不变，尚未链接完整新候选。strlen块读取依赖映射，完整formatter仍有helper模型，整线程栈与USB根因未知；USB/SD0，remaining0。

上一阶段电脑研究：[当前日志完整渲染/扫描循环回放](docs/A23_FORMAT_LOOP.md)：73格式/97转换，3504完整回放/4656取参与438本机snprintf对照匹配，141相关测试无跳过；真实参数/缓存连续到返回，样例FILE flags与截断/NUL保持。SDK内存helper仍模型，TLS/locale/重入/错误/整线程栈未闭合，无新ARM或USB/SD，remaining0。

上一阶段电脑研究：[默认locale字面扫描/初始化审查](docs/A23_LITERAL_SCAN.md)：真实wrapper构造FILE/复制va到TLS/UTF-8扫描及首取参，876回放+4对照、126相关回归；原首转换边界见专题，旧封存保持。

上一阶段电脑研究：[转换入口到真实取参路径审查](docs/A23_PARSER_BRIDGE.md)：73格式/97转换，两配置776日志回放+12对照；更正旧hex标注区域实为%o，真实hex路径已核验，旧封存保持。

上一阶段电脑研究：[格式解析器与缓存局部审查](docs/A23_ARGUMENT_CACHE.md)：位置标志栈位置复用、32项顺序缓存耗尽可继续直接取值，338指令profile/558相关回归通过。旧x32/x64标注更正见最新研究，旧封存保持。

上一阶段电脑研究：[新ELF日志调用与FILE状态](docs/A23_LINKED_LOG_FILE_STATE.md)，79/80个直接调用点绑定73格式，局部错误位保持增长mask，132组追加指令profile/542相关回归通过。get_arg/FILE生命周期/整线程栈仍未知，无新ARM或USB/SD，remaining0，根因未确认。

上一阶段电脑研究：[日志修正完整 ARM 候选](docs/A23_LOG_ARM_CANDIDATE.md)，两配置各13对象/new recipe，机器码日志限长511、旧91观察保持，603 native/524相关回归通过；完整线程栈与USB根因仍未知。未执行ARM/打包/访问USB/SD，remaining0。

实验分支`experiment/uac`的研究入口：Build-ID特定HOS设备补丁、vendor alt0 ISO端点和macOS接收器。
设备仍为A23，新主机工具`native-guard-serial-2`最新于10-11 21:07防休眠重试16轮主机通过，实际回绕一次，23382byte完整设备日志核验通过。2026-10-09串行测试在第1次原生错误后停止，
完整设备日志已核验，SD已安全推出。串行及一次环回绕完整验收通过，稳定性仍未确认；无TD诊断工具已验证，
18:50无TD基线及完整日志已核验；20:34同backend单次burst及2630byte完整设备日志验收通过，20:51已安全推出SD。
UAC/PCM保持禁用。最新事实以[当前状态](docs/STATUS.md)为准。

上一阶段电脑研究：[日志格式、长度与类型契约审查](docs/A23_LOG_CONTRACT.md)完成：
13单元/76处，发现frequency %u/u64错误和通用截断写入缺口；新隔离源码三文件
修复并通过语法检查，最大输出229byte。250 native/515相关回归通过，未构建新
完整ARM，GetSize错误/FILE状态/整线程栈仍待审。下一步新recipe候选及旧观测
对照，再绑格式/FILE/ELF调用点。生产/原runtime/旧封存/票据保持，USB/SD0、
remaining0，根因未知。

## 状态与操作

从仓库根目录执行：

```sh
python3 research/usb-ds-iso/tools/experiment.py status
python3 research/usb-ds-iso/tools/experiment.py verify
python3 research/usb-ds-iso/tools/experiment.py restore --dry-run
```

以上命令不访问USB。缺少本地产物时，按[目录及产物管理](docs/DIRECTORY_LAYOUT.md)选择性恢复。
`test`当前次数0；serial-clock-1两次独立启动各16轮完整验收通过，共32轮、2次实际环回绕，目标2/2完成；SD已安全推出。
连接条件及验收见[同backend串行验收](docs/MATCHED_SERIAL_VALIDATION.md)。
五次逐槽分析及下一项无TD窗口诊断方案见[原生错误分析](docs/NATIVE_ERROR_ANALYSIS.md)。
无TD基线及完整日志已核验，见[无TD诊断](docs/NO_TD_WINDOW_TEST.md)；
最新[单次burst对照](docs/BURST_WINDOW_TEST.md)完整验收通过，唯一次数已消耗；首次串行16轮及回绕完整核验通过，第二次独立复核失败日志已核验；最新时钟诊断完整核验通过，最新有界串行Mach测试16轮完整验收通过，第二次独立复核完整验收通过，下一步离线定义新的诊断目标，见[诊断结果](docs/CLOCK_AUDIT.md)。
后续条件见[测试计划](docs/TEST_PLAN.md)。

Mac 的新 IOUSBHost 接收器已实机执行空窗口与一次burst诊断。
设备继续 A23；空窗口主机观察及完整设备日志关系已重审，960槽status0/actual0、overall0，
原生政策仍未接受。首次SDK burst控制超时、ISO Aborted、有效包0，完整日志已回收，
见[首次burst读卡复核](docs/IOUSBHOST_FIRST_BURST_CARD_REVIEW.md)。两入口剩余0。

## 文档导航

| 文档 | 用途 |
| --- | --- |
| [新ELF格式化与SDK内存连续回放](docs/A23_INTEGRATED_MEMORY.md) | 新绑定、4080完整样例、24720实际helper模型调用及映射/栈边界 |
| [GetSize保护完整ARM隔离候选](docs/A23_LOG_GUARD_ARM_CANDIDATE.md) | 新recipe/13对象完整ELF、638项native、最终分支/限长与旧生命周期对照 |
| [SDK内存函数与GetSize失败保护](docs/A23_SDK_MEMORY_LOG_GUARD.md) | 1282组SDK指令模型、194项native、GetSize失败保护及ARM对象范围 |
| [当前日志完整渲染/扫描循环回放](docs/A23_FORMAT_LOOP.md) | 3504完整样例、本机类型化输出对照、八参连续性/栈复用与剩余SDK/运行态边界 |
| [默认locale字面扫描/初始化审查](docs/A23_LITERAL_SCAN.md) | wrapper FILE/va构造、TLS/UTF-8实际扫描、首取参和纯文本返回，以及渲染/循环缺口 |
| [转换入口到真实取参路径审查](docs/A23_PARSER_BRIDGE.md) | 实际字符/宽度/ll分派接取参、hex区域更正、局部位置标志存活区间与完整扫描缺口 |
| [SDK句柄等待与定长关联路径候选](docs/A23_WAIT_FIXED_PATH.md) | 定长路径、768byte保存直接图、312组句柄等待回放与时限边界 |
| [关联发布/中断与最终ELF栈审查](docs/A23_SESSION_CONCURRENCY_STACK.md) | pthread/TSan、不可升级快照、352byte局部闭合与完整栈缺口 |
| [启动关联与独立保存ARM候选](docs/A23_SESSION_ARM_CANDIDATE.md) | 真实启动/nonce/保存返回、91项native、13对象完整ELF与静态成本 |
| [启动与EP0会话关联原型](docs/A23_SESSION_CORRELATION.md) | REL1关联/失败旁路、不可变receipt、28+24项native与独立容量边界 |
| [启动日志ARM候选](docs/A23_STARTUP_ARM_CANDIDATE.md) | 实际API/启动SID、44项插桩、两窗口完整11对象ELF与成本边界 |
| [独立启动日志原型](docs/A23_STARTUP_JOURNAL.md) | 64条不可变发布区间、独立INI1、native并发/TSan与结果语义 |
| [初始化/启动失败审查](docs/A23_STARTUP_FAILURES.md) | 40项实际函数回放、Core/Capture部分初始化与线程创建/启动失败边界 |
| [故障诊断落盘候选](docs/A23_DIAGNOSTIC_SINK.md) | 双join后拒绝诊断、6656byte独立一次保存、保存后保留资源与140项native |
| [联合预检与trace预算候选](docs/A23_BOUNDED_CANDIDATE.md) | 整个BURST范围预检、逐就绪请求预算与followup停止、185项native/完整ARM ELF |
| [完整会话预算与拒绝诊断](docs/A23_GUARD_SESSION_DIAGNOSTICS.md) | 28项实际视频函数回放、两类容量边界、独立失败诊断与保留资源条件 |
| [buffer门槛与统一退出候选](docs/A23_GUARDED_CANDIDATE.md) | copy/post前拒绝未知范围、原子清理授权、43项native场景与两配置ELF |
| [实际handler隔离候选](docs/A23_EP0_HANDLER_CANDIDATE.md) | 48项真实源码回放、完整候选ELF、停止/账本封装与构建关联边界 |
| [trace owner 与导出准备](docs/A23_EP0_TRACE_OWNER.md) | 独立owner/原始URB报告/join与内存导出策略、28场景及libnx适配器ELF链接 |
| [有界内存trace原型](docs/A23_EP0_MEMORY_TRACE.md) | 128条固定记录、轮询计数/freeze/CRC、25项源码副本回放与独立解码 |
| [HOS共享SETUP审查](docs/A23_HOS_SHARED_SETUP_AUDIT.md) | 实际命令2/虚表/共享存储及事件clear、后续STATUS时间边界与6项源码模拟 |
| [离线代码与证据审计](docs/OFFLINE_AUDIT.md) | backend差异、固件完成路径、60个burst分组及实机证据缺口 |
| [当前macOS主机驱动审计](docs/HOST_DRIVER_AUDIT.md) | 内核集合、NotSent兼容映射、整体结果传播及历史证据边界 |
| [主机请求与平台分派](docs/HOST_DRIVER_FLOW_AUDIT.md) | 方向In、首个错误汇总、T8112虚表及直接transaction API候选 |
| [IOUSBHost transaction接口审计](docs/IOUSBHOST_TRANSACTION_AUDIT.md) | 当前framework主调用链、缓冲区/取消所有权及纯模拟原型 |
| [IOUSBHost离线证据链](docs/IOUSBHOST_EVIDENCE_PIPELINE.md) | 描述符预检、完整证据写盘与独立分析；仅模拟，不开放采集 |
| [IOUSBHost会话与设备关联](docs/IOUSBHOST_SESSION_AUDIT.md) | 断开/迟到回调、模拟生命周期及STATUS/ISO7/启动日志离线关联 |
| [IOUSBHost SDK与原始STATUS绑定](docs/IOUSBHOST_SDK_BINDING_AUDIT.md) | SDK适配编译/模拟故障、原始回复/会话/传输包封装核验；无实机入口 |
| [新接口空窗口观察方案](docs/IOUSBHOST_NO_TD_PLAN.md) | 固定预检/帧号/单请求、失败停止和空槽分布；原生政策未验证 |
| [新接口运行条件准备](docs/IOUSBHOST_RUNTIME_READINESS.md) | 服务引用、最终入队预算和 pending 退出；电脑准备已实现，仅模拟 |
| [新接口单次实机入口](docs/IOUSBHOST_HARDWARE_ENTRY.md) | 已冻结 Mac 接收器、独立一次凭据、停止条件与日志回收；尚未执行 |
| [SDK打开失败诊断](docs/IOUSBHOST_OPEN_DIAGNOSTIC.md) | 沙箱访问拒绝与SDK错误覆盖；真实打开/描述符/pipe/分配准备对照 |
| [新接口首次空窗口](docs/IOUSBHOST_FIRST_EMPTY_WINDOW.md) | 真实单次主机观察完整，960槽status0/actual0；完整设备日志和空槽政策待核验 |
| [有界串行Mach诊断](docs/SERIAL_CLOCK_AUDIT.md) | 下一项测试、时间记录验收及停止条件 |
| [当前状态](docs/STATUS.md) | 最新事实、已验收范围、未确认项及证据指针 |
| [测试计划](docs/TEST_PLAN.md) | 离线研究、单次诊断、串行回绕及后续回归的推进条件 |
| [原生错误分析](docs/NATIVE_ERROR_ANALYSIS.md) | 五次逐槽对照、空槽错误前缀、时序限制及无TD诊断方案 |
| [无TD诊断](docs/NO_TD_WINDOW_TEST.md) | 主机基线、完整无提交日志核验及读卡推出 |
| [单次burst对照](docs/BURST_WINDOW_TEST.md) | 同backend接收器、唯一次数入口、本地验证及下一次条件 |
| [同backend串行验收](docs/MATCHED_SERIAL_VALIDATION.md) | 新主机工具、逐轮ED/context/环检查及最多16轮停止机制 |
| [独立启动复核](docs/INDEPENDENT_SERIAL_REPEAT.md) | 第二次完整串行目标、防休眠入口及停止条件 |
| [时钟诊断](docs/CLOCK_AUDIT.md) | 保存帧AbsoluteTime与Mach入队时刻，单次观察、原生错误不变 |
| [读卡流程](docs/CARD_WORKFLOW.md) | 回收、研究、验证、部署、读回校验与安全推出 |
| [目录说明](docs/DIRECTORY_LAYOUT.md) | 源码位置、冻结产物、恢复与构建输出 |
| [实验指南](docs/EXPERIMENT_GUIDE.md) | 固定目标、通用约定及早期A/B/C技术参考 |
| [历史结果](docs/RESULTS.md) | 按实验阶段保存的日期、原始观察与后续核验 |
| [A18事件](docs/EVENT_AUDIT.md)／[A19发布](docs/PUBLICATION_AUDIT.md)／[A20门铃](docs/DOORBELL_AUDIT.md) | ISO3/4/5诊断布局与对应结果 |
| [A21上下文](docs/CONTEXT_AUDIT.md)／[A22后续SIA](docs/FOLLOWUP_SIA.md) | ISO6配置观察与调度对照 |
| [A23服务间隔](docs/INTERVAL_EXPERIMENT.md)／[独立复现](docs/REPRODUCIBILITY.md) | ISO7条件及原接收器成功/失败对照 |
| [主机微帧观察](docs/HOST_MICROFRAME_AUDIT.md)／[串行验收](docs/NATIVE_SERIAL_VALIDATION.md) | 两次单次成功、逐次原生状态检查及首轮失败停止 |

## 目录

| 目录 | 内容 |
| --- | --- |
| `docs/` | 状态、操作、测试条件、技术说明和历史结果 |
| `patches/` | 设备控制器补丁汇编源码 |
| `host/` | 主机接收器与原生证据核验 |
| `tools/` | 补丁构建、打包、离线分析和统一入口 |
| `tools/workflows/` | 状态与产物管理、有界采集流程 |
| `tests/` | 模拟控制器、接收器及流程测试 |
| `ghidra/` | 反编译导出脚本 |
| `private/` | 忽略提交的厂商模块、冻结包、构建缓存和实机证据 |

冻结包、原生状态及原始日志保留其内容和哈希；当前文档与历史包中的说明分别维护。

控制广播审计最新结果见[离线重审](docs/IOUSBHOST_CONTROL_TRACE_REVIEW.md)：121项回归通过，同一证据完整性通过，原生政策仍未接受。

[原生字段与时间语义](docs/IOUSBHOST_NATIVE_SEMANTICS.md)：960槽仅120个不同完成时间戳，126项相关回归通过；下一步离线定义单burst诊断。

[单次burst离线草案](docs/IOUSBHOST_SINGLE_BURST_DRAFT.md)：137项相关回归通过，双完成及停止规则已定义；没有实机执行器或新次数。

[单次burst模拟执行器及审计](docs/IOUSBHOST_BURST_EXECUTOR_AUDIT.md)：22个原生场景通过ASan/UBSan，147项Python回归无跳过；journal/core独立绑定完成，设备日志/ISO7绑定仍待离线实现。

[单次burst模拟collection审计](docs/IOUSBHOST_BURST_COLLECTION_AUDIT.md)：165项回归无跳过，STATUS/core/A23日志/ISO7/三组控制分发绑定完成；下一步电脑编译审查SDK transport，实机次数0。

[单次burst SDK能力适配](docs/IOUSBHOST_BURST_SDK_ADAPTER.md)：33个新及47个旧原生注入场景通过ASan/UBSan，171项回归无跳过；能力层已编译，硬件证据格式及协调器尚待电脑实现，没有采集入口。

[单次burst SDK协调器及主机格式](docs/IOUSBHOST_BURST_SDK_COORDINATOR.md)：34个新原生场景通过ASan/UBSan，184项回归无跳过；双截止、失败保存和独立主机绑定完成，下一步电脑接独立硬件collection及设备日志/ISO7关系，尚无采集入口。

[单次burst SDK collection与设备关系](docs/IOUSBHOST_BURST_SDK_COLLECTION.md)：204项检查无跳过，34个原生注入场景通过ASan/UBSan；18份collection中5条正常关系通过，原始STATUS/A23日志/ISO7/控制绑定完成。下一步电脑审查单次入口及凭据工作流，尚无可用次数。

[单次SDK burst入口与零次数准备](docs/IOUSBHOST_BURST_ENTRY.md)：221项检查无跳过，12个原生注入场景通过ASan/UBSan；入口及先消耗后启动工作流编译冻结，独立记录offline_build_ready/0。基础电脑实现已齐，下一项实机诊断需另行签发一次；无需拷文件。

[首次SDK burst实机诊断](docs/IOUSBHOST_FIRST_BURST_TEST.md)：控制16.395ms返回Timeout，ISO停止后Aborted，有效包0；证据保存后资源关闭，exit1，无重试。入口finished类型已离线修正，12项native/221项回归通过；remaining0，下一步回收完整设备日志。

[首次SDK burst读卡复核](docs/IOUSBHOST_FIRST_BURST_CARD_REVIEW.md)：6041byte日志确认burst setup到达接口0/1广播记录，无ISO提交/终结记录；四文件及21报告未变化，SD已安全推出，remaining0。下一步电脑审查接口2处理和EP0应答路径。

2026-10-29 A23 URB trace 回合：完成 v4（最后完成 URB 的 IOVA/size）和 v5（8 个条目全部 IOVA/size）的离线构建与实机。v4 r5 在 5 个 URB 后读到 `last_iova=0x80030000`、`last_size=3072`，没有触发 size=0 跳过；v5 160 包为 4 post，两页交替；v5 320 包 + `caffeinate` 为 `posts=8 completes=7 errors=0`，**无 usb fatal**，8 个条目仍只在 `0x80030000`/`0x80040000` 两页间交替。由此推翻本 build 的“5 URB/5 页”硬限制；serial640 的旧 5 URB 崩溃需按当时 in-flight/主机状态或构建差异重新解释。尚未证明 10s 连续 PCM、完整 ring 复用或标准 UAC。证据：`private/runs/A-urb-entries-v5-320-20261029/`、`private/analysis/A23-urb-trace-round-20261029/`；卡最终恢复安全 `52069a44…`。

2026-10-29 18:01 serial640 10s 复测：同 v5 build、640 缓冲、`posts == completes` 单飞，host `caffeinate -dimsu iso-stream --transfers 1 --packets 10000` 收到 3392 有效包、bad=0；设备 `posts=214 completes=213 errors=0 late=212 attempts=214`，无 usb fatal，8 个 URB 条目仍只在 `0x80030000`/`0x80040000` 两页间交替。原始 serial640 的 5 URB 崩溃未复现；旧结论转为 host 休眠/USB 调度或当时运行状态，而不是固有 5 页墙。证据 `private/runs/A-serial640-v5-retest-20261029/`，卡恢复安全 `52069a44…`。
