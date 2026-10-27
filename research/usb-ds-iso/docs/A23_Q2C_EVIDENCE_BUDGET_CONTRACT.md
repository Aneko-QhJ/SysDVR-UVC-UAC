# Q2c 整轮证据预算、停止与交接合同（2026-10-27）

后续[单段整轮额度租约模型](A23_Q2C_EPOCH_LEASE_MODEL.md)已完成38项检查；仍无真实设备grant或全局互斥。下一项仅电脑定义设备额度回执协议与握手预算。下文为本来源合同阶段及当时下一步，原封存保持。

本轮静态核对完成：30 项部署来源锚点、257 个逐请求边界重放、514 个容量算例通过。138 件快照中的本次 execution 原件重新解码，与 Q1 封存解码逐项相同。

现有 17 条 reserve 只保护一次 ready 请求；没有整轮预留。30s 窗口只在同步 owner 调用之间检查；现有 owner/window/sink 也是一次性的，没有无损滚动协议。本轮形成 10 条交接要求，尚未实现新准入、设备改动或滚动。

新增一个研究来源 `tools/audit_a23_q2_evidence_budget.py`，研究清单为 676；此前675及冻结 Q1 receiver672 保持。本轮无编译、原生 fixture、SDK、USB/SD、新范围或授权。

## 来源和重算

设备使用 package binding 指向的 `A23-path-span-device-review-20261016/candidate`，runtime recipe `37269528ee3baa2941e1cb9268ccd4702d9db5b0fec87e913d3111c99b6e894f`；其封存父清单、package 和部署匹配的138快照均验证。主机使用 Q1 r4 的 generated/live_driver.m，不重建或改写候选。

从 execution 原件重新得到30组请求，完整分割 ordinal1..216。前置3组18条；每轮 before STATUS23、BURST20、after STATUS23，共66条；每轮成功记录6个 URB 身份，本次共19个，均为终态3。终态身份依然占用32槽账本，pending=0不回收身份。

## 三种不同的 trace 数字

| 数字 | 依据与条件 | 使用边界 |
| --- | --- | --- |
| 66/轮 | 本次实际形状23+20+23，三轮重算一致 | 是观测值，不是任意请求或交错的最坏上限 |
| 69/轮 | 精确9个ready组：每个线请求在接口0/1因目标接口不匹配仅记3条，目标接口2按已声明的17条请求上界预留；3×(3+3+17) | 条件包括正确setup形状、恰好9组、17上界成立；当前没有把这些条件与整轮额度绑定起来 |
| 153/轮 | 9个ready组均按通用17条请求上界计算，9×17 | 仍假设恰好9组，没有涵盖无限额外流量、停止协议或所有非请求事件 |

单次 AdmissionReady 在 count≤239 时才准入，然后 End 检查本请求是否超过17条、是否新增 dropped/invalid。它不会在主机提交 ISO 前预留整轮额度。非请求 disconnect 的单次 owner 调用说明，也不能被提升成整个窗口最多一次状态变化。

仅作容量算术的示例：若额外预留1条非请求/停止记录，69预算要求开始count≤186，153预算要求count≤102；对count0..256分别核对，共514个算例。这个“1条”是示例条件，真实整轮非请求/停止上界尚未建立，所有 capacity_fits 的 actual_admission_authorized 均为false。

容量256、观测216只余40。当前同形第四轮为18+4×66=282，超出26；条件预留69和通用预留153都放不进这40条。当前设备时间/身份/本地元数据及停止证据的预算还必须独立满足。

## 逐请求准入可能在轮中拒绝

CPU 将本次最后一轮的记录形状追加到已有216条，并重放现有17条逐请求门，得到：

| 拟处理组 | 开始count | 追加记录 | 结束count |
| --- | ---: | ---: | ---: |
| before STATUS / interface0 | 216 | 3 | 219 |
| before STATUS / interface1 | 219 | 3 | 222 |
| before STATUS / interface2 | 222 | 17 | 239 |
| BURST / interface0 | 239 | 3 | 242 |
| BURST / interface1 | 242 | 拒绝：需要17、只余14 | 242 |

这只是假设形状的离线重放，没有发送第四轮。当前 host仍固定三轮。来源中的主机顺序是 before STATUS → frame sample → ISO提交 → BURST；若以后仅放大轮数而保留这些顺序和局部门，拒绝发生时 host ISO可能已经pending，而目标接口2还未处理BURST。不能把逐请求容量保护解释成整轮完成保证。

257个起始count0..256分别重放同一形状，均保持局部计数不溢出。该结果不验证真实请求到达顺序、并发流量、SDK回调或物理传输。

## 30s 是外层检查窗口

部署 main 在等待USB ready之前启动30000ms窗口，不能在首个ISO时重新开始计时。过期检查位于 UvcDeviceProcessRequests 前后；内部可连续服务多组ready请求，只检查 stop_requested，没有在该循环内检查窗口到期。EP0 helper也是同步调用。

因此没有建立同步owner调用的耗时上界，30s不提供中断/取消保证。一个纯算术例子：29.999s进入owner调用，假设耗时250ms，则30.249s返回后才检查过期。250ms在这里是举例条件，不是设备测量或上界，也不是借用主机服务窗口作设备耗时。Q1实际30.000326秒正常结束仍成立，但不能据此排除其他安排的超时延后。

主机与设备时钟没有绝对校准。新的整轮时间准入若依赖剩余窗口，必须声明设备时钟、owner调用耗时与停止耗时的依据；未知时不能凭主机时刻或一次历史样本授予硬截止许可。

## 当前交接路径为何不能直接滚动

来源中的正常路径是请求停止 → owner边界freeze/stop → video与audio实际join → exporter接手 → 无fault/pending的正常导出 → primary和execution保存、回读与commit确认 → handle关闭 → cleanup授权。

freeze不请求USB关闭或排空。任一join失败会保留；正常导出要求pending=0、无fault。ownership Finish拒绝时可以尝试诊断证据，随后走retain分支，诊断保存不是正常释放或新窗口许可。

owner init拒绝已有writer，execution window/build以unused phase的一次CAS消费，sink也只允许一次attempt。文件排他创建失败没有删除/截断回退。当前没有“保存完成就清空trace、删身份、重置phase并继续”的接口；新协议不能绕过这些历史与所有权保护。

回读及commit是已有API层确认，不代表断电耐久证明，也不能代替主机 SDK backing 的交还。设备线程join与主机closure/native DMA属于不同域。

## 十条待实现合同

1. **段身份**：唯一segment/session、recipe、来源束、序号域与前段manifest摘要绑定；不删除旧身份来启动新段。
2. **整轮额度**：在ISO提交前，约束完整请求安排并预留trace、身份、本地元数据及非请求/停止证据。新增“额度请求”或ACK本身也计入安排，不把事后216条当实时额度回执。
3. **时间政策**：区分外层检查和硬截止，声明设备时钟、同步调用与停止耗时；未知耗时不授予deadline准入。
4. **停止新工作**：主机、设备及不同入口都有明确停止准入与确认政策；一个本地flag不等于所有来源关闭。
5. **pending所有权**：完成或保留已准入操作；pending/fault/原生交还未知时，不覆盖存储、不清账本、不自动释放。
6. **writer交还**：owner边界freeze/stop、真实成功join、正确exporter及相应pending/fault条件分别留证，不从计数或观察窗口推断交还。
7. **不可变证据**：唯一创建、完整回读、commit与封存；失败原件保持，诊断证据不能变成正常释放回执。
8. **消费者确认**：ACK绑定精确segment manifest和连续性；缺失或矛盾ACK不能假定额度已释放，重读分类不覆盖原件。
9. **新段门**：证据交接和backing/callback安全各自成立后才考虑下一段；既有一次性owner/window/sink不能直接重置。
10. **真实范围**：任何未来测试需最新138基线、新候选、范围、授权和当次就绪确认；本合同没有提出或保留新序号。

Q2b符号credit不能代替上述设备额度；Q2a原生交还未知也没有因容量算例获得解决。本阶段整轮预留和无损交接均未实现。

## 下一项与封存

下一项只在电脑上设计最小整轮额度租约与停止门候选：把形状、额度、snapshot/segment身份及失效条件显式化；额外流量、时间或所有权条件未知时拒绝新准入。先限定一次有界证据段，不引入自动滚动、真实复用或设备改动，也不重复相同Q2b排列。

审计目录：`private/analysis/A23-q2c-evidence-budget-review-20261027-r1`，摘要 `d2280134256a039437606b964d1cbc605f5ced8fef5ce8f4dd67ef815131d309`。保存部署源码副本、30项锚点、原件重解码、局部边界、容量条件、中途拒绝反例、窗口反例和10条机器合同。

最终交接：`private/analysis/A23-q2c-evidence-budget-closeout-20261027`。Q1 actual465/namespace465、旧actual417/九namespace、138快照、此前675来源和全部sealed evidence保持；研究676与冻结receiver672区分。remaining=0、acquisition_enabled=false、日志pending=false，SD最后已弹出，现场不推定。本轮未调用SDK、USB或SD。
