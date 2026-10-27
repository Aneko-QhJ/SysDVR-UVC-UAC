# A23 实际 handler 隔离候选（2026-10-13）

后续[隔离落盘与停止窗口](A23_EP0_CANDIDATE_SINK.md)已完成电脑检查；本页保留该阶段无sink/触发的历史状态。

本轮把 trace 与所有权账本接入实际 A23 handler 的隔离副本，并完整链接包含原有 sysmodule
全部源码的 libnx ELF。48 个原生源码回放通过 ASan/UBSan，USB 返回结果及调用计数与同服务
模型下的未插桩源码一致；266 项相关 Python 回归无跳过。

生产 source、原协议/timeout、部署和三份凭据保持不变，USB/SD 访问为 0，remaining=0。
两个 ARM ELF 均未执行，没有 NSO/NSP 或安装入口，根因未确认。

## 接入位置与源码对照

[build_a23_trace_candidate.py](../tools/build_a23_trace_candidate.py) 从冻结 A23 校验的原始
uvc_device.c 提取实际控制/分发及 _pollIsoProbe 函数，按唯一源码 anchor 插入旁观 hooks。
生成完整源码树时使用同样的变换，原文件不修改：

- 每个 CtrlIn/CtrlOut 及 ISO post 返回后，保存通道、Result、成功时的有效 ID；失败时不读
  未定义 ID，账本保守标未知，不改变原 Result、ACK/stall 或调用次数。
- 原有 GetCtrlIn/GetCtrlOut/ISO GetReportData 返回后、parse 之前，旁观成功 batch 的原始
  ID/status。失败输出不读；count>8、重复 ID 永久拒绝导出，原 handler 继续原有行为。
- ProcessRequests 外加 enter/leave，函数内部所有早退仍回到 wrapper，processing 不会漏清。
  进入时若已有 PENDING/RETAINED ISO，却没有对应已观察的 active ID，永久拒绝导出。
- 原同步 LOG、事件清除、1s EP0 wait、20ms follow-up wait、CANCEL 及原协议保持原样。
  hooks 没有新增 USB 请求或报告查询；额外 tick/内存操作的实际成本未测量。

账本用于观察与导出门槛，没有改变原 handler 对共享 control buffer 的复用规则，不能据此
宣称整个传输路径已经具备 DMA 安全性。未知控制传输与后续 buffer 复用仍需独立审查。

新增 [ep0_candidate.c](../device/ep0_candidate.c) 和 [API](../device/ep0_candidate.h) 负责
静态 storage、请求编号、旁观、停止和交接。[owner 策略](A23_EP0_TRACE_OWNER.md) 的 16 槽、
ID 不重用和匹配终结条件保持有效；槽满/未知/损坏不影响原 USB 行为，只拒绝导出。

原轻量 fixture 没有真实 report 字段且使用恒定控制 ID，无法验证实际接入。本轮只在生成的
native 副本中替换为真实 8-entry/count ABI、独立控制 ID 及注入报告；原 fixture 保持原样。
前 25 场景仍使用原有分发/共享 SETUP/完整会话断言，但这次重新编译未插桩源作对照；
不把新服务模型说成与旧冻结模型完全相同。另有 23 个实际 handler 故障/终结场景。

## 停止与线程交接

隔离 main 副本在唯一视频 owner 服务请求前初始化，使用实际 svcGetThreadId API 取 writer，
并生成 process/session nonce。wire 的 boot_id 字段在此只是进程 nonce，不是已认证的系统
启动身份。native 使用注入 writer=11/exporter=22 和 UUID；没有运行真实线程。

Ep0CandidateRequestStop 是原子本地 API；没有新增 USB 命令、timer 或实机用户触发入口。
owner 在 WaitReady 返回或 ProcessRequests 整体返回后检查停止，结束时以 STOPPED 冻结。
processing 中请求停止只设置 flag，不能冻结/导出，也不会截断控制 helper。持续 SETUP
可能延长原 ProcessRequests，当前没有已经验证的停止时限。

候选的共享 g_running 改为 atomic_bool，避免新视频线程停止写入与 main/audio 读取之间引入
普通 volatile 数据竞争；生产原文件保持原样。main 保留视频、音频 threadWaitForExit 的
Result，核验 exporter ID，再 handoff。若 join 失败、存在 fault 或未终结 URB，在正常退出
路径中保留 static buffers/USB/Core，并 sleep，先不 threadClose/UvcDeviceExit；不 cancel、
重试或清空账本来凑导出。仅受控正常路径按此处理，异常终止/实际 HOS 排空仍未验证。

线程退出后不能再查询迟到报告。可解除超时占用的迟到报告必须在停止前，从原本就会发生的
GetReportData 返回中被观察到。未返回终结报告时继续保留未知；当前 API 不自动恢复或释放。

## 关键回放结果

| 模型场景 | 账本结果 | 候选内存导出 |
| --- | --- | --- |
| 完整正常 STATUS→BURST→STATUS，未注入 ISO 终结 | 6 个 ID，ISO 仍占用 1 个 | 拒绝 |
| 共享 SETUP 被后续 STATUS 覆盖，无 ISO post | 4 个控制 ID 已终结 | 可导出 STOPPED trace |
| 原始 ISO/控制 status 4 或 5 | 匹配 ID 终结，传输可失败 | 可导出，不宣称传输成功 |
| 控制 wait 超时，之后无该 ID 报告 | 控制 ID 仍占用 | 拒绝 |
| 同样超时，后续原有 IN report 含旧 ACK 与当前 STATUS 的不同终结 ID | 两个控制 ID 都解除 | 可导出，无新增查询 |
| wrong ID/channel、1/2/未知状态、GetReportData 失败 | 保留占用 | 拒绝 |
| 失败 post、坏 batch、身份槽超过 16 | 永久 fault | 拒绝，即使 STATUS 显示终结 |
| helper wait 内请求 stop / 模拟 join 失败 | 不在 helper 内冻结 / 不交接 | 拒绝 |
| trace 溢出，但独立账本已排空 | 丢失计数保留，记录不完整 | 可保存，不宣称完整窗口 |

原始 status 3/4/5 作为终结的语义沿用冻结 A23 静态假设；到达时刻、队列 batch、join 和
线程身份在 native 中均为注入。这不是实机已经验证的所有权证明，也没有确认共享 SETUP
覆盖就是本次 SDK 失败原因。

## 导出封装与构建关联

[ep0_candidate_capture.h](../device/ep0_candidate_capture.h) 只在 owner gate 成功后写调用方
内存，最大 6640 bytes；短 buffer/拒绝条件不触碰输出。外层 EP0OWN1 固定 simulation，
携带 writer/exporter、构建输入摘要、不可变账本与内层 EP0TRC1，三组 CRC 分别覆盖 header、
账本和内层 trace。16-byte 账本 entry 保存 channel、ID、terminal status；没有把 report
到达历史写成完整 journal。

构建输入摘要来自 source/生成器/fixture/固定 defines、验证后 runtime payload、libnx.a/
usbds.h/switch.specs 和编译器版本；写入候选生成 header，native 使用同一摘要。recipe.json
及 audit.json 把该摘要与本次实际 ELF SHA256 关联。摘要不是 ELF 自身哈希；不同输出路径
可改变调试信息及 ELF hash，因此保存每次实际文件的 hash，不声称重构二进制一致。

[独立分析器](../tools/analyze_ep0_candidate_capture.py) 拒绝截断、附加 bytes、CRC 损坏、
重标记、recipe 不符、未终结/重复账本 ID，以及成功 post 与账本不一致。trace 无损时两边
post 集合须相同，有损时只允许已观察 post 属于账本。CRC 与摘要只关联数据，不认证真实
线程/join、runtime DMA 或硬件来源，所有 authentication/hardware/root-cause 字段保持 false。

候选只提供内存 bytes，仍没有 SD/file sink。native 为了研究拒绝原因，额外通过核心序列化
冻结 trace 并写 `.bin`/`.owner.json`；明确标 native_debug_inspection=true。这条调试旁路
不出现在 ARM 候选。只有 gate 成功的模型另写 `.capture.bin`，不能把旁路文件当作放行。

## 完整 ELF、证据和下一步

基线为原有 5 个 C 文件；候选为隔离原源码加 runtime，共 6 个对象。真实 libnx/startup/
switch.specs 完整链接，并核验实际 caller/IPC/hook 符号。部分静态 helper 会被 O3 inline，
不以缺少局部符号判定丢代码。runtime payload 从原始 HOS NSO 与冻结 IPS/manifest 只读生成，
22 项 before bytes 均核对；没有调用原来会写 private header 或打包的工具。

更正旧文档的计数：manifest/IPS 实际为 22 项，日志 record=21 是最后一项的零基索引。
此前“21 项修改”的当前说明已更正，历史封存材料保持原样。

最新 [terminal review](../private/analysis/A23-EP0-handler-candidate-review-20261013-terminal/audit.json)
保存 48 场景、完整候选/基线树、native binaries、ARM objects/ELF/map、recipe、独立解码及
SHA256SUMS。无 suffix 与 final 的早期 47 场景版本均保留，当前交付以 terminal 为准。
[validation](../private/analysis/A23-EP0-handler-candidate-validation-20261013/validation.json)
另存源码快照、266 项回归、凭据/历史 manifest 核对；初次 47 场景回归日志也保留。
未宣称全库 discovery 通过。

下一步电脑实现隔离的文件 sink、失败/短写/读回/commit 验证，并定义能审查的停止触发及
记录窗口。正式生成可部署包前仍需解决 simulation 标记/来源与实际启动身份、真实 ID 是否
重用、终结语义和插桩/SD 成本；当前没有可用测试次数，不部署或访问硬件来补这些缺口。
