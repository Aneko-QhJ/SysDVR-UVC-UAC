# 文档索引

> 自动生成，勿手改。重生成：`python3 research/usb-ds-iso/tools/index_docs.py`。
> 当前状态见 [CURRENT.md](CURRENT.md)；历史阶段见 [ARCHIVE_INDEX.md](ARCHIVE_INDEX.md)。

## 当前入口

| 文件 | 说明 |
| --- | --- |
| [CURRENT.md](CURRENT.md) | 唯一当前状态 |
| [../START_HERE.md](../START_HERE.md) | 60 秒上手 |
| [../WORKFLOW.md](../WORKFLOW.md) | 最小研究流程 |
| [../README.md](../README.md) | 研究目录入口 |
| [../README_HISTORY.md](../README_HISTORY.md) | 逐轮时间线（历史） |

## 最近修改

| 文件 | 日期 | 大小 | 摘要 |
| --- | --- | --- | --- |
| [A23_BUFFER_RECYCLE.md](A23_BUFFER_RECYCLE.md) | 2026-10-28 | 2K | A23 事件 terminal： |
| [A23_BUSY_MAP_LEAK.md](A23_BUSY_MAP_LEAK.md) | 2026-10-28 | 3K | 从反编译和反汇编看，Normal producer 的顺序是： |
| [A23_MAILBOX_REPLAY.md](A23_MAILBOX_REPLAY.md) | 2026-10-28 | 2K | `test_mailbox_multiplex.py` 用 `test_patch.Machine` 执行真实 A23 补丁： |
| [A23_PER_URB_ASSEMBLY.md](A23_PER_URB_ASSEMBLY.md) | 2026-10-28 | 1K | [patches/iso_burst_perurb.S](../patches/iso_burst_perurb.S)： |
| [A23_PER_URB_IMPLEMENTATION.md](A23_PER_URB_IMPLEMENTATION.md) | 2026-10-28 | 3K | 把单 mailbox 改成 3 个 0x20 的 mailbox，按 URB 起始槽 `slot/32 % 3` 选择；每个 URB |
| [A23_PER_URB_MAILBOX_DESIGN.md](A23_PER_URB_MAILBOX_DESIGN.md) | 2026-10-28 | 2K | `iso_enter` 每次提交都重置同一个 mailbox： |
| [A23_REARM_BOUNDARY.md](A23_REARM_BOUNDARY.md) | 2026-10-28 | 5K | `0xF601` 是 **`KernelError_SessionClosed`**：第二次/第三次 `PostBufferAsync` 时 |
| [A23_SERIAL_BASELINE.md](A23_SERIAL_BASELINE.md) | 2026-10-28 | 1K | `iso-stream-serial640.nsp`（SHA256 `c129dce7…`）： |
| [A23_SINGLE_MAILBOX_MULTI_URB.md](A23_SINGLE_MAILBOX_MULTI_URB.md) | 2026-10-28 | 2K | `iso_burst_patch.S` 的 `iso_enter` 每次提交都会重置同一个 mailbox： |
| [A23_STREAM_CRASH.md](A23_STREAM_CRASH.md) | 2026-10-28 | 3K | `ISO_PROBE_STREAM` 的 3 缓冲、每 16ms 提交一次实验： |
| [A23_SUSTAINED_STREAM_LIMIT.md](A23_SUSTAINED_STREAM_LIMIT.md) | 2026-10-28 | 4K | 640 池排除了“同 buffer 复用”这个解释：**每个 buffer 只映射一次，仍在约 5 个 URB 后崩**。 |
| [CURRENT.md](CURRENT.md) | 2026-10-28 | 10K | 视频可用；音频不可用。最近一次短包实机主机侧通过、设备侧保存失败；离线路径修正版已存在， |
| [UAC_PCM_PRODUCER.md](UAC_PCM_PRODUCER.md) | 2026-10-28 | 6K | `usb:ds` 的 alt0-only endpoint filter 已用 runtime NOP patch 去掉；alt1 端点可以安装。 |
| [A23_ALT1_ENDPOINT_PATCH.md](A23_ALT1_ENDPOINT_PATCH.md) | 2026-10-27 | 3K | HOS `usb:ds` 的 `FUN_000295d0` 在 bus state 变为 Configured 时，为每个接口/速度解析配置 |
| [A23_ALT1_PROBE.md](A23_ALT1_PROBE.md) | 2026-10-27 | 7K | 目标：在**不引入 UAC / ISO / IPS**的情况下，回答一个最小问题—— |

## 全部文档（259）

| 文件 | 日期 | 大小 | 标题 / 摘要 |
| --- | --- | --- | --- |
| [A23_ALT1_ENDPOINT_PATCH.md](A23_ALT1_ENDPOINT_PATCH.md) | 2026-10-27 | 3K | ALT1 端点安装 patch（2026-10-27） — HOS `usb:ds` 的 `FUN_000295d0` 在 bus state 变为 Configured 时，为每个接口/速度解析配置 |
| [A23_ALT1_PROBE.md](A23_ALT1_PROBE.md) | 2026-10-27 | 7K | ALT1 vendor 探针（2026-10-27） — 目标：在**不引入 UAC / ISO / IPS**的情况下，回答一个最小问题—— |
| [A23_ARCHIVE_READ_VIEW.md](A23_ARCHIVE_READ_VIEW.md) | 2026-10-23 | 6K | 单次归档检查的读取复用候选（2026-10-23） — 隔离候选通过26个原生场景，但本地对照没有可确认的速度收益，暂不接入实机。正常检查的实际文件打开/内容读取从3305次降到1757次，三次候选计时却与原版相近、略高。保留这一负结果，停止继续为该版本扩大模拟或准备实机。 |
| [A23_ARGUMENT_CACHE.md](A23_ARGUMENT_CACHE.md) | 2026-10-15 | 5K | 格式解析器局部入口与参数缓存审查（2026-10-14） — 2026-10-15更正：本页旧工具标为x32/x64的局部取参区域实际由%o分支进入，不能当作 |
| [A23_AUDIO_CADENCE_GAP.md](A23_AUDIO_CADENCE_GAP.md) | 2026-10-27 | 8K | 从有界 ISO burst 到 PCM：速率与调度缺口（2026-10-27） — 后续进展：[固定16TD×24字节候选](A23_SHORT24_OFFLINE_CANDIDATE.md)已完成独立控制器、 |
| [A23_BOOTSTRAP_CAPTURE_MODEL.md](A23_BOOTSTRAP_CAPTURE_MODEL.md) | 2026-10-19 | 6K | 日志建立前中断与描述符取证模型 — 后续：[封存前复读与观察边界模型](A23_CAPTURE_WINDOW_MODEL.md)已验证组件后续变更，并保留最后观察后的变化反例；观察一致不证明来源始终未变。以下保留原阶段。 |
| [A23_BOUND_RECEIVER.md](A23_BOUND_RECEIVER.md) | 2026-10-15 | 7K | A23父输入、运行recipe与ELF的独立绑定候选（2026-10-15） — 已在新的隔离候选中补齐上轮发现的摘要层次缺口。新接收器描述、构建清单、零次数记录、 |
| [A23_BOUNDED_CANDIDATE.md](A23_BOUNDED_CANDIDATE.md) | 2026-10-14 | 8K | A23 联合预检与 trace 预算候选（2026-10-14） — 独立候选补齐两个边界：**BURST在ISO状态/payload改写之前同时检查ISO和ACK范围；每个 |
| [A23_BROKER_MODEL.md](A23_BROKER_MODEL.md) | 2026-10-19 | 6K | A23 监督、消费许可与退出收集的闭环模型 — 后续：[启动前复核与异常退出收集模型](A23_FAILURE_COLLECTION_MODEL.md)已补上报告缺失或损坏时的退出证据封存，并增加启动前来源复核。生产broker与OS级能力隔离仍未实现。以下保留原模… |
| [A23_BUFFER_RECYCLE.md](A23_BUFFER_RECYCLE.md) | 2026-10-28 | 2K | A23 buffer recycle / DMA unmap（2026-10-28） — A23 事件 terminal： |
| [A23_BUSY_MAP_LEAK.md](A23_BUSY_MAP_LEAK.md) | 2026-10-28 | 3K | A23 busy-map leak / 8 项 URB 表（2026-10-28） — 从反编译和反汇编看，Normal producer 的顺序是： |
| [A23_CACHED_BUILD_RELATIONS.md](A23_CACHED_BUILD_RELATIONS.md) | 2026-10-20 | 6K | 缓存构建结构与日志引用关联 — 后续：[缓存中的entry、receipt与SDK session关联](A23_CACHED_SESSION_LINKS.md)已建立两种binding间的数据联系；原生许可/context和时限仍待核验，注入dri… |
| [A23_CACHED_CLOCK_DOMAINS.md](A23_CACHED_CLOCK_DOMAINS.md) | 2026-10-20 | 6K | 缓存时钟域与模型时限算术 — 后续：[缓存来源准入、verifier与静态收集关联](A23_CACHED_COLLECTION_LINKS.md)已完成45场景及49测试；静态收集、外层退出及verifier执行声明分别处理，完整运行认证仍未完成… |
| [A23_CACHED_COLLECTION_LINKS.md](A23_CACHED_COLLECTION_LINKS.md) | 2026-10-20 | 5K | A23 缓存来源准入、verifier与静态收集关联（2026-10-20） — 后续：[缓存外层取证与完整文件清单边界](A23_CACHED_OUTER_FORENSICS.md)已补齐四份外层原字节，覆盖first capture全部96文件；身份/退出仍为保存声明，现场运行未认证。以下保留原… |
| [A23_CACHED_JOURNAL_EPOCHS.md](A23_CACHED_JOURNAL_EPOCHS.md) | 2026-10-20 | 6K | 缓存中的完整日志与两轮事务子集 — 后续：[构建字节分组与有界分片](A23_GROUPED_BUILD_BYTES.md)已将两份外部构建字节装入有界缓存；构建语义、session/receipt及完整SDK链关联仍待核验。以下保留原阶段。 |
| [A23_CACHED_OUTER_FORENSICS.md](A23_CACHED_OUTER_FORENSICS.md) | 2026-10-20 | 5K | A23 缓存外层取证与完整文件清单边界（2026-10-20） — 后续：[原生精确等待与显式时钟域候选](A23_NATIVE_CLOCK_CANDIDATE.md)已完成2333向量及52测试；独立C候选尚未接入冻结driver，真实时钟和现场等待仍未认证。以下保留原阶段。 |
| [A23_CACHED_PERMIT_CONTEXT.md](A23_CACHED_PERMIT_CONTEXT.md) | 2026-10-20 | 6K | 缓存中的模拟发行、原生许可与context关联 — 后续：[缓存时钟域与模型时限算术](A23_CACHED_CLOCK_DOMAINS.md)已建立driver独立域内预算/到达/quiet算术规则，并给出分数最小等待反例；原生与现场时钟认证仍未完成。以下保留原阶段。 |
| [A23_CACHED_SESSION_LINKS.md](A23_CACHED_SESSION_LINKS.md) | 2026-10-20 | 6K | 缓存中的entry、receipt与SDK session关联 — 后续：[缓存中的模拟发行、原生许可与context关联](A23_CACHED_PERMIT_CONTEXT.md)已核对内部许可与外层实际/注入context关系；生产许可和时限仍未认证。以下保留原阶段。 |
| [A23_CAPACITY_V2_CANDIDATE.md](A23_CAPACITY_V2_CANDIDATE.md) | 2026-10-15 | 7K | A23独立V2容量候选（2026-10-15） — 已将[上一轮设计](A23_DIAGNOSTIC_READINESS.md)实现为独立V2候选：**256条trace、32个永久 |
| [A23_CAPTURE_WINDOW_MODEL.md](A23_CAPTURE_WINDOW_MODEL.md) | 2026-10-19 | 5K | 封存前复读与观察边界模型 — 后续：[独立字节视图与硬链接模型](A23_PINNED_BYTE_VIEW_MODEL.md)已验证按外部合同分离字节复制、硬链接拒绝和缓存读取；没有升级为来源实时认证或生产采集许可。以下保留原阶段。 |
| [A23_CHECKED_EXPORT.md](A23_CHECKED_EXPORT.md) | 2026-10-22 | 5K | A23 导出双边校验与接受回执（2026-10-22） — 后继候选：[91件基线、完整来源和消费继承的新真实CLI](A23_LIVE91_CHECKED_READY.md)已封存。下文仅覆盖607来源的历史隔离模型；新候选仍待新的单次实测授权。 |
| [A23_CHILD_SIGNAL_POLICY.md](A23_CHILD_SIGNAL_POLICY.md) | 2026-10-22 | 6K | A23 子进程信号恢复与就绪门槛（2026-10-22） — 本轮问题是上一阶段SIGINT guard使child继承临时屏蔽。新增独立a23_child_signal_bootstrap.py、a23_child_signal_owner.py、audit_a23_child… |
| [A23_COLLECTION_JOURNAL_MODEL.md](A23_COLLECTION_JOURNAL_MODEL.md) | 2026-10-19 | 6K | 收集中断日志与只读取证模型 — 后续：[日志建立前中断与描述符取证模型](A23_BOOTSTRAP_CAPTURE_MODEL.md)已验证引导窗口并补上空/半截标记、无日志和路径替换的只读取证；没有实现恢复或原子快照。以下保留原阶段。 |
| [A23_COMMIT_CONCURRENCY_MODEL.md](A23_COMMIT_CONCURRENCY_MODEL.md) | 2026-10-20 | 4K | A23 提交期间并发发布与缓存诊断关联（2026-10-20） — 后续：[独立worker失败与材料完整性](A23_WORKER_FAILURE_MODEL.md)补13种独立C安排及纯字节拒绝规则；483来源、60测试与搬移重编译通过，本阶段故障尚未接入完整driver。以下保留… |
| [A23_CONTEXT65_BASELINE63.md](A23_CONTEXT65_BASELINE63.md) | 2026-10-18 | 4K | 序号65：独立采用63份只读基线（2026-10-18） — 后续：[序号65首次实测及只读回收](A23_CONTEXT65_FIRST_LIVE.md)已完成，SDK初始化及65..80载荷成功。65权限已消费，69原件已保存并弹出；下文保留原离线研究状态，不能据前后变化单独… |
| [A23_CONTEXT65_FIRST_LIVE.md](A23_CONTEXT65_FIRST_LIVE.md) | 2026-10-18 | 6K | 序号65首次实测与设备回收（2026-10-18） — 后续：[多突发准入与两轮协调器模型](A23_MULTIBURST_ADMISSION.md)已完成离线审查；未发新测试、未改当前设备包或本次65记录。以下保留实测与回收结论。 |
| [A23_CONTEXT65_FLAG_CARD.md](A23_CONTEXT65_FLAG_CARD.md) | 2026-10-18 | 6K | 启动标记的两阶段物理卡适配器（2026-10-18，Asia/Shanghai） — 现场续接：[已只读保存63份且标记已存在](A23_CONTEXT65_FLAG_CARD_LIVE.md)。原正式作业已失败封存，14:11:50+08弹出，无标记写入；下方“planned/SD0”为此前离线状态。 |
| [A23_CONTEXT65_FLAG_CARD_LIVE.md](A23_CONTEXT65_FLAG_CARD_LIVE.md) | 2026-10-18 | 3K | 启动标记现场核验与63份新基线（2026-10-18，Asia/Shanghai） — 后续离线重建已完成：[独立63份基线流程](A23_CONTEXT65_BASELINE63.md)。新版预览接受真实回执，旧59拒绝继续保留；以下为本次现场核验原始结论，未重跑或修改封存证据。 |
| [A23_CONTEXT65_FLAG_REPAIR.md](A23_CONTEXT65_FLAG_REPAIR.md) | 2026-10-18 | 5K | 缺失启动标记的有限修复方案（2026-10-18，Asia/Shanghai） — 续接：[两阶段物理卡适配器](A23_CONTEXT65_FLAG_CARD.md)已离线完成；下方“没有物理卡写入入口”描述原298项模型候选。新正式作业仅准备，实际卡与序号65状态保持。 |
| [A23_CONTEXT65_READINESS.md](A23_CONTEXT65_READINESS.md) | 2026-10-18 | 6K | 序号65的一次流程与最新基线（2026-10-18，Asia/Shanghai） — 续接：[有限标记修复方案及模型](A23_CONTEXT65_FLAG_REPAIR.md)已完成26项专项与6组审计；只有临时目录模型，真实基线及未发行状态保持。下方保留一次流程的完成记录。 |
| [A23_CONTEXT65_RECEIVER.md](A23_CONTEXT65_RECEIVER.md) | 2026-10-18 | 8K | 序号65与执行环境证据候选（2026-10-17，Asia/Shanghai） — 2026-10-18续接：[独立一次流程与最新基线](A23_CONTEXT65_READINESS.md)已完成离线验证；下方“尚未绑定工作流”为2026-10-17历史状态。当前基线仍缺boot2.flag，65.… |
| [A23_CONTROL_BUFFER_CLEANUP.md](A23_CONTROL_BUFFER_CLEANUP.md) | 2026-10-13 | 7K | A23 控制 buffer 复用与退出路径审查（2026-10-13） — 本轮用实际 A23 源码确认两个候选边界：**账本最后排空不证明此前没有复用未知 buffer； |
| [A23_DIAGNOSTIC_READINESS.md](A23_DIAGNOSTIC_READINESS.md) | 2026-10-15 | 9K | A23诊断候选的会话容量与分支证据审查（2026-10-15） — 本轮得到一个具体阻塞：**现有128条trace候选只能在最多两次普通GET_INTERFACE查询后 |
| [A23_DIAGNOSTIC_SINK.md](A23_DIAGNOSTIC_SINK.md) | 2026-10-14 | 7K | A23 独立故障诊断落盘候选（2026-10-14） — 新隔离候选接入**双线程join成功、Finish拒绝后的一次诊断保存**。正常/诊断文件路径独立； |
| [A23_DRIVER_FAULT_MODEL.md](A23_DRIVER_FAULT_MODEL.md) | 2026-10-20 | 5K | A23 driver callback、deadline 与 profile 采样故障回放（2026-10-20） — 后续：[参与式版本时钟快照候选](A23_VERSIONED_CLOCK_CANDIDATE.md)已独立验证43场景与58测试，参与式ABA被拒绝，但绕过契约仍漏检；完整driver未切换，以下两个原反例保持。 |
| [A23_DRIVER_WORKER_FAILURE_MODEL.md](A23_DRIVER_WORKER_FAILURE_MODEL.md) | 2026-10-20 | 6K | A23 完整隔离 driver 的 worker 故障与收集边界（2026-10-20） — 后续：[独立supervisor收集候选](A23_SUPERVISOR_CANDIDATE.md)在不重跑driver下验证18种固定Python进程安排；60测试与493来源搬移通过，进程退出0且driver完成仍… |
| [A23_ELF_BOUNDARIES.md](A23_ELF_BOUNDARIES.md) | 2026-10-14 | 6K | ELF函数边界与异常出口审查（2026-10-14） — 新的独立分析器按ELF符号类型/大小组织实际指令，不再把所有反汇编标签当作函数。两封存候选各核对396个FUNC符号、394个唯一入口，357个有声明大小、37个大小为0；4个局部标签并入所在范围。cache flus… |
| [A23_EP0_CANDIDATE_SINK.md](A23_EP0_CANDIDATE_SINK.md) | 2026-10-13 | 6K | A23 隔离候选的落盘与停止窗口（2026-10-13） — 后续[控制buffer与退出审查](A23_CONTROL_BUFFER_CLEANUP.md)确认：最终排空不排除此前复用，原样__appExit未受正常路径门槛保护；本页保留该阶段实现与验证记录。 |
| [A23_EP0_DISPATCH_AUDIT.md](A23_EP0_DISPATCH_AUDIT.md) | 2026-10-13 | 7K | A23 首次 SDK burst 的 EP0 路径审查（2026-10-13） — 首次 burst 仍为失败。电脑审查进一步缩小了设备停止位置：在同一设备实例、前后 STATUS 有效且 |
| [A23_EP0_HANDLER_CANDIDATE.md](A23_EP0_HANDLER_CANDIDATE.md) | 2026-10-13 | 8K | A23 实际 handler 隔离候选（2026-10-13） — 后续[隔离落盘与停止窗口](A23_EP0_CANDIDATE_SINK.md)已完成电脑检查；本页保留该阶段无sink/触发的历史状态。 |
| [A23_EP0_MEMORY_TRACE.md](A23_EP0_MEMORY_TRACE.md) | 2026-10-13 | 9K | A23有界内存trace原型（2026-10-13） — 后续已完成[实际handler隔离候选](A23_EP0_HANDLER_CANDIDATE.md)：48项源码回放、完整libnx |
| [A23_EP0_TRACE_OWNER.md](A23_EP0_TRACE_OWNER.md) | 2026-10-13 | 8K | A23 trace owner、退出与导出准备（2026-10-13） — 后续已完成[实际handler隔离候选](A23_EP0_HANDLER_CANDIDATE.md)：hooks、停止/交接API、 |
| [A23_ERPT_PREFIX_CORRELATION.md](A23_ERPT_PREFIX_CORRELATION.md) | 2026-10-25 | 5K | 新增ERPT与未闭合生命周期的离线关联（2026-10-25） — 新增ERPT可解释为“检测到强制关机”，但现有材料不能确定是哪次启动、何种触发或哪个模块。四条quiet_enter前缀也不能定位崩溃位置。本次321..368三轮216条trace与27条正常返回生命周期的关联保持成… |
| [A23_EVIDENCE_CONCLUSIONS.md](A23_EVIDENCE_CONCLUSIONS.md) | 2026-10-27 | 9K | 当前合同、证据结论与剩余问题（2026-10-26） — 2026-10-27 推进策略更新：事实和证据边界继续保留，后续流程按 |
| [A23_EXECUTION_READINESS.md](A23_EXECUTION_READINESS.md) | 2026-10-15 | 8K | A23诊断窗口、主机等待与V2材料关联（2026-10-15） — 本轮把[独立V2容量候选](A23_CAPACITY_V2_CANDIDATE.md)继续推进到执行条件审查，发现三个 |
| [A23_EXECUTION_V3_CANDIDATE.md](A23_EXECUTION_V3_CANDIDATE.md) | 2026-10-15 | 9K | A23执行候选：前置过期检查与EXE3保存（2026-10-15） — 已把[上轮执行审查](A23_EXECUTION_READINESS.md)中的两个设备缺口落实到独立候选： |
| [A23_FAILURE_COLLECTION_MODEL.md](A23_FAILURE_COLLECTION_MODEL.md) | 2026-10-19 | 6K | 启动前复核与异常退出收集模型 — 后续：[收集中断日志与只读取证模型](A23_COLLECTION_JOURNAL_MODEL.md)已增加扫描前尝试标记、进程中断保留和不改写原事务的独立取证。原生构建未重编译或执行，生产故障收集与OS级隔离仍未实现… |
| [A23_FINAL_MODEL_COLLECTION.md](A23_FINAL_MODEL_COLLECTION.md) | 2026-10-19 | 5K | A23 异常模型最终收集与独立归档复核 — 后续：[父子进程监督与环境交接模型](A23_MODEL_SUPERVISOR.md)完成真实context辅助程序与超时保留验证；消费许可/最终收集的端到端接入与生产监督器仍待实现。以下保留最终收集阶段结果。 |
| [A23_FIXTURE_JOB_BINDING.md](A23_FIXTURE_JOB_BINDING.md) | 2026-10-21 | 6K | A23 fixture 启动前绑定与退出后关联（2026-10-21） — 后续：[fixture中断发布与恢复拒绝](A23_FIXTURE_PUBLICATION.md)完成517来源、43安排和62测试；新增独占标记同步与receipt分段同步/link发布候选，原launcher未改。… |
| [A23_FIXTURE_PUBLICATION.md](A23_FIXTURE_PUBLICATION.md) | 2026-10-21 | 7K | A23 fixture 中断发布与恢复拒绝（2026-10-21） — 后续：[同步发布接入新离线fixture launcher](A23_INTEGRATED_FIXTURE.md)完成523来源、51安排和64测试；父同步后启动固定child，联合发布与清理准入。仅新离线副本接入，生… |
| [A23_FORMAT_LOOP.md](A23_FORMAT_LOOP.md) | 2026-10-15 | 5K | 当前日志格式的完整渲染与扫描循环回放（2026-10-15） — 本轮续接[字面扫描与初始化](A23_LITERAL_SCAN.md)，执行取参后的真实整数、hex和 |
| [A23_FORMATTER_FRONTIER.md](A23_FORMATTER_FRONTIER.md) | 2026-10-14 | 6K | 日志格式化分派与默认locale审查（2026-10-14） — _svfprintf_r的br x1是受范围检查保护的只读分派表：91个halfword表项对应28个函数内部目标，已按实际ELF和CFG展开。blr x23的初始默认目标则是__utf8_mbtowc，自身用户态栈1… |
| [A23_FS_PATH_SPAN.md](A23_FS_PATH_SPAN.md) | 2026-10-16 | 4K | 文件创建路径缓冲审查（2026-10-16，Asia/Shanghai） — 承接[生命周期首次实测](A23_LIFECYCLE_FIRST_LIVE.md)：两次 SD 打开返回 0，但 diagnostic/EXE3 创建均返回 `0xD401`。本次只做离线审查和原型验证，未读写 SD、… |
| [A23_GROUPED_BUILD_BYTES.md](A23_GROUPED_BUILD_BYTES.md) | 2026-10-20 | 5K | 构建字节分组与有界分片 — 后续：[缓存构建结构与日志引用关联](A23_CACHED_BUILD_RELATIONS.md)已核对冻结成员、头/binary及worker/log/entry引用；完整SDK链和编译来源仍未认证。以下保留原阶段。 |
| [A23_GUARD_CADENCE.md](A23_GUARD_CADENCE.md) | 2026-10-22 | 6K | A23 显式校验边界与计时候选（2026-10-22） — 后续接线：[导出双边检查、接受回执和独立收集器](A23_CHECKED_EXPORT.md)已通过独立控制器模型验证。下文“调用方尚未接入”描述为该阶段历史；新真实91件scope仍待准备。 |
| [A23_GUARD_QUEUE_DESIGN.md](A23_GUARD_QUEUE_DESIGN.md) | 2026-10-25 | 9K | 完整校验与回调的最小队列设计（2026-10-25） — 本轮把[剩余校验研究](A23_LIVE120_RESIDUAL_GUARD.md)推进到具体时序、接线与停止条件，并完成一个文件校验期间的原生dispatch探针。结论是值得继续一个仅针对两次轮间边界的离线候选：保留… |
| [A23_GUARD_SESSION_DIAGNOSTICS.md](A23_GUARD_SESSION_DIAGNOSTICS.md) | 2026-10-14 | 8K | A23 完整会话预算与拒绝诊断（2026-10-14） — 封存guard候选的实际VideoStreamThread已完成28项native回放。完整STATUS→BURST→STATUS |
| [A23_GUARDED_CANDIDATE.md](A23_GUARDED_CANDIDATE.md) | 2026-10-14 | 7K | A23 buffer 复用门槛与统一退出候选（2026-10-14） — 隔离候选已经在 **memcpy/post 之前拒绝未知占用的 buffer 复用**，并将正常退出与 |
| [A23_GUARDIAN_FAILURE.md](A23_GUARDIAN_FAILURE.md) | 2026-10-21 | 6K | A23 guardian 自身中断与管道失效对照（2026-10-21） — 后续：[状态管道显式失败候选](A23_STATUS_TRANSPORT.md)完成541来源、53安排及70测试。新增原始失败frame说明最早窗口也可能在request或ready发送时触发EPIPE；并非每次都到… |
| [A23_GUARDIAN_OWNED.md](A23_GUARDIAN_OWNED.md) | 2026-10-21 | 7K | A23 guardian 直接拥有 worker 的离线对照（2026-10-21） — 后续：[guardian自身中断与管道失效对照](A23_GUARDIAN_FAILURE.md)完成537来源、33安排与64测试。新46个actor仅10个有创建者wait，36个终止但回收未认证；不能把上一阶段存… |
| [A23_HOS_SHARED_SETUP_AUDIT.md](A23_HOS_SHARED_SETUP_AUDIT.md) | 2026-10-13 | 7K | A23 HOS共享SETUP审查（2026-10-13） — 已确认当前Build-ID的HOS usb:ds使用一份8byte最新SETUP存储，接口读取时复制这份存储， |
| [A23_HOST_EXECUTION_LINK.md](A23_HOST_EXECUTION_LINK.md) | 2026-10-15 | 11K | A23主机通知适配与EXE3收集对接（2026-10-15） — 后续实施见[隔离等待入口与SDK启动分离](A23_WAITING_ENTRY.md)：32组完整入口注入及 |
| [A23_INTEGRATED_FIXTURE.md](A23_INTEGRATED_FIXTURE.md) | 2026-10-21 | 6K | A23 同步发布接入离线 fixture launcher（2026-10-21） — 后续：[父中断与worker归属窗口](A23_PARENT_CRASH.md)完成528来源、27安排与64测试。复现owner缺失/半写但worker存在；退出事件不升级为wait，14份孤儿worker终止后的回… |
| [A23_INTEGRATED_MEMORY.md](A23_INTEGRATED_MEMORY.md) | 2026-10-15 | 6K | 新ELF完整格式化与SDK内存指令连续回放（2026-10-15） — 续接[GetSize保护完整候选](A23_LOG_GUARD_ARM_CANDIDATE.md)，重新绑定两个新ELF， |
| [A23_INTEREPOCH_GUARD_WIRING.md](A23_INTEREPOCH_GUARD_WIRING.md) | 2026-10-25 | 7K | 两次轮间后台校验的最小接线（2026-10-25） — [队列设计](A23_GUARD_QUEUE_DESIGN.md)已实现为隔离控制器，并接到冻结三轮entry/driver的临时原生fixture。正常路径两次worker返回、两次job/permit复核、两次恢复… |
| [A23_INTEREST_TRACE.md](A23_INTEREST_TRACE.md) | 2026-10-24 | 6K | Interest通知路径与最小留证候选（2026-10-24） — 后续集成：[当前103件诊断候选](A23_LIVE103_INTEREST_READY.md)已编译封存，含准备期与关机确认后的失败留证，等待新单次授权和现场就绪确认。下文保留此前隔离阶段历史。 |
| [A23_ISO_RETENTION_WINDOW.md](A23_ISO_RETENTION_WINDOW.md) | 2026-10-17 | 6K | ISO 错误保留与接收窗口审查（2026-10-17，Asia/Shanghai） — 三次已保存的 SDK 测试具有同一条更具体的失败路径：**首 TD 匹配到 CC23，补丁锁存错误并保留请求**。在两端帧号属于同一总线帧域的条件下，三次主机窗口都比设备目标帧晚31帧。后续优先验证窗口覆盖假设；尚未确… |
| [A23_ISOLATED_DRIVER_MODEL.md](A23_ISOLATED_DRIVER_MODEL.md) | 2026-10-20 | 4K | A23 完整 driver 的隔离数值时钟回放（2026-10-20） — 后续：[callback/deadline/profile故障回放](A23_DRIVER_FAULT_MODEL.md)新增46场景与60测试通过；可见profile变化拒绝，ABA反例仍通过，不认证原子读取或真实S… |
| [A23_LEAD32_FIRST_LIVE.md](A23_LEAD32_FIRST_LIVE.md) | 2026-10-17 | 7K | lead32 首次有效实测及只读回收（2026-10-17，Asia/Shanghai） — 一次 lead32 ISO burst 收到 **16×192=3072 字节，逐包内容和序号均匹配**。主机、EXE3、primary 和显式上下文匹配的 LCP1 所供证据链完整，设备报告保存和正常返回。这支持接收… |
| [A23_LEAD32_READINESS.md](A23_LEAD32_READINESS.md) | 2026-10-17 | 5K | lead32 判读、收集与一次入口（2026-10-17，Asia/Shanghai） — 后续实测已完成：[lead32首次有效实测及回收](A23_LEAD32_FIRST_LIVE.md)。16包准确载荷及所供设备链完整；新增未归因ERPT仍待查。两条记录均0次、有效记录已回收并弹出。下文“未签发/未启… |
| [A23_LEAD32_RECEIVER.md](A23_LEAD32_RECEIVER.md) | 2026-10-17 | 5K | 提前接收窗口的离线候选（2026-10-17，Asia/Shanghai） — 后续实测已完成：[lead32首次有效实测及回收](A23_LEAD32_FIRST_LIVE.md)。16包准确载荷及所供设备链完整；新增未归因ERPT仍待查。两条记录均0次、有效记录已回收并弹出。下文“未签发/未启… |
| [A23_LEAD32_REPEAT1_LIVE.md](A23_LEAD32_REPEAT1_LIVE.md) | 2026-10-17 | 6K | lead32 独立复现及设备只读回收（2026-10-17） — 用户明确确认“SD已装回、USB已接Mac、Switch完全关机，可以开始这一次新测试”后，签发并消费一条全新repeat1记录。主机确认WAITING后才提示开机；用户已回复“已开机”。本次只启动一次接收器、提交一次… |
| [A23_LEAD32_REPEAT_PREPARATION.md](A23_LEAD32_REPEAT_PREPARATION.md) | 2026-10-17 | 4K | lead32 独立复现准备与ERPT比较（2026-10-17，Asia/Shanghai） — 同固件、同lead32接收器、同预算的独立复现材料已核验，**没有创建新正式记录、启动接收器或读写卡**。当前仍只有[一次有效成功burst](A23_LEAD32_FIRST_LIVE.md)，重复性与稳定性尚未验证。 |
| [A23_LIFECYCLE_CAPSULE_PROTOTYPE.md](A23_LIFECYCLE_CAPSULE_PROTOTYPE.md) | 2026-10-16 | 7K | 无文件状态的退出链审查与阶段记录原型（2026-10-16） — 针对[首次 quiet 实测未留下导出文件](A23_QUIET_FIRST_LIVE_RECOVERY.md)的问题，本轮重新 |
| [A23_LIFECYCLE_CARD_DEPLOYMENT.md](A23_LIFECYCLE_CARD_DEPLOYMENT.md) | 2026-10-16 | 5K | 生命周期候选现场部署（2026-10-16，Asia/Shanghai） — 本页记录两次明确分开的卡操作。用户重新接卡并授权备份、核验和部署；没有授权在本轮启动实机诊断。 |
| [A23_LIFECYCLE_CARD_FILES.md](A23_LIFECYCLE_CARD_FILES.md) | 2026-10-16 | 7K | A23 生命周期候选部署与原件回收工具（2026-10-16） — 已把[新包部署准备](A23_LIFECYCLE_PREPARATION.md)落实为独立文件工具，完成 16 个部署/回收场景及 32 项新增测试；309 项相关回归全部通过，失败、错误、跳过均为 0。完整结果保存在… |
| [A23_LIFECYCLE_CARD_READ.md](A23_LIFECYCLE_CARD_READ.md) | 2026-10-16 | 2K | 现场只读读卡结果（2026-10-16 14:04，Asia/Shanghai） — 用户授权“读卡”后，已识别 UUID 为 `37614F76-3E12-3470-B5C8-52B5A449C213` 的 Switch SD，分区 disk4s1、整盘 disk4、挂载点 `/Volumes/SWI… |
| [A23_LIFECYCLE_DEVICE_CANDIDATE.md](A23_LIFECYCLE_DEVICE_CANDIDATE.md) | 2026-10-16 | 6K | A23 生命周期记录设备候选（2026-10-16） — 已把 [LCP1 阶段记录原型](A23_LIFECYCLE_CAPSULE_PROTOTYPE.md)接入独立设备候选，完成 SDK 文件适配源码、完整 ARM 链接与离线故障验证。240 项相关回归通过，失败、错误… |
| [A23_LIFECYCLE_FIRST_LIVE.md](A23_LIFECYCLE_FIRST_LIVE.md) | 2026-10-16 | 4K | 生命周期候选首次实测及读卡（2026-10-16，Asia/Shanghai） — 用户在部署完成后要求“继续”，核验 213 项来源、旧记录、新包/接收器及真实部署和弹出回执后，签发独立的一次记录。主机先进入 WAITING，用户随后开机进入 CFW，捕获唯一一次 HS 到达并执行一次请求链。没有复… |
| [A23_LIFECYCLE_PREPARATION.md](A23_LIFECYCLE_PREPARATION.md) | 2026-10-16 | 7K | A23 生命周期候选部署包与一次执行入口（2026-10-16） — 已完成[第 4 代接收器](A23_LIFECYCLE_RECEIVER.md)对应的离线部署包、一次记录预览/签发入口及执行流程。277 项相关回归通过，失败、错误、跳过均为 0；最后补充目标磁盘一致性检查后，18 … |
| [A23_LIFECYCLE_RECEIVER.md](A23_LIFECYCLE_RECEIVER.md) | 2026-10-16 | 6K | A23 生命周期候选接收器与回收判读（2026-10-16） — 已为[生命周期设备候选](A23_LIFECYCLE_DEVICE_CANDIDATE.md)建立独立接收器、六项材料绑定及原件收集工具，完成 31 个回收场景与 12 个等待流程模型。新增 19 项测试；连同既有测试… |
| [A23_LINKED_LOG_FILE_STATE.md](A23_LINKED_LOG_FILE_STATE.md) | 2026-10-14 | 5K | 新 ELF 日志调用点与字符串 FILE 状态审查（2026-10-14） — 本轮只读审查[日志修正完整候选](A23_LOG_ARM_CANDIDATE.md)，将实际日志调用与源码格式 |
| [A23_LITERAL_SCAN.md](A23_LITERAL_SCAN.md) | 2026-10-15 | 5K | 默认locale字面扫描与格式化初始化审查（2026-10-15） — 本轮续接[转换入口到取参路径](A23_PARSER_BRIDGE.md)，从既有完整ELF的`_vsnprintf_r` |
| [A23_LIVE103_INTEREST_FIRST_RESULT.md](A23_LIVE103_INTEREST_FIRST_RESULT.md) | 2026-10-25 | 5K | 103件基线候选首次三轮实测（2026-10-25） — 本次一次授权采集完成225..272三轮，主机严格分析和独立重读均通过，共9216正确字节。设备日志唯一匹配三轮请求、状态及URB；关联生命周期确认正常返回。接收器exit0，创建者直接wait，SD已只读回收并安全弹… |
| [A23_LIVE103_INTEREST_READY.md](A23_LIVE103_INTEREST_READY.md) | 2026-10-24 | 6K | 当前103件基线的interest诊断候选（2026-10-24） — 消息留证已接入新的固定三轮入口并编译封存。最终版本绑定当前103件原件、632来源、49..224完整消费历史及81/113/145/177四个旧namespace，只允许新范围225..272。27个原生注入场景与9… |
| [A23_LIVE109_SHORT128_FIRST_RESULT.md](A23_LIVE109_SHORT128_FIRST_RESULT.md) | 2026-10-25 | 8K | 128项候选首测：等待超时与启动卡图标排查（2026-10-25） — 一次273..320许可已经整段消费。本次接收器实际WAITING后，用户报告开机卡在Nintendo Switch图标；主机等待约120.310611秒后超时，未选中目标、未打开SDK、未提交ISO或BURST，收到… |
| [A23_LIVE109_SHORT128_READY.md](A23_LIVE109_SHORT128_READY.md) | 2026-10-25 | 6K | 当前109件基线的固定128项三轮候选（2026-10-25） — 固定128 transaction候选已实现、编译并封存，最终r4通过34个原生注入场景和12项专项检查。绑定636来源、当前109原件、完整49..272消费历史及五个旧namespace；仅允许新范围273..32… |
| [A23_LIVE112_GUARD_METADATA.md](A23_LIVE112_GUARD_METADATA.md) | 2026-10-25 | 6K | 固定128项三轮的完整校验开销与文件类型候选（2026-10-25） — 新的本地分段表明，目录遍历中完整文件属性查询比SHA-256计算更昂贵。一个只把文件类型查询改为lstat的隔离候选，在本次交错重放中将完整校验均值从628.042 ms降到340.839 ms，约减少45.7%；每次… |
| [A23_LIVE112_SHORT128_FIRST_RESULT.md](A23_LIVE112_SHORT128_FIRST_RESULT.md) | 2026-10-25 | 10K | 112件基线固定128项三轮首个传输结果（2026-10-25） — 本次在用户新授权及关机/装卡/USB就绪确认后完成321..368三轮，主机严格分析及独立重读接受，共9216正确字节。用户在实际WAITING提示后报告进入CFW/HOME，接收器exit0并由创建者直接wait，无… |
| [A23_LIVE120_LSTAT_FIRST_RESULT.md](A23_LIVE120_LSTAT_FIRST_RESULT.md) | 2026-10-25 | 8K | 120件基线lstat三轮首测主机结果（2026-10-25） — 本次369..416单次三轮的主机链通过，共9216正确字节，接收器exit0且创建者直接wait，外层启动脚本也exit0。独立消费者重读与原collect输出一致，无abort、interest为空观察前缀。保存至… |
| [A23_LIVE120_LSTAT_READY.md](A23_LIVE120_LSTAT_READY.md) | 2026-10-25 | 6K | 120件基线的lstat固定三轮候选（2026-10-25） — 独立候选已编译、离线接线及环境核验通过，尚未实测。只将完整校验目录遍历中的文件类型查询改为lstat，绑定最近120件原件、完整49..368消费历史与七个旧namespace；拟新范围369..416，一次最多三轮、… |
| [A23_LIVE120_RESIDUAL_GUARD.md](A23_LIVE120_RESIDUAL_GUARD.md) | 2026-10-25 | 6K | lstat后剩余校验开销与持续采集约束（2026-10-25） — 最新三轮369..416的主机与设备链已经闭合：9216正确字节、216条trace、27条生命周期、约30秒正常到期返回；126原件已回收弹出，remaining0。本轮继续离线研究，重核最新交接及其八组封存证据、6… |
| [A23_LIVE126_INTEREPOCH_FIRST_RESULT.md](A23_LIVE126_INTEREPOCH_FIRST_RESULT.md) | 2026-10-25 | 7K | 126件候选：轮间worker三轮实测及读卡结果（2026-10-25） — 本次单次最多三轮417..464已完成，主机和设备链一致：417/433/449三轮各3072正确字节，共9216，URB387/403/419；唯一新增execution含216条trace，无丢失/无效，关联27条… |
| [A23_LIVE126_INTEREPOCH_LAUNCH_PLAN.md](A23_LIVE126_INTEREPOCH_LAUNCH_PLAN.md) | 2026-10-25 | 6K | 126件候选的一次性启动计划审查（2026-10-25） — [651来源/126件候选](A23_LIVE126_INTEREPOCH_READY.md)的一次性启动计划已准备并审查。launcher、专用workflow、生成workflow和原生scope一致；沙箱外仅查询… |
| [A23_LIVE126_INTEREPOCH_READY.md](A23_LIVE126_INTEREPOCH_READY.md) | 2026-10-25 | 6K | 126件基线的轮间后台校验候选（2026-10-25） — 独立候选已编译封存，原生与Python校验通过。651来源、126件当前回收快照、完整49..416消费历史和spent369现已绑定；软件描述范围为417..464，尚未保留或授权。实际许可remaining0，未启… |
| [A23_LIVE132_COMPLETION_OFFLINE.md](A23_LIVE132_COMPLETION_OFFLINE.md) | 2026-10-26 | 8K | 导出后的单次队列续接与终结证据（2026-10-26） — 已离线修补[末端边界审查](A23_POSTEXPORT_BOUNDARY.md)中的四种确定性反例：最后比较或接受回执之后进入的interest、旧ISO回调，以及排在导出工作块后面的provider入口，现在会在新… |
| [A23_LIVE132_Q1_FIRST_RESULT.md](A23_LIVE132_Q1_FIRST_RESULT.md) | 2026-10-26 | 6K | Q1 首次实测与只读回收结果（2026-10-26） — 本次 672 来源候选的单次 Q1 实测完成：465/481/497 三轮各 3072 个正确字节，共 9216；主机服务窗口和终结事实通过，独立消费者复算一致，设备 trace、STATUS、序号和 URB 唯一对应… |
| [A23_LIVE132_Q1_LAUNCH_PLAN.md](A23_LIVE132_Q1_LAUNCH_PLAN.md) | 2026-10-26 | 5K | Q1 一次性计划与只读上下文核对（2026-10-26） — Q1 的一次性启动计划已完成离线审查，采用 r1；当前没有新实测、人工授权、序号保留或消费。当前 `remaining=0`、`acquisition_enabled=false`。软件能力已实现不增加执行权限。 |
| [A23_LIVE132_Q1_SOFTWARE_READY.md](A23_LIVE132_Q1_SOFTWARE_READY.md) | 2026-10-26 | 9K | Q1：新末轮合同的真实入口软件准备（2026-10-26） — 已完成[Q1问题卡](A23_EVIDENCE_CONCLUSIONS.md)的真实入口、工作流、独立消费者与失败回收软件接线。最终选r4：10个原生场景、13项模式/许可拒绝及8项坏失败材料语义拒绝通过。正常及较密服… |
| [A23_LIVE132_TERMINAL_OFFLINE.md](A23_LIVE132_TERMINAL_OFFLINE.md) | 2026-10-26 | 8K | 当前132件接收器的末轮观察适配（2026-10-26） — 已将[独立末轮控制器](A23_TERMINAL_OBSERVATION_WIRING.md)接到实际生成的driver、entry、coordinator和原checked export。当前132件基线、完整49.… |
| [A23_LIVE75_FIRST_RESULT.md](A23_LIVE75_FIRST_RESULT.md) | 2026-10-22 | 6K | A23 同接口两轮实测结果（2026-10-22） — 后续电脑研究：[显式校验去重与计时候选](A23_GUARD_CADENCE.md)已完成隔离原生验证；真实controller尚未采用，本次实测原件和结论保持。 |
| [A23_LIVE75_TWO_EPOCH_READY.md](A23_LIVE75_TWO_EPOCH_READY.md) | 2026-10-22 | 7K | A23 当前75件基线的两轮实测候选（2026-10-22） — 最新实测结果（2026-10-22）：[同接口两轮成功及时间线](A23_LIVE75_FIRST_RESULT.md)已核对。一次采集完成113..128和129..144，两个新URB387/403共6144正确字… |
| [A23_LIVE91_CHECKED_READY.md](A23_LIVE91_CHECKED_READY.md) | 2026-10-23 | 6K | A23 当前91件基线的双边校验实测候选（2026-10-22） — 本候选已于2026-10-23完成一次实测、日志回收及安全弹出，145..176耗尽、remaining0；[两轮及双边回执结果](A23_LIVE91_FIRST_RESULT.md)。新快照为97件，以下准备时状态… |
| [A23_LIVE91_CRITICAL_PATH.md](A23_LIVE91_CRITICAL_PATH.md) | 2026-10-23 | 5K | 双轮间隔的关键路径（2026-10-23） — 本轮只分析封存日志，并对临时文件副本做原生只读重放。没有Switch/USB/SD访问、真实SDK对象、新授权、正式保留或消费；611来源、已完成实测记录及历史namespace保持不变。 |
| [A23_LIVE91_FIRST_RESULT.md](A23_LIVE91_FIRST_RESULT.md) | 2026-10-23 | 4K | 91件基线候选首次实测结果（2026-10-23） — 本次已完成一次授权采集：同接口两轮145..160、161..176均通过主机严格分析，合计6144正确字节；真实SDK路径的导出前后检查与接受回执完整。设备记录唯一对应这两轮，关联生命周期报告正常返回。SD已只读回收… |
| [A23_LIVE97_THREE_FIRST_RESULT.md](A23_LIVE97_THREE_FIRST_RESULT.md) | 2026-10-24 | 4K | 三轮候选首次实测与读卡结果（2026-10-24） — 本次一次许可及177..224整段已耗尽，整体失败、不重试。前两轮177..192、193..208保存了6144正确字节，STATUS/ISO7及设备URB关联一致；第三轮尚未提交，主机因`paired_resour… |
| [A23_LIVE97_THREE_READY.md](A23_LIVE97_THREE_READY.md) | 2026-10-23 | 7K | 当前97件基线的固定三轮候选（2026-10-23） — 完整三轮主机入口已编译封存：当前97件原件、623来源、49..176完整消费历史与三个旧namespace进入校验；新scope只允许177..224，最多三轮。原生固定48许可、三组失败owner快照、STATUS… |
| [A23_LIVE_TWO_EPOCH_CLI.md](A23_LIVE_TWO_EPOCH_CLI.md) | 2026-10-22 | 10K | A23 真实两轮CLI、一次许可与失败留证（2026-10-22） — 最新实测结果（2026-10-22）：[同接口两轮成功及时间线](A23_LIVE75_FIRST_RESULT.md)已核对。一次采集完成113..128和129..144，两个新URB387/403共6144正确字… |
| [A23_LIVE_TWO_EPOCH_FIRST_RESULT.md](A23_LIVE_TWO_EPOCH_FIRST_RESULT.md) | 2026-10-22 | 8K | A23 真实两轮入口首次实测与只读回收（2026-10-22） — 最新实测结果（2026-10-22）：[同接口两轮成功及时间线](A23_LIVE75_FIRST_RESULT.md)已核对。一次采集完成113..128和129..144，两个新URB387/403共6144正确字… |
| [A23_LOG_ARM_CANDIDATE.md](A23_LOG_ARM_CANDIDATE.md) | 2026-10-14 | 5K | 日志限长与类型修正完整 ARM 候选（2026-10-14） — 本轮将[日志契约审查](A23_LOG_CONTRACT.md)的三文件修正接入新的完整隔离源码树。 |
| [A23_LOG_CONTRACT.md](A23_LOG_CONTRACT.md) | 2026-10-14 | 6K | 日志格式、长度与类型契约审查（2026-10-14） — 两份封存候选的13个C单元各预处理出76处日志调用，仅使用d/s/u/x及已有ll长度和固定宽度，没有浮点、宽字符、位置参数或动态宽度。加入printf格式检查声明后，原代码各发现1处真实类型不匹配：ISO timin… |
| [A23_LOG_GUARD_ARM_CANDIDATE.md](A23_LOG_GUARD_ARM_CANDIDATE.md) | 2026-10-15 | 6K | 日志大小读取失败保护的完整ARM隔离候选（2026-10-15） — 续接[SDK内存函数与日志保护](A23_SDK_MEMORY_LOG_GUARD.md)，将GetSize失败保护接入 |
| [A23_MAILBOX_REPLAY.md](A23_MAILBOX_REPLAY.md) | 2026-10-28 | 2K | A23 三 URB in-flight mailbox replay（2026-10-28） — `test_mailbox_multiplex.py` 用 `test_patch.Machine` 执行真实 A23 补丁： |
| [A23_MODEL_SUPERVISOR.md](A23_MODEL_SUPERVISOR.md) | 2026-10-19 | 5K | A23 父子进程监督与环境交接模型 — 后续：[监督、消费许可与退出收集闭环模型](A23_BROKER_MODEL.md)已接通假SDK模型并验证真实环境拒绝；生产broker/现场入口仍未实现。以下保留context-only监督阶段及其5秒约束。 |
| [A23_MULTIBURST_ADMISSION.md](A23_MULTIBURST_ADMISSION.md) | 2026-10-18 | 5K | 从单次突发到两轮串行：离线准入研究（2026-10-18） — 后续：[补丁双轮发布与旧事件代际](A23_REARM_GENERATIONS.md)完成离线重放，含第16轮地址别名反例；本页保留原服务/协调器模型结果。 |
| [A23_NATIVE_CLOCK_CANDIDATE.md](A23_NATIVE_CLOCK_CANDIDATE.md) | 2026-10-20 | 5K | A23 原生精确等待与显式时钟域候选（2026-10-20） — 后续：[独立quiet轮询与deadline适配候选](A23_QUIET_POLL_CANDIDATE.md)已验证完成事件/guard/失败撤销及arrival/poll边界；未接入冻结Objective-C dr… |
| [A23_NEXT_LIVE_TWO_EPOCH.md](A23_NEXT_LIVE_TWO_EPOCH.md) | 2026-10-22 | 10K | A23 下一项实机研究：同一次启动内两轮串行（2026-10-22） — 最新实测结果（2026-10-22）：[同接口两轮成功及时间线](A23_LIVE75_FIRST_RESULT.md)已核对。一次采集完成113..128和129..144，两个新URB387/403共6144正确字… |
| [A23_PAIRED_SDK_RESOURCES.md](A23_PAIRED_SDK_RESOURCES.md) | 2026-10-18 | 7K | 两轮SDK资源能力与离线验证（2026-10-18） — 后续：[独立SDK两轮驱动与联合回执](A23_TWO_EPOCH_SDK_DRIVER.md)已完成编译和假operations验证；真实映射/双轮未测，旧离线协调器保持拒绝SDK资源。以下为本阶段历史结果。 |
| [A23_PARENT_CRASH.md](A23_PARENT_CRASH.md) | 2026-10-21 | 6K | A23 父进程中断、worker 归属与退出观察（2026-10-21） — 后续：[guardian直接拥有worker的离线对照](A23_GUARDIAN_OWNED.md)完成532来源、36安排与64测试。本轮28个新worker由guardian直接wait；旧14个非子进程work… |
| [A23_PARSER_BRIDGE.md](A23_PARSER_BRIDGE.md) | 2026-10-15 | 5K | 转换入口到真实取参路径审查（2026-10-15） — 本轮续接[参数缓存局部审查](A23_ARGUMENT_CACHE.md)，将实际转换入口、字符读取、 |
| [A23_PATH_SPAN_CARD_DEPLOYMENT.md](A23_PATH_SPAN_CARD_DEPLOYMENT.md) | 2026-10-16 | 3K | 路径缓冲候选现场部署（2026-10-16，Asia/Shanghai） — 用户按提示保持 Switch 关机并回复“已接好”后，已完成新候选备份、部署、读回和安全弹出。操作目录名沿用 19:12 准备脚本时的标识；实际弹出时间为 **22:54:35+08**。本轮未签发一次记录或启动实机测… |
| [A23_PATH_SPAN_DEVICE_CANDIDATE.md](A23_PATH_SPAN_DEVICE_CANDIDATE.md) | 2026-10-16 | 4K | 完整路径缓冲设备候选（2026-10-16，Asia/Shanghai） — 承接[路径跨度审查](A23_FS_PATH_SPAN.md)，已从首次实测生命周期候选复制出独立设备候选，接入五条诊断保存路径的完整缓冲。原已部署程序、旧接收器、包和现场证据保持不变；本轮没有访问 SD 或启动 US… |
| [A23_PATH_SPAN_FIRST_LIVE.md](A23_PATH_SPAN_FIRST_LIVE.md) | 2026-10-17 | 5K | 路径缓冲候选首次测试（2026-10-17，Asia/Shanghai） — 用户明确要求“开始测试”后，核验 233 项来源、旧记录、第 5 代接收器、新包及真实部署/弹出回执，签发并消费唯一一次新记录。主机 WAITING 先于新的 HS 到达，用户随后确认“已开机”；执行一次请求链，无自动… |
| [A23_PATH_SPAN_MATERIALS.md](A23_PATH_SPAN_MATERIALS.md) | 2026-10-16 | 4K | 路径缓冲候选接收器、判读与部署包（2026-10-16，Asia/Shanghai） — 已为[完整路径缓冲候选](A23_PATH_SPAN_DEVICE_CANDIDATE.md)构建独立的第 5 代接收器和原件收集工具，并完成对应 NSP 包转换及核验。正式设备 ELF、recipe、NPDM、配置保… |
| [A23_PATH_SPAN_READINESS.md](A23_PATH_SPAN_READINESS.md) | 2026-10-16 | 4K | 新路径候选部署与一次诊断入口（2026-10-16，Asia/Shanghai） — 已将[第 5 代接收器及新包](A23_PATH_SPAN_MATERIALS.md)接入独立卡文件工具、签发入口和执行工作流。旧工具/材料继续保持原身份。本次只在电脑临时目录演练，没有访问真实卡、创建正式一次记录或启… |
| [A23_PER_URB_ASSEMBLY.md](A23_PER_URB_ASSEMBLY.md) | 2026-10-28 | 1K | A23 per-URB mailbox 汇编候选（2026-10-28） — [patches/iso_burst_perurb.S](../patches/iso_burst_perurb.S)： |
| [A23_PER_URB_IMPLEMENTATION.md](A23_PER_URB_IMPLEMENTATION.md) | 2026-10-28 | 3K | A23 per-URB mailbox 实现草案（2026-10-28） — 把单 mailbox 改成 3 个 0x20 的 mailbox，按 URB 起始槽 `slot/32 % 3` 选择；每个 URB |
| [A23_PER_URB_MAILBOX_DESIGN.md](A23_PER_URB_MAILBOX_DESIGN.md) | 2026-10-28 | 2K | A23 per-URB mailbox 设计（2026-10-28） — `iso_enter` 每次提交都重置同一个 mailbox： |
| [A23_PINNED_BYTE_VIEW_MODEL.md](A23_PINNED_BYTE_VIEW_MODEL.md) | 2026-10-19 | 6K | 独立字节视图与硬链接模型 — 后续：[固定字节视图的只读语义消费者](A23_PINNED_SEMANTIC_CONSUMER.md)已完成六份材料的部分关系检查，保持完整链、事务和现场认证字段为false。以下保留原阶段。 |
| [A23_PINNED_SEMANTIC_CONSUMER.md](A23_PINNED_SEMANTIC_CONSUMER.md) | 2026-10-19 | 5K | 固定字节视图的只读语义消费者 — 后续：[缓存中的完整日志与两轮事务子集](A23_CACHED_JOURNAL_EPOCHS.md)已固定完整92份原始材料并检查封存/事务/STATUS；完整SDK链和外部构建仍未认证。以下保留原阶段。 |
| [A23_POSTCOMPLETION_STATUS_VIEW.md](A23_POSTCOMPLETION_STATUS_VIEW.md) | 2026-10-26 | 7K | 最终采样之后的状态表述（2026-10-26） — 已完成[终结采样修补](A23_LIVE132_COMPLETION_OFFLINE.md)之后的语义核对，并增加只读归档状态视图。6个原生诊断场景、13项拒绝检查和2种CLI展示通过。结论是：历史采样通过与后来观察到… |
| [A23_POSTEXPORT_BOUNDARY.md](A23_POSTEXPORT_BOUNDARY.md) | 2026-10-26 | 8K | 最终导出之后的故障检测边界（2026-10-26） — 已在冻结[132件接收器](A23_LIVE132_TERMINAL_OFFLINE.md)中复现一个明确的末端缺口：最后一次live状态比较之后，接受回执写入和loop成功之间没有再次健康检查。此时已经进入provi… |
| [A23_PRERETAINED_OWNER.md](A23_PRERETAINED_OWNER.md) | 2026-10-22 | 6K | A23 启动前预保留进程对象（2026-10-22） — 后续：[原生PID窗口与SIGINT暂缓对照](A23_SIGINT_GUARD.md)完成575来源、两轮9安排与78测试。SIGINT暂缓覆盖指定信号安排，同步异常仍有真实未登记child；child还继承SIGI… |
| [A23_Q2_OWNERSHIP_CONTRACT.md](A23_Q2_OWNERSHIP_CONTRACT.md) | 2026-10-26 | 9K | Q2 资源所有权、复用与证据容量合同（2026-10-26） — 后续[Q2a交还能力表](A23_Q2A_SDK_HANDOFF_CAPABILITIES.md)已完成11份官方页面/4份SDK头文件/14路径资料核对，明确原生完整交还仍未证明；下一项仅离线Q2b归属与准入候选。下… |
| [A23_Q2A_SDK_HANDOFF_CAPABILITIES.md](A23_Q2A_SDK_HANDOFF_CAPABILITIES.md) | 2026-10-26 | 9K | Q2a SDK 交还能力表（2026-10-26） — 后续[Q2b有限归属模型](A23_Q2B_GENERATION_MODEL.md)已完成34项测试及5760种有限事件安排；原生交还仍是假设，未接SDK或真实入口。以下为本阶段能力核对及当时下一步，原封存保持。 |
| [A23_Q2B_GENERATION_MODEL.md](A23_Q2B_GENERATION_MODEL.md) | 2026-10-27 | 7K | Q2b 有限 slot/generation 离线模型（2026-10-26） — 后续[Q2c整轮证据预算与交接合同](A23_Q2C_EVIDENCE_BUDGET_CONTRACT.md)已完成部署来源、边界和容量核对；下一项仅电脑设计整轮额度租约/停止门。下文为本模型阶段及当时下一步，原封存保… |
| [A23_Q2C_EPOCH_LEASE_MODEL.md](A23_Q2C_EPOCH_LEASE_MODEL.md) | 2026-10-27 | 6K | Q2c 整轮额度租约与停止门离线候选（2026-10-27） — 当前研究组织方式见 [研究规则](RESEARCH_RULES.md)。本文保留该模型的实际能力及未证明项； |
| [A23_Q2C_EVIDENCE_BUDGET_CONTRACT.md](A23_Q2C_EVIDENCE_BUDGET_CONTRACT.md) | 2026-10-27 | 8K | Q2c 整轮证据预算、停止与交接合同（2026-10-27） — 后续[单段整轮额度租约模型](A23_Q2C_EPOCH_LEASE_MODEL.md)已完成38项检查；仍无真实设备grant或全局互斥。下一项仅电脑定义设备额度回执协议与握手预算。下文为本来源合同阶段及当时下一步，… |
| [A23_QUIET_CARD_DEPLOYMENT.md](A23_QUIET_CARD_DEPLOYMENT.md) | 2026-10-16 | 3K | quiet 候选读卡与部署（2026-10-16） — 按用户“读卡，部署文件”的指令，已完成 SD 身份/旧版本核验、原件回收与备份、quiet |
| [A23_QUIET_DEPLOYMENT_REVIEW.md](A23_QUIET_DEPLOYMENT_REVIEW.md) | 2026-10-16 | 7K | quiet 候选部署包与回收判读（2026-10-16） — 本轮把[接口 2 诊断方案](A23_QUIET_DIAGNOSTIC_PREPARATION.md)推进到可审阅的离线部署包： |
| [A23_QUIET_DIAGNOSTIC_PREPARATION.md](A23_QUIET_DIAGNOSTIC_PREPARATION.md) | 2026-10-16 | 8K | 独立接口 2 诊断准备方案（2026-10-16） — 本方案把[quiet 路径核验](A23_QUIET_PATHS.md)收敛为一次可审阅的分支取证流程，目标是 |
| [A23_QUIET_DRIVER_COPY.md](A23_QUIET_DRIVER_COPY.md) | 2026-10-20 | 5K | A23 driver隔离副本与时钟桥验证（2026-10-20） — 后续：[完整driver隔离数值时钟回放](A23_ISOLATED_DRIVER_MODEL.md)已在裁剪的注入模型中执行相同候选，19场景与60测试通过；真实SDK/现场时钟与生产许可仍未认证。以下保留原阶段。 |
| [A23_QUIET_FIRST_LIVE_HOST.md](A23_QUIET_FIRST_LIVE_HOST.md) | 2026-10-16 | 4K | quiet 候选首次实测：主机结果与待回收材料（2026-10-16） — 用户在说明一次诊断及“先主机预等待，再提示开机”后回复“开始”，据此签发并消费 |
| [A23_QUIET_FIRST_LIVE_RECOVERY.md](A23_QUIET_FIRST_LIVE_RECOVERY.md) | 2026-10-16 | 5K | quiet 首次实测的读卡回收：未找到导出文件（2026-10-16） — 按用户“读卡吧”的指令，核对同一 SD 的 UUID 后卸载并重新只读挂载，保存部署文件、 |
| [A23_QUIET_ONCE_READY.md](A23_QUIET_ONCE_READY.md) | 2026-10-16 | 4K | 一次 quiet 诊断的签发入口与现场交接（2026-10-16） — 用户已确认可以配合完全关机、取放 SD 和按现有方式启动 CFW。该回复确认现场操作 |
| [A23_QUIET_PATHS.md](A23_QUIET_PATHS.md) | 2026-10-16 | 7K | quiet ELF 等待、静默与保存路径核验（2026-10-16） — 已对[当前接收器绑定的 quiet 设备程序](A23_QUIET_RECEIVER.md)重新绑定实际指令、格式 |
| [A23_QUIET_POLL_CANDIDATE.md](A23_QUIET_POLL_CANDIDATE.md) | 2026-10-20 | 5K | A23 独立quiet轮询与deadline适配候选（2026-10-20） — 后续：[driver隔离副本与时钟桥验证](A23_QUIET_DRIVER_COPY.md)已生成完整driver补丁并编译对象，27个Foundation桥场景及58测试通过；完整SDK模型尚未执行，profile… |
| [A23_QUIET_RECEIVER.md](A23_QUIET_RECEIVER.md) | 2026-10-15 | 6K | A23 quiet 候选接收器与六项材料收集（2026-10-15） — 已把[隔离捕获与文本日志的设备候选](A23_QUIET_WINDOW_CANDIDATE.md)接入新独立接收器、 |
| [A23_QUIET_WINDOW_CANDIDATE.md](A23_QUIET_WINDOW_CANDIDATE.md) | 2026-10-15 | 7K | A23 隔离捕获与文本日志的诊断候选（2026-10-15） — 已实现上一轮约定的最小设备候选：30 秒诊断窗口只推进 USB 请求，视频和音频工作 |
| [A23_READONLY_SCOPE_VERIFIER.md](A23_READONLY_SCOPE_VERIFIER.md) | 2026-10-19 | 5K | A23 只读来源复核器、独立构建与联合回执 — 后续：[异常模型最终收集与独立归档复核](A23_FINAL_MODEL_COLLECTION.md)完成退出后文件收集与只读CLI；现场故障收集/采集仍未接通。以下保留来源复核阶段结果。 |
| [A23_REARM_BOUNDARY.md](A23_REARM_BOUNDARY.md) | 2026-10-28 | 5K | A23 re-arm / 缓冲复用边界（2026-10-27） — `0xF601` 是 **`KernelError_SessionClosed`**：第二次/第三次 `PostBufferAsync` 时 |
| [A23_REARM_GENERATIONS.md](A23_REARM_GENERATIONS.md) | 2026-10-18 | 6K | 第二次发布、事件代际与主机存储（2026-10-18） — 后续：[独立两轮离线协调器与归档核验](A23_TWO_EPOCH_RECEIVER.md)已实现并验证；本页保留原ARM重放及第16轮代际反例。 |
| [A23_SDK_INIT_ENVIRONMENT.md](A23_SDK_INIT_ENVIRONMENT.md) | 2026-10-18 | 8K | SDK初始化错误与启动标记审查（2026-10-17，Asia/Shanghai） — 后续：[序号65首次实测及只读回收](A23_CONTEXT65_FIRST_LIVE.md)已完成，SDK初始化及65..80载荷成功。65权限已消费，69原件已保存并弹出；下文保留原离线研究状态，不能据前后变化单独… |
| [A23_SDK_MEMORY_LOG_GUARD.md](A23_SDK_MEMORY_LOG_GUARD.md) | 2026-10-15 | 6K | SDK内存函数边界与日志大小读取失败保护（2026-10-15） — 续接[完整格式化循环回放](A23_FORMAT_LOOP.md)，本轮完成两配置1282组SDK内存函数 |
| [A23_SEQUENCE_FIRST_LIVE.md](A23_SEQUENCE_FIRST_LIVE.md) | 2026-10-17 | 5K | 序号49首次实测（2026-10-17） — 续接：[SDK初始化与启动标记审查](A23_SDK_INIT_ENVIRONMENT.md)已完成；执行模式差异和外层错误覆盖有证据，实机根因仍未确认。下方保留实测与回收原始结论。 |
| [A23_SEQUENCE_READINESS.md](A23_SEQUENCE_READINESS.md) | 2026-10-17 | 5K | 序号49的一次流程准备（2026-10-17） — 后续状态：序号49..64已在一次授权测试中永久保留，主机于SDK初始化失败且未提交ISO。59原件已回收并弹出，但boot2.flag缺失，部署核验未通过；见[首次实测及回收](A23_SEQUENCE_FIRST_… |
| [A23_SEQUENCE_RECEIVER.md](A23_SEQUENCE_RECEIVER.md) | 2026-10-17 | 6K | 历史范围绑定的序号主机候选（2026-10-17） — 后续更新：正式一次流程已完成离线接入和验证，见[序号49流程准备](A23_SEQUENCE_READINESS.md)。本页保留候选构建阶段的历史状态；49..64仍未正式保留，本轮无实机测试。 |
| [A23_SEQUENCE_WITNESS.md](A23_SEQUENCE_WITNESS.md) | 2026-10-17 | 6K | 跨端会话关联与起始序号可行性（2026-10-17） — 离线复核确认：当前SETUP顺序和状态比较不能区分两次成功运行的设备文件。现有设备协议已把主机指定的16位起始序号传到STATUS、trace和16个ISO包；可以优先准备一个绑定不同起始序号的新主机候选，以提高已知旧… |
| [A23_SERIAL_BASELINE.md](A23_SERIAL_BASELINE.md) | 2026-10-28 | 1K | A23 one-in-flight 串行基线（2026-10-28） — `iso-stream-serial640.nsp`（SHA256 `c129dce7…`）： |
| [A23_SERVICE_OBSERVATION_OFFLINE.md](A23_SERVICE_OBSERVATION_OFFLINE.md) | 2026-10-25 | 7K | 末轮观察的队列服务证据候选（2026-10-25） — 继续离线审查[417..464实测](A23_LIVE126_INTEREPOCH_FIRST_RESULT.md)，结论是下一项应补末轮观察证据，而不是重复相同三轮或继续缩短ISO空槽。本轮核对旧证据/可变票据后，新… |
| [A23_SESSION_ARM_CANDIDATE.md](A23_SESSION_ARM_CANDIDATE.md) | 2026-10-14 | 8K | 启动关联与独立保存ARM候选（2026-10-14） — 在上一轮启动ARM候选的新副本中接入REL1：VideoThread在Ep0CandidateStart成功后发布既有writer/boot/session nonce，main在诊断保存返回后发布绑定该份DIA1输入… |
| [A23_SESSION_CONCURRENCY_STACK.md](A23_SESSION_CONCURRENCY_STACK.md) | 2026-10-14 | 7K | 关联发布/中断与最终ELF栈审查（2026-10-14） — 上一轮REL1候选的并发与中断边界已补验：未release的context/receipt不会成为已发布数据；runtime capture未返回或中断时不会输出成功文件，第一份快照完成后也不能升级或覆盖。所有生产、候… |
| [A23_SESSION_CORRELATION.md](A23_SESSION_CORRELATION.md) | 2026-10-14 | 6K | 启动与EP0会话关联原型（2026-10-14） — 新增独立EP0REL1内存封装，关联当前启动journal、已停止且双join的EP0诊断、admission计数和已返回的旧DIA1保存结果。失败join/缺少context在读取owner、guard、admiss… |
| [A23_SHARED_SEQUENCE32_NATIVE_PERMIT.md](A23_SHARED_SEQUENCE32_NATIVE_PERMIT.md) | 2026-10-19 | 8K | 共享32序号账本与原生文件许可（2026-10-19） — 后续：[只读来源复核器与独立构建](A23_READONLY_SCOPE_VERIFIER.md)完成文件/注入模型验证；正式发行与现场acquire保持关闭，失败最终收集器尚待实现。以下保留共享账本阶段结果。 |
| [A23_SHORT24_FIRST_LIVE.md](A23_SHORT24_FIRST_LIVE.md) | 2026-10-27 | 5K | 短包首次实测：主机观察通过，设备保存失败（2026-10-27） — 本轮已完成配套部署、唯一一次采集、关机后只读回收与分析。主机收到了连续的 |
| [A23_SHORT24_OFFLINE_CANDIDATE.md](A23_SHORT24_OFFLINE_CANDIDATE.md) | 2026-10-27 | 7K | 固定 16TD×24 字节短包候选（2026-10-27） — 后续[SDK组件与设备关系核验](A23_SHORT24_SDK_AND_RELATION.md)已完成：21个原生注入场景 |
| [A23_SHORT24_ONCE_PLAN.md](A23_SHORT24_ONCE_PLAN.md) | 2026-10-27 | 4K | 一次24字节短包诊断问题卡（已执行并回收，次数已消耗） — 已完成[首次短包实测与回归修正](A23_SHORT24_FIRST_LIVE.md)。配套NSP/IPS部署核验后， |
| [A23_SHORT24_PACKAGE_AND_ENTRY.md](A23_SHORT24_PACKAGE_AND_ENTRY.md) | 2026-10-27 | 6K | 短包配套包、驻留入口与写盘（2026-10-27） — 本配套包已用于[首次短包实测](A23_SHORT24_FIRST_LIVE.md)：主机384字节观察通过，设备保存失败。 |
| [A23_SHORT24_SDK_AND_RELATION.md](A23_SHORT24_SDK_AND_RELATION.md) | 2026-10-27 | 6K | 短包 SDK 组件与设备侧录关系（2026-10-27） — 后续[NSP/IPS配套包、驻留入口与写盘](A23_SHORT24_PACKAGE_AND_ENTRY.md)已完成离线准备和 |
| [A23_SHORT_WINDOW_SCOPE.md](A23_SHORT_WINDOW_SCOPE.md) | 2026-10-25 | 7K | 三轮节奏与128项接收窗口审查（2026-10-25） — 本次只分析封存文件，632来源及五个消费namespace保持，没有USB、SD、新SDK对象、原生编译、新授权或范围保留。结论是下一项值得实现独立的固定128 transaction候选，检验缩短接收窗口后能否仍严格… |
| [A23_SIGINT_GUARD.md](A23_SIGINT_GUARD.md) | 2026-10-22 | 7K | A23 原生PID窗口与SIGINT暂缓对照（2026-10-22） — 后续：[子进程信号恢复与就绪门槛](A23_CHILD_SIGNAL_POLICY.md)完成579来源、两轮20场景与78测试。普通child的临时INT屏蔽在Python启动后恢复，就绪后再发送取样请求；仍不是pr… |
| [A23_SINGLE_MAILBOX_MULTI_URB.md](A23_SINGLE_MAILBOX_MULTI_URB.md) | 2026-10-28 | 2K | A23 单 mailbox 与多 URB in flight（2026-10-28） — `iso_burst_patch.S` 的 `iso_enter` 每次提交都会重置同一个 mailbox： |
| [A23_SPAWN_BOUNDARY.md](A23_SPAWN_BOUNDARY.md) | 2026-10-22 | 7K | A23 Popen保存窗口与外层直接归属对照（2026-10-22） — 后续：[启动前预保留进程对象](A23_PRERETAINED_OWNER.md)完成572来源、两轮12安排和78测试。独立候选覆盖指定构造器/PID已登记窗口；原生创建至PID登记及创建者整进程退出仍未验证。以下保… |
| [A23_STARTUP_ARM_CANDIDATE.md](A23_STARTUP_ARM_CANDIDATE.md) | 2026-10-14 | 7K | A23 启动日志 ARM 隔离候选（2026-10-14） — 新完整ARM候选在实际Core/Capture/UVC初始化、__appInit和线程创建/启动调用处接入EP0INI1。 |
| [A23_STARTUP_FAILURES.md](A23_STARTUP_FAILURES.md) | 2026-10-14 | 8K | A23 初始化与启动失败审查（2026-10-14） — 本轮核对实际Core/Capture/grc:d、顶层USB初始化和线程启动代码，确认三个调用顺序边界： |
| [A23_STARTUP_JOURNAL.md](A23_STARTUP_JOURNAL.md) | 2026-10-14 | 8K | A23 独立启动阶段记录原型（2026-10-14） — 新增固定64条、只追加的**EP0INI1启动日志**，区分API调用、原始Result、void返回和fatal |
| [A23_STATUS_CAPTURE_REVISION.md](A23_STATUS_CAPTURE_REVISION.md) | 2026-10-22 | 7K | A23 STATUS计数语义修正与判断前留证（2026-10-22） — 最新实测结果（2026-10-22）：[同接口两轮成功及时间线](A23_LIVE75_FIRST_RESULT.md)已核对。一次采集完成113..128和129..144，两个新URB387/403共6144正确字… |
| [A23_STATUS_TRANSPORT.md](A23_STATUS_TRANSPORT.md) | 2026-10-21 | 7K | A23 状态管道显式失败候选（2026-10-21） — 后续：[局部终态发布中断对照](A23_TERMINAL_PUBLICATION.md)完成546来源、50安排和74测试。两次完整回放48个发布中断，4次在完整exit文件fsync后仍中断；局部退出码声明不等于实际… |
| [A23_STREAM_CRASH.md](A23_STREAM_CRASH.md) | 2026-10-28 | 3K | 3-URB stream crash（2026-10-27） — `ISO_PROBE_STREAM` 的 3 缓冲、每 16ms 提交一次实验： |
| [A23_SUPERVISOR_CANDIDATE.md](A23_SUPERVISOR_CANDIDATE.md) | 2026-10-20 | 5K | A23 独立 supervisor 收集候选（2026-10-20） — 后续：[supervisor管道、退出与清理边界](A23_SUPERVISOR_CLEANUP.md)补15种安排；60测试与498来源搬移通过，区分EOF/退出、组终止sent/not_found/error和ha… |
| [A23_SUPERVISOR_CLEANUP.md](A23_SUPERVISOR_CLEANUP.md) | 2026-10-20 | 6K | A23 supervisor 管道、退出与清理边界（2026-10-20） — 后续：[统一supervisor候选](A23_SUPERVISOR_UNIFIED.md)合并两阶段32种指定安排并补5种关闭错误；503来源、37场景与60测试通过，同一观察/限额/终止/准入，保留来源未认证负对照… |
| [A23_SUPERVISOR_JOB_LINK.md](A23_SUPERVISOR_JOB_LINK.md) | 2026-10-21 | 6K | A23 supervisor 与 job/receipt 的只读关联候选（2026-10-20） — 后续：[fixture自身job启动与结果绑定](A23_FIXTURE_JOB_BINDING.md)完成512来源、34安排和60测试；新Python fixture生成独立job/nonce与receipt，历史… |
| [A23_SUPERVISOR_UNIFIED.md](A23_SUPERVISOR_UNIFIED.md) | 2026-10-20 | 6K | A23 统一 supervisor 收集、清理与关闭候选（2026-10-20） — 后续：[job/receipt只读关联](A23_SUPERVISOR_JOB_LINK.md)完成507来源、57场景与56测试；识别entry与SDK receipt绑定差异，提供未应用静态接入计划，只声明跨模型对… |
| [A23_SUSTAINED_STREAM_LIMIT.md](A23_SUSTAINED_STREAM_LIMIT.md) | 2026-10-28 | 4K | A23 持续流上限（2026-10-28） — 640 池排除了“同 buffer 复用”这个解释：**每个 buffer 只映射一次，仍在约 5 个 URB 后崩**。 |
| [A23_TERMINAL_COMMIT.md](A23_TERMINAL_COMMIT.md) | 2026-10-21 | 7K | A23 局部终态目录同步与最终 commit 候选（2026-10-21） — 后续：[纯磁盘缓存只读恢复分类](A23_TERMINAL_RECOVERY.md)完成554来源、87安排和82测试；不接收事件/观察，完整commit仅关联字节，历史目录同步和wait保持unknown。原发布协议… |
| [A23_TERMINAL_DEADLINE.md](A23_TERMINAL_DEADLINE.md) | 2026-10-22 | 6K | A23 取样独立期限与子进程直接wait（2026-10-22） — 后续：[调用者中断与运行时句柄交接](A23_TERMINAL_OWNER.md)完成565来源、两轮74安排和82测试。新增显式owner候选，原deadline监督器与固定worker保持。以下保留原阶段。 |
| [A23_TERMINAL_INTAKE.md](A23_TERMINAL_INTAKE.md) | 2026-10-22 | 7K | A23 临时目录只读取样入口（2026-10-21） — 后续：[取样独立期限与子进程直接wait](A23_TERMINAL_DEADLINE.md)完成562来源、两轮67安排和82测试。原取样器保持；新监督器提供非阻塞管道与独立IO截止时间，未认证硬实时返回或调用者中断… |
| [A23_TERMINAL_OBSERVATION_WIRING.md](A23_TERMINAL_OBSERVATION_WIRING.md) | 2026-10-26 | 7K | 末轮观察的离线模型接线（2026-10-26） — 已将[服务窗口策略](A23_SERVICE_OBSERVATION_OFFLINE.md)接到独立末轮控制器，完成专属worker、返回门、复核、模型健康poll、采样和最终检查回调的顺序验证。独立Python消费者… |
| [A23_TERMINAL_OWNER.md](A23_TERMINAL_OWNER.md) | 2026-10-22 | 7K | A23 调用者中断与运行时句柄交接（2026-10-22） — 后续：[Popen保存窗口与外层直接归属对照](A23_SPAWN_BOUNDARY.md)发现保存前句柄缺失和保存后管道未登记两个负对照。原owner保持；新隔离子类仅修正已保留child的管道发现。以下保留原阶段的… |
| [A23_TERMINAL_PUBLICATION.md](A23_TERMINAL_PUBLICATION.md) | 2026-10-21 | 7K | A23 局部终态发布中断对照（2026-10-21） — 后续：[目录同步与最终commit候选](A23_TERMINAL_COMMIT.md)完成551来源、82安排及82测试。新协议记录先part/file fsync，再不可覆盖link和目录同步，最后发布commit… |
| [A23_TERMINAL_RECOVERY.md](A23_TERMINAL_RECOVERY.md) | 2026-10-21 | 6K | A23 纯磁盘缓存只读恢复分类（2026-10-21） — 后续：[临时目录只读取样入口](A23_TERMINAL_INTAKE.md)完成557来源、83安排和82测试。候选使用固定白名单、NOFOLLOW与两轮观察；仍不声称目录原子性，原纯分类器保持。以下保留原阶段。 |
| [A23_THREAD_PATHS.md](A23_THREAD_PATHS.md) | 2026-10-14 | 7K | 线程等待调用点与采集重试审查（2026-10-14） — 完整线程图里有两种等待：eventWait只等待1个Event；UvcDeviceProcessRequests的后续SETUP轮询同时等待VC、VS、ISO三个Event。新的只读审查按实际调用点接入句柄回放，保留所… |
| [A23_THREE_EPOCH_OFFLINE.md](A23_THREE_EPOCH_OFFLINE.md) | 2026-10-23 | 6K | 固定三轮主机离线核心（2026-10-23） — 后续接线已完成：[当前97件三轮候选](A23_LIVE97_THREE_READY.md)已编译封存，等待新单次授权和现场状态确认。下文保留此前离线核心阶段的历史语境。 |
| [A23_THREE_EPOCH_SCOPE.md](A23_THREE_EPOCH_SCOPE.md) | 2026-10-23 | 6K | 固定三轮串行实验的范围审查（2026-10-23） — 后续实现：[三轮离线核心](A23_THREE_EPOCH_OFFLINE.md)已完成SDK资源/driver及模型验证，完整真实入口尚未就绪。下文是该实现之前的范围设计。 |
| [A23_TWO_EPOCH_BASELINE69_WORKFLOW.md](A23_TWO_EPOCH_BASELINE69_WORKFLOW.md) | 2026-10-19 | 7K | 69份基线与32序号一次流程模型（2026-10-19） — 后续：[共享账本引擎与原生文件permit](A23_SHARED_SEQUENCE32_NATIVE_PERMIT.md)已完成临时命名空间/原生注入验证；生产fresh verifier与现场CLI未接通。以下保留… |
| [A23_TWO_EPOCH_RECEIVER.md](A23_TWO_EPOCH_RECEIVER.md) | 2026-10-18 | 7K | 有限两轮接收协调器与分轮归档（2026-10-18） — 后续：[独立两轮SDK资源层](A23_PAIRED_SDK_RESOURCES.md)已编译并以假operations接入本页离线协调器；真实SDK资源仍被本页入口拒绝，SDK执行驱动未接入。以下保留原验证结果。 |
| [A23_TWO_EPOCH_SDK_DRIVER.md](A23_TWO_EPOCH_SDK_DRIVER.md) | 2026-10-19 | 7K | 两轮SDK执行驱动与联合回执（2026-10-18） — 后续：[独立等待入口、文件构建绑定及最终检查点](A23_TWO_EPOCH_SDK_ENTRY.md)已完成离线验证；生产许可与现场执行模式未实现。以下保留驱动阶段结果。 |
| [A23_TWO_EPOCH_SDK_ENTRY.md](A23_TWO_EPOCH_SDK_ENTRY.md) | 2026-10-19 | 8K | 两轮SDK等待入口、构建绑定与最终检查点（2026-10-19） — 后续：[最新69基线与32序号一次流程模型](A23_TWO_EPOCH_BASELINE69_WORKFLOW.md)已完成只读采用和隔离文件验证；生产共享账本及permit尚未接入。以下保留入口阶段结果。 |
| [A23_V3_RUNTIME.md](A23_V3_RUNTIME.md) | 2026-10-15 | 8K | A23 V3线程运行路径、日志与身份核对（2026-10-15） — 本轮审查封存V3 `window-30s`最终ELF、生成源码及已安装SDK头文件。确认工作线程 |
| [A23_V3_STACK_PROFILES.md](A23_V3_STACK_PROFILES.md) | 2026-10-15 | 8K | A23 V3实际日志、文件名与等待路径栈剖面（2026-10-15） — 已对新接收器绑定的同一份V3 window-30s ELF重新核验实际日志入口及相关SDK指令。 |
| [A23_VERSIONED_CLOCK_CANDIDATE.md](A23_VERSIONED_CLOCK_CANDIDATE.md) | 2026-10-20 | 5K | A23 参与式版本时钟快照候选（2026-10-20） — 后续：[版本快照接入主机端隔离模型](A23_VERSIONED_DRIVER_MODEL.md)完成59场景与61测试；C候选未改，模型引入store owner与提交票据，生产集成仍false。以下保留独立C阶段。 |
| [A23_VERSIONED_DRIVER_MODEL.md](A23_VERSIONED_DRIVER_MODEL.md) | 2026-10-20 | 6K | A23 版本快照接入主机端隔离模型（2026-10-20） — 后续：[指定并发与缓存诊断关联](A23_COMMIT_CONCURRENCY_MODEL.md)在driver/桥/C原字节保持下完成72场景与61测试；加入13种worker安排和字节消费关联，不认证全部交错或真实… |
| [A23_WAIT_FIXED_PATH.md](A23_WAIT_FIXED_PATH.md) | 2026-10-14 | 6K | SDK句柄等待与定长关联路径候选（2026-10-14） — 在新的隔离候选中，用定长拼接生成原REL1路径，移除关联文件adapter对snprintf的依赖。保存函数自身栈由560降到480byte，最终ELF的保存直接调用图闭合，入口累计用户态SP上界768byte；原91… |
| [A23_WAITING_COLLECTION.md](A23_WAITING_COLLECTION.md) | 2026-10-15 | 6K | A23等待日志纳入EXE3收集主结果（2026-10-15） — 已完成新的独立收集封装，将等待交接、SDK日志/最终快照、EXE3及可选原始OWN2/DIA2 |
| [A23_WAITING_ENTRY.md](A23_WAITING_ENTRY.md) | 2026-10-15 | 7K | A23隔离等待入口与SDK启动分离（2026-10-15） — 后续实施见[等待接收器构建与启动门禁](A23_WAITING_RECEIVER.md)：新main及完整构建/ |
| [A23_WAITING_RECEIVER.md](A23_WAITING_RECEIVER.md) | 2026-10-15 | 6K | A23等待接收器构建与启动门禁（2026-10-15） — 后续实施见[等待日志纳入EXE3收集主结果](A23_WAITING_COLLECTION.md)：24组材料与94项 |
| [A23_WORKER_FAILURE_MODEL.md](A23_WORKER_FAILURE_MODEL.md) | 2026-10-20 | 5K | A23 独立 worker 失败与材料完整性模型（2026-10-20） — 后续：[完整隔离driver的worker故障与收集边界](A23_DRIVER_WORKER_FAILURE_MODEL.md)将15种安排接入Capture/BeginCommit/post-guard，87场景和… |
| [BURST_WINDOW_TEST.md](BURST_WINDOW_TEST.md) | 2026-10-09 | 5K | 同backend单次burst对照（2026-10-09） — `burst-window-1`已在20:34完成一次fresh HS burst，主机侧验收通过；20:43完整2630byte设备日志核验匹配，单次完整验收通过。 |
| [CARD_WORKFLOW.md](CARD_WORKFLOW.md) | 2026-10-27 | 6K | 读卡到安全推出的完整流程 — 当前操作范围按 [研究规则](RESEARCH_RULES.md) 和本次用户要求解释。 |
| [CLOCK_AUDIT.md](CLOCK_AUDIT.md) | 2026-10-11 | 6K | A23主机帧时间戳诊断 — 最新3350byte失败设备日志已核验：A23安装及唯一URB正常终结，raw16包精确，但主机 |
| [CONTEXT_AUDIT.md](CONTEXT_AUDIT.md) | 2026-10-09 | 5K | A21：ISO6 发布前硬件端点上下文 — A21已单次实机，context配置匹配但缺一槽，严格失败；完整设备日志已核验。 |
| [CURRENT.md](CURRENT.md) | 2026-10-28 | 10K | 当前状态（2026-10-27 19:20，Asia/Shanghai） — 视频可用；音频不可用。最近一次短包实机主机侧通过、设备侧保存失败；离线路径修正版已存在， |
| [DIRECTORY_LAYOUT.md](DIRECTORY_LAYOUT.md) | 2026-10-09 | 4K | 实验分支目录与本地产物 — `research/usb-ds-iso/README.md`是唯一研究入口。短期状态写入`docs/STATUS.md`；详细证据按实验 |
| [DOORBELL_AUDIT.md](DOORBELL_AUDIT.md) | 2026-10-09 | 4K | A20：ISO5 原门铃路径前后 MFI — A20已单次实机，raw连续正确但原生状态失败；完整设备日志已核验。 |
| [EVENT_AUDIT.md](EVENT_AUDIT.md) | 2026-10-09 | 7K | A18：有界 ISO3 事件 / MFI 诊断 — A18已单次实机，16包内容与原生状态正确但缺一槽，严格失败；完整设备日志已核验。 |
| [EXPERIMENT_GUIDE.md](EXPERIMENT_GUIDE.md) | 2026-10-09 | 14K | USB设备侧ISO实验指南 — 最新事实见[当前状态](STATUS.md)：A23串行测试首轮原生失败，完整3365byte设备日志已核验， |
| [FOLLOWUP_SIA.md](FOLLOWUP_SIA.md) | 2026-10-09 | 6K | A22：首包显式 FrameID，后续 TD 使用 SIA — A22已单次实机，raw连续正确但原生状态失败；完整4948byte设备日志已核验。 |
| [HOST_DRIVER_AUDIT.md](HOST_DRIVER_AUDIT.md) | 2026-10-12 | 9K | 当前 macOS USB 主机驱动离线审计（2026-10-12） — 已定位本机内核集合并追到兼容层错误转换。最重要的结果是：日志中的 `frStatus` 虽然来自 |
| [HOST_DRIVER_FLOW_AUDIT.md](HOST_DRIVER_FLOW_AUDIT.md) | 2026-10-12 | 9K | 主机请求结果、平台分派与新接口候选（2026-10-12） — 继续[主机驱动审计](HOST_DRIVER_AUDIT.md)，已确认普通完成路径中的方向判定，追到正常ISO |
| [HOST_MICROFRAME_AUDIT.md](HOST_MICROFRAME_AUDIT.md) | 2026-10-09 | 4K | A23：主机微帧观察（microframe-audit-1） — 本专题工具已在两次独立启动各完成一次严格成功采集，完整设备日志均已核验。 |
| [INDEPENDENT_SERIAL_REPEAT.md](INDEPENDENT_SERIAL_REPEAT.md) | 2026-10-11 | 5K | A23第二次独立启动串行复核 — 2026-10-11第一次完整串行验收已通过：16轮各16个192byte包、raw/native/public/URB/ISO7/ |
| [INTERVAL_EXPERIMENT.md](INTERVAL_EXPERIMENT.md) | 2026-10-09 | 9K | A23：HS 125 µs 服务间隔对照 — 本页保留A23服务间隔改动、构建验证及原接收器两次实机观察。 |
| [IOUSBHOST_BURST_COLLECTION_AUDIT.md](IOUSBHOST_BURST_COLLECTION_AUDIT.md) | 2026-10-13 | 5K | IOUSBHost 单次 burst 设备关系与 collection 离线审计（2026-10-13） — 后续已实现并编译[独立SDK能力适配](IOUSBHOST_BURST_SDK_ADAPTER.md)；下文为07:28模拟collection阶段及其冻结记录。 |
| [IOUSBHOST_BURST_ENTRY.md](IOUSBHOST_BURST_ENTRY.md) | 2026-10-13 | 5K | 单次 SDK burst 入口与零次数准备（2026-10-13） — 后续17:02已执行[首次实机诊断](IOUSBHOST_FIRST_BURST_TEST.md)：控制Timeout、ISO停止后 |
| [IOUSBHOST_BURST_EXECUTOR_AUDIT.md](IOUSBHOST_BURST_EXECUTOR_AUDIT.md) | 2026-10-13 | 4K | IOUSBHost 单次 burst 模拟执行器与日志绑定（2026-10-12） — 后续10-13已完成[模拟collection设备关系审计](IOUSBHOST_BURST_COLLECTION_AUDIT.md)， |
| [IOUSBHOST_BURST_SDK_ADAPTER.md](IOUSBHOST_BURST_SDK_ADAPTER.md) | 2026-10-13 | 6K | IOUSBHost 单次 burst SDK 适配与离线验证（2026-10-13） — 本文记录08:19的能力层阶段；后续协调器与独立主机格式已在[电脑复核](IOUSBHOST_BURST_SDK_COORDINATOR.md)完成，采集入口仍未开放。 |
| [IOUSBHOST_BURST_SDK_COLLECTION.md](IOUSBHOST_BURST_SDK_COLLECTION.md) | 2026-10-13 | 5K | 单次 burst SDK collection 与设备关系（2026-10-13） — 后续13:38阶段已完成[单次SDK入口与零次数准备](IOUSBHOST_BURST_ENTRY.md)，221项Python |
| [IOUSBHOST_BURST_SDK_COORDINATOR.md](IOUSBHOST_BURST_SDK_COORDINATOR.md) | 2026-10-13 | 6K | 单次 burst SDK 协调器与主机观察格式（2026-10-13） — 后续13:11阶段已完成[独立SDK collection与设备关系](IOUSBHOST_BURST_SDK_COLLECTION.md)， |
| [IOUSBHOST_CONTROL_TRACE_REVIEW.md](IOUSBHOST_CONTROL_TRACE_REVIEW.md) | 2026-10-12 | 2K | A23 控制广播日志离线重审（2026-10-12） — 已修正no-TD审计对EP0方括号字段的解释：实机字段是interface_index，Mock字段是请求序号。 |
| [IOUSBHOST_EVIDENCE_PIPELINE.md](IOUSBHOST_EVIDENCE_PIPELINE.md) | 2026-10-12 | 6K | IOUSBHost离线描述符与证据链（2026-10-12） — 接续[接口与所有权审计](IOUSBHOST_TRANSACTION_AUDIT.md)，已完成描述符预检、模拟证据写盘、 |
| [IOUSBHOST_FIRST_BURST_CARD_REVIEW.md](IOUSBHOST_FIRST_BURST_CARD_REVIEW.md) | 2026-10-13 | 2K | 首次 SDK burst 读卡复核（2026-10-13 17:43，Asia/Shanghai） — 完整设备日志已只读回收，6041 bytes，SHA256 `81337a5f62f4357f2045a48a1e0640953cb9bbf940c6c036882b968645a1e7de`。 |
| [IOUSBHOST_FIRST_BURST_TEST.md](IOUSBHOST_FIRST_BURST_TEST.md) | 2026-10-13 | 4K | 第一次 SDK 单 burst 实机诊断（2026-10-13 17:02，Asia/Shanghai） — 后续：17:43已完成只读回收及安全推出，见[读卡复核](IOUSBHOST_FIRST_BURST_CARD_REVIEW.md)。下文为测试时记录。 |
| [IOUSBHOST_FIRST_EMPTY_CARD_REVIEW.md](IOUSBHOST_FIRST_EMPTY_CARD_REVIEW.md) | 2026-10-12 | 3K | 第一次 IOUSBHost 空窗口读卡核验（2026-10-12 19:54） — 后续：控制广播审计已修正，同一原始证据重审完整性通过；原拒绝记录保留，政策仍未接受。见[重审说明](IOUSBHOST_CONTROL_TRACE_REVIEW.md)。 |
| [IOUSBHOST_FIRST_EMPTY_WINDOW.md](IOUSBHOST_FIRST_EMPTY_WINDOW.md) | 2026-10-12 | 3K | 新接口第一次实际空窗口（2026-10-12 19:41，Asia/Shanghai） — 后续：控制广播审计已修正，同一原始证据重审完整性通过；原拒绝记录保留，政策仍未接受。见[重审说明](IOUSBHOST_CONTROL_TRACE_REVIEW.md)。 |
| [IOUSBHOST_HARDWARE_ENTRY.md](IOUSBHOST_HARDWARE_ENTRY.md) | 2026-10-12 | 7K | 新接口的一次无 TD 实机入口（2026-10-12） — 19:41 已在正确执行环境完成第一次实际空窗口：1次提交/1次callback、overall0，960槽 |
| [IOUSBHOST_NATIVE_SEMANTICS.md](IOUSBHOST_NATIVE_SEMANTICS.md) | 2026-10-12 | 5K | IOUSBHost 原生空槽与时间戳语义核验（2026-10-12） — 已离线核对本机SDK、此前冻结反汇编和本次原始960条记录。没有实机请求、SD访问或新增凭据。 |
| [IOUSBHOST_NO_TD_PLAN.md](IOUSBHOST_NO_TD_PLAN.md) | 2026-10-12 | 9K | 新transaction接口的空窗口观察方案（2026-10-12） — 继续[SDK与原始STATUS绑定](IOUSBHOST_SDK_BINDING_AUDIT.md)，把新backend空窗口的预检、 |
| [IOUSBHOST_OPEN_DIAGNOSTIC.md](IOUSBHOST_OPEN_DIAGNOSTIC.md) | 2026-10-12 | 4K | SDK 打开失败的定位（2026-10-12） — 本次打开失败的原因已确认：Codex 命令执行沙箱拒绝 IOServiceOpen 创建 USB user client。 |
| [IOUSBHOST_RUNTIME_READINESS.md](IOUSBHOST_RUNTIME_READINESS.md) | 2026-10-12 | 6K | 新接口的运行条件准备（2026-10-12） — 本页记录当时的纯模拟准备。后续 Mac 接收器和独立一次凭据已经完成本地准备，尚未执行， |
| [IOUSBHOST_SDK_BINDING_AUDIT.md](IOUSBHOST_SDK_BINDING_AUDIT.md) | 2026-10-12 | 8K | IOUSBHost SDK适配与原始STATUS绑定（2026-10-12） — 继续[会话审计](IOUSBHOST_SESSION_AUDIT.md)，完成SDK适配实现的编译与模拟故障注入、原始STATUS |
| [IOUSBHOST_SESSION_AUDIT.md](IOUSBHOST_SESSION_AUDIT.md) | 2026-10-12 | 9K | IOUSBHost离线会话、断开与设备关联（2026-10-12） — 继续[离线证据链](IOUSBHOST_EVIDENCE_PIPELINE.md)，完成可注入的单请求会话组件、持久化事件日志、 |
| [IOUSBHOST_SINGLE_BURST_DRAFT.md](IOUSBHOST_SINGLE_BURST_DRAFT.md) | 2026-10-12 | 6K | IOUSBHost 单次 burst 离线诊断草案（2026-10-12） — 已定义独立候选计划、字节验收和失败停止模型。它只有离线plan/candidate命令，没有registry打开、 |
| [IOUSBHOST_TRANSACTION_AUDIT.md](IOUSBHOST_TRANSACTION_AUDIT.md) | 2026-10-12 | 10K | IOUSBHost transaction调用链与离线所有权原型（2026-10-12） — 继续[请求与平台分派审计](HOST_DRIVER_FLOW_AUDIT.md)，已核对本机用户态framework提交、完成、 |
| [MATCHED_SERIAL_VALIDATION.md](MATCHED_SERIAL_VALIDATION.md) | 2026-10-11 | 9K | A23同backend最多16次串行验收 — 20:34的单次burst已通过主机验收；20:43读卡取得完整2630byte日志，确认A23运行安装及 |
| [NATIVE_ERROR_ANALYSIS.md](NATIVE_ERROR_ANALYSIS.md) | 2026-10-11 | 11K | A23原生错误分析（2026-10-09） — 五次独立启动记录中，三次单次严格通过、两次失败。新的共同特征是：两次失败的接收窗口 |
| [NATIVE_SERIAL_VALIDATION.md](NATIVE_SERIAL_VALIDATION.md) | 2026-10-09 | 4K | A23：逐次原生状态核验与最多16次串行验收 — 2026-10-09实机最多16次测试在第1次原生错误后停止；完整设备日志已核验。 |
| [NO_TD_WINDOW_TEST.md](NO_TD_WINDOW_TEST.md) | 2026-10-09 | 8K | 无TD窗口诊断（2026-10-09） — 最新18:50一次fresh HS无TD窗口的主机基线通过：960槽全部Underrun、overall0， |
| [OFFLINE_AUDIT.md](OFFLINE_AUDIT.md) | 2026-10-12 | 9K | A23离线研究：代码差异、完成路径与证据缺口 — 2026-10-12，Asia/Shanghai。本轮不访问USB或SD，不准备新的实机入口，不修改部署包、历史run、collection或采集状态。 |
| [PROGRESS_HANDOFF.md](PROGRESS_HANDOFF.md) | 2026-10-27 | 250K | 进度交接（2026-10-27，Asia/Shanghai） — 已完成[首次短包实测与回归修正](A23_SHORT24_FIRST_LIVE.md)。配套NSP/IPS部署核验后， |
| [PUBLICATION_AUDIT.md](PUBLICATION_AUDIT.md) | 2026-10-09 | 7K | A19：ISO4 发布阶段 MFI 锚点 — A19已单次实机，原生状态正确但缺一槽，严格失败；完整设备日志已核验。 |
| [REPRODUCIBILITY.md](REPRODUCIBILITY.md) | 2026-10-09 | 2K | A23：重启后的独立复现验证 — 本页记录原A23接收器的独立复现阶段；该阶段已在第二次启动失败后停止。 |
| [RESEARCH_DIRECTION.md](RESEARCH_DIRECTION.md) | 2026-10-27 | 207K | 项目现状、结论与研究路径（2026-10-22，Asia/Shanghai） — 目标保持为免客户端的标准UVC视频与UAC/PCM音频，同时保留低延迟和视频共存。 |
| [RESEARCH_RULES.md](RESEARCH_RULES.md) | 2026-10-27 | 6K | 当前研究规则（2026-10-27，Asia/Shanghai） — 本规则落实用户本次要求：先不用虚拟机，简化过度严格的研究约束。 |
| [RESULTS.md](RESULTS.md) | 2026-10-12 | 156K | 实验历史结果（2026-10-01至2026-10-09） — 本页保留各阶段当时的原始观察、计划和后续核验；“当前”“待读卡”“下一步”仅指该条记录时点。 |
| [SERIAL_CLOCK_AUDIT.md](SERIAL_CLOCK_AUDIT.md) | 2026-10-12 | 9K | A23有界串行Mach时间戳诊断 — 此前防休眠串行失败中，raw16包及设备URB正常终结，但native/public报错，开头293个NotSent空槽。 |
| [STATUS.md](STATUS.md) | 2026-10-27 | 255K | 当前状态（2026-10-27，Asia/Shanghai） — 已完成[首次短包实测与回归修正](A23_SHORT24_FIRST_LIVE.md)。配套NSP/IPS部署核验后， |
| [TEST_PLAN.md](TEST_PLAN.md) | 2026-10-27 | 212K | 后续测试条件（2026-10-22） — 当前计划约束已于 2026-10-27 更新，见 [研究规则](RESEARCH_RULES.md)。先不用虚拟机， |
| [UAC_PCM_PRODUCER.md](UAC_PCM_PRODUCER.md) | 2026-10-28 | 6K | UAC PCM producer 设计（2026-10-27） — `usb:ds` 的 alt0-only endpoint filter 已用 runtime NOP patch 去掉；alt1 端点可以安装。 |
| [UAC_STANDARD_LAYER.md](UAC_STANDARD_LAYER.md) | 2026-10-27 | 4K | UAC1 标准层（离线 P0） — 日期：2026-10-27。范围：只做电脑上的离线实现与测试；**没有启用 UAC、没有调用 |
