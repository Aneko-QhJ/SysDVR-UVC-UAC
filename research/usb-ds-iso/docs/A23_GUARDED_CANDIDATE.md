# A23 buffer 复用门槛与统一退出候选（2026-10-14）

隔离候选已经在 **memcpy/post 之前拒绝未知占用的 buffer 复用**，并将正常退出与
__appExit 的清理交给一次性原子授权。19 个实际控制处理函数场景、10 个退出场景、
9 个策略边界和 5 个实际 adapter 场景通过 ASan/UBSan；296 项相关 Python 回归无跳过。
默认窗口关闭与30秒样例各链接8对象完整libnx ELF，仅编译/链接，未执行或打包。

这是独立生成的研究候选，生产源码、原候选runtime和旧封存材料保持原样。
三份票据哈希不变，burst仍failed_no_retry/remaining0，USB/SD0，根因未确认。
本阶段完成上一轮[buffer/退出审查](A23_CONTROL_BUFFER_CLEANUP.md)提出的门槛实现。

## buffer 门槛

[构建工具](../tools/build_a23_guard_candidate.py)只在新输出树中改写封存
[sink候选](A23_EP0_CANDIDATE_SINK.md)。源码锚点必须唯一，旧runtime输入必须逐字节
匹配封存；recipe绑定输入、原sink manifest、编译器和libnx.a，两个窗口配置分别绑定摘要。
ARM树同时保留原trace/账本及实际UvcDeviceProcessRequests wrapper。

[范围策略](../device/ep0_buffer_guard.h)与[adapter](../device/ep0_candidate_guard.c)
在原账本的16个永久身份槽上补充地址和长度，匹配(channel,id)，ID0有效。
只有原有raw report观察到匹配终结3/4/5，才能解除相应范围；不会新增GetReportData、
清账本、cancel或close。CPU owner必须在ProcessRequests内部，已停止/已join、fault、
非法地址/溢出、范围超过4096、未知映射或身份不符一律拒绝。

- _ctrlWrite在实际memcpy之前、_ctrlRead在首次OUT之前检查完整请求，预留数据及status两个身份槽。
- _ctrlInXfer/_ctrlOutXfer在event clear/post之前再次检查；成功post后立即绑定实际指针、长度和返回ID。
- _ctrlAck在开始记录ACK helper之前检查零长地址身份；零长度不覆盖DMA数据字节，但保留同地址请求身份。
- ISO trigger在status/payload改写之前检查ISO buffer并预留ISO+ACK两个槽；实际ISO post也绑定地址。
- post失败或绑定不可信时设置永久fault并原子请求stop。既有未知范围或fault导致后续请求在copy/post前停止。
  拒绝计数/原因只保留在候选内存和native审查JSON，**没有增加wire字段或拒绝时的SD导出通道**。

VS1/ISO2仍共用控制buffer，VC0独立。范围检查采用半开区间，含部分重叠及零长地址点；
相邻非零范围可不重叠。整个请求预留用于避免先copy/data post、随后才发现status槽不足。
身份槽不会因终结循环利用，容量保守保留，不能把30秒停止窗口当作无限请求预算。

| 回放条件 | 旧候选 | 新隔离候选 |
| --- | --- | --- |
| 非零IN/OUT timeout、report错误、错ID、非终结状态；后续共享buffer请求 | copy未知范围并再post | 原copy重叠0、同地址repost0，fault/stop，拒绝导出 |
| BURST零长ACK或STATUS零长OUT timeout | 后续同地址repost两次 | 保留零长身份并拒绝复用；不宣称payload损坏 |
| VS访问ISO已占用的共享buffer | 覆盖1byte并repost | copy/post前拒绝 |
| 独立VC buffer请求 | 不重叠，旧ISO身份仍pending | 原服务观察不变，无新拒绝；最终仍不能导出 |
| 原有report已观察终结3/4/5 | 后续复用放行 | 原服务观察不变，后续放行 |
| late-report-after-copy | copy168bytes之后报告到达，最终pending0/export放行 | 新请求在copy前拒绝，没有新report查询；旧ID保留pending1 |

19个场景沿用原模型，其中17个经过实际dispatcher、2个直接调用实际非零OUT helper。
新的5个adapter场景单独核验失败post、ID0、缺少映射、通道不符和非法范围：均永久拒绝
后续复用及导出。9个策略场景覆盖地址溢出、相邻/部分重叠、零长点、容量、owner及原子阶段。
正常完成/终结4或5/独立VC的原有服务计数与旧候选逐字段一致；**拒绝分支有意改变USB调用**，
不能沿用上一阶段“所有行为相同”的结论。

门槛拒绝后请求stop并不证明已经停止线程、服务不再借用内存或所有URB终结。
当前没有通过新查询收集迟到report的恢复机制，旧请求可能永远pending；正常Finish也会因
永久fault拒绝保存，资源保留。不能为了得到capture而解除fault或重标已有封存样本。

## 统一清理授权

[原子阶段](../device/ep0_cleanup_gate.h)为INITIAL→JOINING→AUTHORIZED→CLAIMED→DONE。
主线程在两次threadWaitForExit之前进入JOINING；只有两次Result成功、Finish放行、文件save
成功、两个threadClose之后才发布AUTHORIZED。原main的UvcDeviceExit延后至__appExit，
后者先请求stop，再读取原子授权；不会在可能仍运行的owner上检查可变账本。

- INITIAL/JOINING：回调保持资源并sleep。包括未启动、线程仍运行、即使已排空但没有授权。
- 任一join失败、pending/Finish拒绝或save失败：正常路径保留，不授权，不threadClose/USB/Core/sm清理。
- AUTHORIZED：回调原子claim一次，执行原UvcDeviceExit/CoreExit/smExit，再发布DONE。
- CLAIMED：重入保持；DONE：后续回调直接返回。正常模型主动调用两次回调，清理仍只有一次。

10项实际退出片段回放覆盖上述状态。正常成功结果为join2、threadClose2、接口close3、
usbDsExit/CoreExit/smExit各1、save1；所有失败/未授权结果都无资源close。
未启动回调没有强行沿用正常授权，初始化中途失败也可能一直保留；没有实现阶段化早期回滚。
这些是native中注入线程/服务结果并直接调用callback的模型，实际异常回调可达性、libnx
执行上下文及清理Result语义没有实机验证。原子授权仅传递已检查的条件，不认证它们。

## 验证与封存

[11项Python检查](../tests/test_a23_guard_candidate.py)核验复用拦截、正常分支对照、零长
身份、迟到report、失败post映射、退出授权/重复调用、两配置链接与生产/票据不变。
[策略fixture](../tests/ep0_guard_policy_test.c)与生成的buffer/adapter/exit源码只在电脑运行。

```sh
python3 research/usb-ds-iso/tools/build_a23_guard_candidate.py --output /private/tmp/A23-guard-review-new
```

输出目录必须不存在；该命令只运行native fixtures并编译/链接ARM ELF。

- `private/analysis/A23-guarded-candidate-review-20261014`：生成native源码/二进制、43场景结果，
  两套完整候选源码/8对象/ELF/map、各配置recipe、audit与SHA256SUMS。
- `private/analysis/A23-guarded-candidate-validation-20261014`：296项相关回归、输入及生产源码
  快照、旧封存材料/三份票据/本地文档链接复核，独立validation与SHA256SUMS。

## 下一步与证据缺口

下一步电脑审查完整STATUS→BURST→STATUS及停止交接的候选覆盖与16槽/trace预算，补齐
拒绝后可保留诊断的离线路径和初始化失败阶段，不靠放行未排空资源取得文件。先评估
拒绝与真实main调度的衔接、有限请求预算及早期退出策略，再讨论新的诊断候选。

当前没有NSO/NSP、新部署、USB命令或可用实机次数。DMA借用及终结3/4/5仍是显式模型假设，
CPU调用顺序来自实际源码。拒绝的内存诊断尚无安全导出通道，停止延迟、运行成本、ID重用、
真实join、SD commit持久性、异常退出和来源认证未验证；初次SDK burst seq0根因仍未知。

后续[完整会话预算与拒绝诊断](A23_GUARD_SESSION_DIAGNOSTICS.md)核对了trace先写满和ISO先提交/ACK后拒绝的边界；独立诊断只在电脑输出，封存候选未改。
