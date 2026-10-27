# Q2c 整轮额度租约与停止门离线候选（2026-10-27）

当前研究组织方式见 [研究规则](RESEARCH_RULES.md)。本文保留该模型的实际能力及未证明项；
末尾的额度回执协议是当时提出的后续分支，不再作为所有新诊断的共同前置条件。
涉及真实容量或复用的新实验仍需处理对应约束；当前暂不用虚拟机，旧执行门禁未改写。

最小单段符号候选已完成，r1 的38项测试通过。它先预留完整9组请求和停止所需额度，再在开始、ISO提交前复核计数/时间；未知条件、快照变化、超额或失序都会停止新准入，保持额度不退还。

候选只有模型条件和符号迁移，没有设备额度回执、全局互斥、原生交还、硬截止、真实证据提交或滚动能力。未接入接收器；本轮无SDK、USB/SD、新范围或授权。新增3个研究来源，总679；此前676与冻结Q1 receiver672保持。

## 实现与绑定

- `tools/a23_q2_epoch_lease_model.py`：仅依赖dataclasses/hashlib/json的单控制器、单段模型。
- `tests/test_a23_q2_epoch_lease_model.py`：边界、失效、停止和独立阈值检查。
- `tools/audit_a23_q2_epoch_lease_model.py`：来源、父交接、实际记录与namespace绑定审计。

Binding 包含segment、snapshot/source/recipe摘要、精确shape摘要。Watermark包含generation、trace/身份计数、模型tick、deadline及固定MODEL_TICKS_ONLY域。摘要只绑定内容，不认证设备来源，也不证明不同控制器之间的互斥。

shape固定为before STATUS、BURST、after STATUS，每阶段按接口0/1/2排列；trace上界为3/3/17，目标接口身份上界2，整轮trace69、身份6。这继承 [Q2c来源合同](A23_Q2C_EVIDENCE_BUDGET_CONTRACT.md)的条件包络，并不是新增的实机保证。

Conditions必须显式给出额外流量、停止trace/身份、epoch和stop耗时，以及shape、外部流量、耗时和所有权已知的模型假设。任何未知值、false、错误标签、非模型时钟或不匹配绑定均不能预留。握手本身尚未加入此9组shape，不能把真实额度请求伪装成一个非请求事件。

## 两道门与一个有界段

| 阶段 | 候选行为 |
| --- | --- |
| reserve | 单次尝试；完整shape+extra+stop的trace/身份、epoch+stop时间均需放得下；失败不自动重试 |
| claim | 精确租约一次消费；重新核对同段/generation/deadline、当前计数和剩余模型时间，禁止拿旧快照开始 |
| before | 依次观察三个before组；计数增量与接口/顺序必须匹配，ready组至少保留3条基础记录 |
| arm_iso | 只在before三组完成后发生一次；再次核对当前watermark和时间，不调用真实ISO |
| burst/after | 只有模拟ISO已arm后才能继续既定6组；额外ready、超额、非目标身份post、时序错误使计数条件失效 |
| finish_shape | 九组完成后生成MODEL_ONLY前缀回执；不声称native I/O完成、真实commit、额度回收或下一段许可 |
| stop | 停止新模型操作，最多记录一次已预留的stop额度；超额、时间假设失效或计数未知时不接受stop回执 |

已经观察到的超额无法“撤回”。模型将counters_trusted_in_model置false，保留最后接受的水位及异常报告；不把旧水位冒充当前完整计数。失效后保留租约，不退还credit、不创建第二段。

合法有界非请求事件需在extra额度内且至少消费一条trace；零成本事件不能无限穿过模型。shape_complete只描述已观察的模型前缀，之后的异常仍可使控制器停止；裸字段不代表当前健康。

## 验证结果

| 检查 | 结果与前提 |
| --- | --- |
| 测试方法 | 38项通过，无skipped/expected failure |
| 容量网格 | trace0..256 × identities0..32，共8481组；独立阈值oracle为trace≤186且identities≤25 |
| 条件预留 | 网格中4862组可形成符号租约；采用shape69/6、stop1条/1身份、extra0等显式模型条件，真实设备grant数0 |
| 当前216/19 | shape69加stop1条已超256，预留即拒绝；没有模拟ISO arm或轮中半准入 |
| 延迟claim | 121种tick0..120；deadline100、epoch10、stop2时，89种tick≤88可条件开始；均未因此arm ISO |
| 有界额外事件 | 一条已声明非请求trace分别放在9组请求前后10个切点，均可完成模型shape，仍保留stop额度且不退款 |
| 身份/快照 | source/recipe/shape/snapshot、generation、计数、clock域变化均拒绝；租约改标签和重放拒绝 |
| 事件失效 | 额外或错误ready、超额trace/身份、未预算非请求、零成本非请求、计数漂移与时间超额均停新准入 |
| 停止 | 保留预留；stop额度一次消费，超额/超时/计数未知不能取得stop回执或cleanup许可 |
| 全局来源边界 | 两个独立控制器可对同一模型快照各自预留；测试明确保留global_cross_controller_serialization=false和actual_device_grant_authenticated=false |

网格的阈值来自Q2c的shape69+stop1、身份6+stop1，未调用候选内部预算计算作为oracle。时间和extra条件是模型输入；没有用它们认证设备耗时或真实额外流量。

三组完整结果摘要与详细检查日志保存在审计的cases.json/tests.log。没有重跑Q2b的5760个排列，也没有把8481次条件判定计为真实采集。

## 目前仍缺什么

模型只验证单控制器公开事件下的有限顺序；不存在真实counter attestation、设备串行签发、持久化租约账本、消息验证、并发交错或ABI适配。它的hash不是权限凭证，Python私有属性也不是对恶意代码的安全隔离。

MODEL_TICKS_ONLY没有物理时钟或定时器，耗时假设不提供硬中断。单次段回执只说明符号shape前缀，不提供SDK callback/DMA交还或无损证据提交。

因此当前不能把模型Lease传给真实driver。必须先解决设备计数与grant的真实来源、快照一致性以及全局单次消费；新增握手/ACK/失败恢复请求也要计入完整shape预算。原生backing交还仍遵守Q2a未知项，Q2b的代际隔离也不替代它。

下一项仅电脑设计最小设备额度回执协议：定义身份、计数generation、来源绑定、单次消费、拒绝/失效及丢回执后的状态分类；重算握手本身的trace/身份/时间开销。先限定一个有界段，不实现自动滚动或真实设备适配，不直接第四轮。

## 封存与操作状态

最终审计：`private/analysis/A23-q2c-epoch-lease-model-review-20261027-r1`，摘要 `6f290b5428f8a917c41800acb7db5c1af5c4e9b2f06e0a2d70b1ea7816b544d3`。保存679来源清单、源码、38项检查、网格摘要、停止门与当前216预拒绝记录。

最终交接：`private/analysis/A23-q2c-epoch-lease-model-closeout-20261027`。Q1 actual465/namespace465、旧actual417/九namespace、138快照及此前sealed evidence保持。remaining=0、acquisition_enabled=false、日志pending=false，SD最后已弹出，现场不推定。本轮没有SDK对象/调用、USB/SD、编译或原生fixture。
