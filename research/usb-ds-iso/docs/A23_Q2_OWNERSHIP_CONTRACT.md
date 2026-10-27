# Q2 资源所有权、复用与证据容量合同（2026-10-26）

后续[Q2a交还能力表](A23_Q2A_SDK_HANDOFF_CAPABILITIES.md)已完成11份官方页面/4份SDK头文件/14路径资料核对，明确原生完整交还仍未证明；下一项仅离线Q2b归属与准入候选。下文问题卡为本合同初版顺序，历史阶段封存保持。

首版 Q2 离线合同已完成来源核对，尚未实现新的接收器或复用候选。现有三轮程序没有可用于持续传输的存储交还协议，不能通过重置计数器、换 generation 标签或增加第四轮来补齐。

本阶段只读取封存源码、Q1 原件与当前本地 SDK 头文件。Q1 的 [有界实测结论](A23_LIVE132_Q1_FIRST_RESULT.md)保持；本轮没有编译、fixture、SDK 对象、USB/SD 操作、新范围或授权，remaining=0。

## 实际执行来源

主机依据 Q1 r4 build 的编译命令和 generated 文件，build manifest 为 `dc0373e727426069db1bf7d084da69a38b11c7a8207f56b5bf2be126dc2c7035`，672 来源束保持。不能直接用通用 owner 的 960 transaction 模板解释本次 128 transaction 的生成程序。

设备依据已部署 package 的 binding、封存 device review 和 recipe：runtime recipe `37269528ee3baa2941e1cb9268ccd4702d9db5b0fec87e913d3111c99b6e894f`。实际来源的 trace 容量为 256、owner identity 槽位 32、窗口 30000ms；checkout 通用模板的 128/16 不代表部署配置。

23 项来源锚点及精确行号、原件副本保存在 `private/analysis/A23-q2-ownership-contract-20261026-r2/source-facts.json` 和 `inputs/`。这些是静态来源核对，不是新协议的模型或硬件证明。

## 谁仍持有资源

| 对象 | 当前持有者与已实现行为 | Q2 缺口 |
| --- | --- | --- |
| 每组 payload / transaction backing | owner、driver 数组、lease 数组共同持有；保存成功后 driver 调用 acknowledgeEvidenceSaved，owner 清掉自己的两项引用 | driver 与 lease 仍持有，owner 状态未恢复 prepared；没有可重用池或交还 API |
| 三组固定存储 | lease 验证三组地址/长度，driver 保留全部存储和 resources；固定 n<3 | 不能把第四次提交映射回第一组；重建 owner 也不能证明旧 SDK 访问结束 |
| ISO/control 回调 | closure 固定捕获 epoch n；原生入口先更新原子状态，再转交 owner queue；重复/异常入口会置坏状态 | epoch 计数不是 buffer generation 隔离；旧回调元数据必须独立存活 |
| pipe/interface/service/interest | lease、driver、entry 保留资源并有 self hold；closeUnused 拒绝 runtime touched 资源 | 缺主动 I/O 完成、取消后统一关闭和交还合同 |
| 失败请求 | 异步 abort 后保留 backing；指针不匹配时 owner 隔离保留；stop 不授予释放 | 取消成功返回、人工关机或终结事实均不能代替原生访问权交还 |
| 设备 URB 身份 | session 内 append-only；重复(channel,id)拒绝；终态只清 active，不回收身份槽 | 长流需要身份寿命、预算和 session 边界，不能借 pending=0 清空身份历史 |
| payload 快照、journal、证据文件 | backing 之外另有复制和持久化；本次按三轮上限有界 | 背压必须计算快照、回调元数据和证据容量，不只是 DMA backing |

owner 的保存确认和 lease 的所有权不是同一个层次。三组 backing 合计 84480 字节，这个数字不包含快照、SDK 内部存储、journal 或其他对象，不能作为整个进程的内存上限。

## 当前本地 SDK 头文件能说明什么

本轮读取选中 SDK 的规范路径、三份 IOUSBHost 头文件与 SDKSettings，并保存字节摘要；其 CanonicalName 为 macosx27.0。framework 的 Headers 路径含别名，首版审计被严格文件读取器拒绝；失败原样封存，r2 将最终路径规范化后通过。没有通过这些文件认证 Q1 当时编译使用的 SDK 身份。

| 头文件说明 | 可以作为合同输入 | 不能自动推出 |
| --- | --- | --- |
| Asynchronous abort 不等待被取消 I/O 完成 | 当前异步返回不足以授予 backing 复用 | return=true 已无原生访问或已排空回调 |
| Synchronous abort 等被取消 I/O 完成后返回 | 可作为下一步要审核的更强交还机制 | 所有 closure、interest、owner queue 工作均已返回或不再到达 |
| I/O 在指定串行队列服务，interest 在另一个内部串行队列 | 必须分别分析入口与队列寿命 | owner queue 上一次 barrier 覆盖了所有来源 |
| destroy 移除连接并注销 interest | 关闭阶段需要纳入对象/服务生命周期 | 头文件已给出全部 buffer 与已排队回调的交还时点 |

本次未调用 abort、destroy 或任何 SDK 方法。正常完成、提交拒绝、同步取消和销毁的精确 buffer/closure 寿命仍需有来源的能力表；同步取消与 owner queue 的等待依赖也尚未核对。

## 必须先满足的十条合同

1. **不可变身份**：每次提交绑定 session、slot、generation 和 request ID；旧回调不能冒充新请求。
2. **原生访问权交还**：复用前须有独立、可解释的 SDK backing 访问结束依据。generation 检查只隔离逻辑身份，不能阻止旧 DMA 写入同一地址。
3. **证据提交**：完整快照与可验收的持久化先于存储改写；保存失败保留该 generation。
4. **旧回调元数据**：迟到、重复回调只访问所属代的不可变元数据，不解引用已复用的旧指针，不清掉新代 pending；按既定失败政策停止新准入并保留相关资源。
5. **多域取消**：分别定义 ISO、control、interest 和本地队列工作的寿命；一次 pipe abort 不是所有域的关闭协议。
6. **有界池与背压**：free、pending、quarantine 及旧回调元数据均计入容量；耗尽时停止新提交，不覆盖活跃存储或自动扩容冒充有界。
7. **证据额度**：提交前为完整请求安排、停止证据和不确定性保留额度；不清空 trace 或覆盖旧原件。
8. **设备身份与线序号**：明确 session 内身份预算以及 16 位 wire sequence 的回绕政策；终态身份不自动回收，generation 不能代替线上的关联合同。
9. **停止与释放分离**：stop、保存回执、终结切点、worker 返回或人类关机确认本身不授予 active SDK 存储释放。
10. **新实机边界**：任何未来实验须最新 138 件基线、新候选、新范围、新授权与当次设备确认；本文未提出或保留新序号范围。

复用许可必须同时满足：同一不可变请求身份、证据已提交、原生 backing 访问已交还、本地访问者已交还或只保留安全旧元数据、无所有权不确定性、池和证据额度可用。当前这组条件没有实现；交还未知时保持 retained 并停止新准入。

不要求以无限等待证明“未来永远无事件”。可用的协议应分别证明 backing 的访问权交还，以及仍可能存在的旧回调如何安全访问元数据。

## 从 Q1 原件重算的容量

| 项目 | 本次原件与静态来源 |
| --- | --- |
| trace 分组 | 30 组请求完整分割全部 ordinal1..216，无重复/遗漏 |
| 前置 | 三接口 SET_INTERFACE 共 18 条 |
| 每轮 | before STATUS23 + BURST20 + after STATUS23 = 66 条；三轮分别重算一致 |
| 三轮 | 18 + 3×66 = 216，容量256，剩余40 |
| 相同形状四轮 | 18 + 4×66 = 282，超出26；这是条件推算，不是未来请求一定同形的保证 |
| 单请求准入 | 现有实现预留17条；观测到的66条/轮不能作为任意交错的最坏上限 |
| owner identity | 19/32 已占用，19项均status3、pending0，仍只剩13个身份槽 |
| 窗口 | 30000ms；没有无损切换窗口、消费旧证据并滚动导出的协议 |

设备端还会在填写/重投 ISO backing 前检查 ownership guard。扩容或滚动证据必须保留该保护、不可变历史和新旧 session/generation 关联；本阶段没有更改设备容量或清理任何记录。

## 问题卡和下一步

| 顺序 | 仅电脑要解决的问题 | 完成标准 |
| --- | --- | --- |
| Q2a | 当前 SDK 在完成、拒绝、异步/同步取消、destroy 各路径到底交还什么，在哪个线程/队列交还 | 逐条绑定一手来源的能力表；未知项仍拒绝复用，不把头文件说明扩大成全域 drain |
| Q2b | slot/generation 与旧回调元数据怎样保持有界 | 最小状态机候选；旧/重复回调、指针别名、写入失败、未知交还、满池反例不能授予复用；模型不冒充 SDK 证明 |
| Q2c | 256 trace / 32 identities / 30s 窗口如何支持有界续接 | 先建立完整最坏预算、停止和无损证据交接合同，再决定容量或设备代码是否需要变更 |

先做 Q2a；不能只增加相同成功样本、重开安静窗口、修改计数器或直接第四轮。Q2b 的代际隔离只能解决本地归属问题，Q2c 的证据合同也不自动授权 buffer 复用。

## 封存

审计 r2：`private/analysis/A23-q2-ownership-contract-20261026-r2`，摘要 `7133bb76bea0fd6c11d7075120947c945aedf0d0c13c380941ee8f07cdb0c6ad`。首版规范路径拒绝：`private/analysis/A23-q2-ownership-contract-20261026`，摘要 `4d1a4d2ef120d87b87143dad110a663a048fc54062a5f32b20c84ef4af555b35`。

最终交接 `private/analysis/A23-q2-ownership-contract-closeout-20261026` 保存合同、SDK 观察、容量、23项锚点、票据前后与文档副本。672 来源束、旧 actual417/九 namespace、本次 actual465/namespace465、Q1 全部 sealed evidence 和 138 件快照保持；日志 pending=false，SD 最后已弹出，当前设备现场不推定。
