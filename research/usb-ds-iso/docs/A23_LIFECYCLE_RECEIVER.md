# A23 生命周期候选接收器与回收判读（2026-10-16）

已为[生命周期设备候选](A23_LIFECYCLE_DEVICE_CANDIDATE.md)建立独立接收器、六项材料绑定及原件收集工具，完成 31 个回收场景与 12 个等待流程模型。新增 19 项测试；连同既有测试共 259 项相关回归通过，失败、错误、跳过均为 0。本轮没有重新生成设备 ELF，没有打包 NSP、部署、签发或实机运行。

## 新接收器及身份

新接收器使用第 4 代 build / record / description / consumed receipt，与旧 quiet 第 3 代分开。运行身份继续使用设备候选的 recipe，而不是旧 quiet recipe 或主机源码摘要。绑定固定六项文件：ELF、设备 recipe、symbols、嵌入 recipe 头、sysmodule.json、main.npdm；同步核对 ELF 中的两个 recipe 对象、NPDM 的 main 栈请求 8192、优先级 44、CPU 3 及配置字段。8192 仍只是请求值，不认证实际内核预算。

接收器、原生交接、进程及 SDK claim 都携带运行 recipe、设备 ELF、NPDM、配置、main 栈请求及完整绑定摘要。文件检查模式只核对电脑上的材料。临时副本测试确认 live 源码/设备材料变化、重新封存后生成源码或设备文件变化、旧回执、重复 JSON 字段、错误 recipe/NPDM 都被拒绝。进程 claim 为排他写；SDK 交接前重新检查回执及材料，不能凭较早的检查结果通过。

源码闭包从旧 195 项增加 7 项，共 202 项，旧来源未改。新增内容为独立 guard、材料绑定、构建、收集、审查工具及两份测试来源。生成树有 4 项主机源码/常量，14 个单元分别完成正式接收器及带 address/undefined sanitizer 的模型程序链接。原生源码数量检查在这一代提高到 224，构建包仍限制 256 个文件；实际封存构建为 219 项。

| 材料 | SHA256 |
| --- | --- |
| 设备 runtime recipe，保持 | `39b10989773f3d216138de2ea3c8027ae1f42c6dbafbd84f454fb4cc9acfc549` |
| 设备 ELF，保持 | `737ad5c1df026d7ea94ac898de0ff69ed4fef8c369f400d1dce72b377d58eb38` |
| 新接收器 | `f4a23c2391279b872ceb84c89293ce43d8614dff2bd66c24a453e4dfac51aac6` |
| 新主机设备绑定 | `e73fa51d55efbbb15ccc83c4f20352a5d4cec5d12d424b7ec490f93e46e8d3ac` |
| 接收器构建 SHA256SUMS，219 项 | `cfd6c60358517265861e5bf71d971a751aa8468c9e90645c210dbea18d639e49` |
| 审查包 SHA256SUMS，1540 项 | `eec791e3348deb14af59ecd1625ceeafcdb4fc9beabf1cf8fda05971aca9018d` |

材料位于 `private/analysis/A23-lifecycle-receiver-review-20261016`，其中 `offline-record.json` 为 `offline_build_ready / remaining=0 / acquisition_enabled=false`。模型中的 consumed 记录仅为显式注入的静态输入，没有调用签发器或接收器采集入口。新的 Python 现场签发/执行流程尚未建立；不能把该离线记录直接用于旧 quiet 执行入口。

## 回收与判断

`tools/collect_a23_lifecycle_execution.py` 的 freeze 接收既有主机目录、记录、run 及零至 16 个生命周期文件，EXE3 和外部主结果均可省略。工具保留原始文件名与原始字节，冻结六材料、接收器、构建 manifest、回执及现有 claim，随后仅分析新副本；不会把缺失 EXE3 替换成模型或空文件。analyze 对封存副本重新计算结论，无须读取记录中的原始设备路径或当前源码；收集目录可移动。

生命周期解析沿用 LCP1 合法前缀规则。头有效时可保留损坏槽之前的记录，报告 CRC、部分记录、零尾、空洞等情况；不能修补或跳过坏槽。文件名须匹配头中的 main nonce。存在多个文件时报告选择不唯一，保留全部文件，不自动选一个“最像”的 run。

与有效 EXE3 的内容关联要求：生命周期 recipe 正确、文件名匹配 nonce、存在双方成功 join 后的 context，context 的 boot/session 与 EXE3 相同，writer 等于 EXE3 exporter、频率相同、头起点不晚于 EXE3 窗口起点、context 不早于 EXE3 stop。关联仍是所供字节的自洽，不认证物理同 run。坏尾之前的 context 可以匹配，但不能因此把部分文件判为完整文件。

| 场景 | 材料绑定 | 原 EXE3 证据链 | LCP1 内容关联 | 新增完整条件 |
| --- | --- | --- | --- | --- |
| 匹配的模型输入 | 通过 | 通过 | 通过 | 满足 |
| 缺 EXE3 | 可通过 | 不完整 | 无 EXE3 可比较 | 不满足 |
| 缺主结果或主结果 commit 失败 | 可通过 | 不完整 | 可匹配 | 不满足 |
| 无 LCP1、缺 context 或头损坏 | 可通过 | 可通过 | 不满足 | 不满足 |
| context 后坏槽、部分文件或短零尾 | 可通过 | 可通过 | 可匹配合法前缀 | 不满足 |
| nonce/recipe/context/writer/频率不匹配 | 可通过 | 可通过 | 不满足 | 不满足 |
| 多个 LCP1 文件 | 可通过 | 可通过 | 不自动选择 | 不满足 |
| 旧回执或进程/SDK claim 不匹配 | 不通过 | 原始内容仍独立分析 | 可匹配 | 不满足 |

结果明确分开 `binding.supplied_binding_consistent`、`bound_execution_chain_complete`、`lifecycle.supplied_context_associated` 与 `supplied_chain_complete`。最后一项只表示所供软件材料同时满足旧 EXE3 链和单一、全长 3968 字节、具有可关联 context 及干净尾部的 LCP1 条件；不要求最后阶段必为 main_return，也不证明设备退出、载荷成功或记录自身提交。

31 个场景覆盖 EXE3 存在/缺失/部分、外部主结果缺失/不匹配、保存回执失败、缺 LCP1/context、坏头/坏尾、短文件、旧 recipe、不同 nonce、不同 writer/频率/context、多文件以及回执/claim 错配。独立 EXE3 结论不会被 LCP1 的缺失或损坏覆盖。所有物理同 run、设备 join、清理授权、记录自身 commit、最后实际执行点、硬件验收及根因标记保持 false。

## 验证及后续边界

验证包位于 `private/analysis/A23-lifecycle-receiver-validation-20261016`。44 份旧封存、7840 个条目重核通过；七生产文件、旧三票据、三离线记录及当前已消费现场记录保持。新审查包及其构建包均独立封存并复核。

本轮只证明主机程序链接和注入输入下的行为。实际 Switch 文件服务、耗时、设备栈预算、主机 SDK/IOKit 调用以及 LCP1/EXE3 物理来源均未验证。新日志会改变初始化和停止阶段时序，也可能自身阻塞；其 commit 不能证明其他结果文件自身 commit。

下一项先为第 4 代材料建立独立现场记录/执行入口，校验本轮验证身份及新部署包，明确预等待、CFW 新启动、受控关机和原件回收顺序，并复核设备调用链栈与文件服务生命周期限制。准备工作不增加次数。卡上仍为旧 quiet 版本，旧实测仍是 ISO actual 全 0 的失败，当前现场记录保持 `failed_no_retry / remaining=0`，根因未知。
