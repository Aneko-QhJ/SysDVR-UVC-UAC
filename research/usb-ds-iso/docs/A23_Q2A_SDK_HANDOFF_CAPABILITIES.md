# Q2a SDK 交还能力表（2026-10-26）

后续[Q2b有限归属模型](A23_Q2B_GENERATION_MODEL.md)已完成34项测试及5760种有限事件安排；原生交还仍是假设，未接SDK或真实入口。以下为本阶段能力核对及当时下一步，原封存保持。

本轮资料核对完成：11 份 Apple 官方页面、当前本地 macosx27.0 的 4 份 IOUSBHost 头文件，以及 Q1 实际编译的生成代码形成 14 条路径能力表，22 项来源锚点核对通过。表中明确分开文档保证、当前代码行为、局部推断及本次资料未说明的条件。

尚未证明完整的原生 backing 交还或所有回调排空，也未实现新的接收器、取消或复用协议。本轮 SDK 对象/方法调用、USB/SD、编译、fixture、新许可均为 0。672 来源、Q1 原件与十个 namespace 保持。

## 来源与 API 身份

当前 ISO selector 是 `enqueueIORequestWithData:transactionList:transactionListCount:firstFrameNumber:options:error:completionHandler:`。Apple 文档的 preciseIdentifier 与该 Objective-C selector 一致，参数为 IOUSBHostIsochronousTransaction。旧 frameList selector 是另一个 API，不能跨 API 套用错误返回与回调保证。[当前 transactionList API](https://developer.apple.com/documentation/iousbhost/iousbhostpipe/enqueueiorequest(with:transactionlist:transactionlistcount:firstframenumber:options:completionhandler:))、[旧 frameList API](https://developer.apple.com/documentation/iousbhost/iousbhostpipe/enqueueiorequest(with:framelist:framelistcount:firstframenumber:completionhandler:))。

网页工具对新页面只能读取 JavaScript 提示，且不接受页面链接的 Markdown content-type；本轮改为只读 GET Apple 官方提供的 `.md`，校验 framework、symbol metadata、selector、字节数与 SHA256。没有把网页内容当作执行指令。11 次 GET 均完成，资料及访问限制保存在 `private/analysis/A23-q2a-sdk-handoff-docs-20261026`。

本地 SDK 采用最终规范路径，前三份头文件与上轮摘要一致，另加入 IOUSBHostIOSource.h；它们只是当前 SDK 的观察，不认证 Q1 编译时 SDK 的身份。主机路径以 Q1 r4 build 的 generated 文件和其中的 source 副本为准。

## 14 条能力路径

“未建立”表示在本次所列精确文档、头文件与代码中未建立该保证，不表示已经实测其相反行为。

| 路径 | 已有保证或代码行为 | 不能据此授予的权限 |
| --- | --- | --- |
| P1 正常 ISO completion | 当前 API 与回调类型绑定；回调报告 transfer 结果，调用者提供 data/transaction backing | 当前精确页面与头文件没有给出完整 backing 最后访问及所有 closure 寿命协议；queued owner handler 仍需自己完成 |
| P2 当前 ISO enqueue 返回 false/error | 原始 BOOL/error 可保存；现有 lease 对拒绝或矛盾结果 pin 保留 | 本次精确 transactionList 页面未列出错误返回后绝不回调的条款；不能借用旧 API 条款 |
| P3 control enqueue 返回 error | 官方明确该方法返回错误时不执行 completion | 不取消另一个 pipe 的 ISO，不交还旧 owner queue 工作 |
| P4 旧 frameList enqueue 返回 error | 该旧 selector 有明确“不回调”说明 | 不能提升为当前 transactionList selector 的保证 |
| P5 异步 pipe abort 返回成功 | 本地 SDK 明确不等待被取消 I/O 完成 | 不代表 I/O 已完成、control 已取消、本地回调已结束 |
| P6 同步 pipe abort 返回成功 | 相关被取消 I/O 在返回前完成/终止；按方法说明阻挡新 I/O | 不能扩大成 control、interest、所有 closure 与本地队列的全域 drain；owner queue 内同步调用安全性未建立 |
| P7 device-request abort 返回成功 | 独立方法取消 send/enqueueDeviceRequest 家族 | 不是 pipe ISO 或本地 queued work 的取消操作 |
| P8 任意 abort 失败 | 失败结果可留证 | 单靠失败不产生成功交还依据 |
| P9 destroy 返回 | 连接关闭、interest 注销；重复调用无进一步效果 | 本次资料没有把已排队本地工作、所有 closure 与 backing 交还统一为一个完成点 |
| P10 owner queue 前缀 fence | 当前代码确实把原生回调转交该队列；interest 原生交付来自另一队列 | 一个本地前缀不能自行关闭稍后的外部入口。这是局部推断，不是实测全域排空 |
| P11 保存并 acknowledge | driver 确实调用 ack，owner 清自己的两个引用；driver/lease 继续持有 backing | 保存成功没有新增 rearm、原生交还或共享引用释放 |
| P12 分配成功 | 内核映射 NSMutableData 交给调用者，其 length/capacity 不可改 | 分配所得的对象所有权不回答 active I/O 何时停止访问；不得用 resize 实现池复用 |
| P13 closeUnused | 当前 lease 对 runtime touched 拒绝清理；取消适配器只接受异步选项 | 准备期清理不能直接用于 active I/O；不能只更改同步选项接上现有取消路径 |
| P14 generation 或安静/终结采样 | 提供逻辑身份与历史观察 | 不阻止旧 DMA 访问，不关闭回调来源，不提供 backing 交还 |

P1/P2 的范围见 [transactionList 精确文档](https://developer.apple.com/documentation/iousbhost/iousbhostpipe/enqueueiorequest(with:transactionlist:transactionlistcount:firstframenumber:options:completionhandler:))；P3/P4 的显式错误条款分别来自 [control enqueue](https://developer.apple.com/documentation/iousbhost/iousbhostobject/enqueuedevicerequest:data:completiontimeout:error:completionhandler:) 和 [旧 frameList enqueue](https://developer.apple.com/documentation/iousbhost/iousbhostpipe/enqueueiorequest(with:framelist:framelistcount:firstframenumber:completionhandler:))。三个 selector 分别保留 metadata，未合并成一条通用规则。

P5/P6 使用本地 IOUSBHostDefinitions.h 与 [同步 abort option](https://developer.apple.com/documentation/iousbhost/iousbhostabortoption/synchronous)、[pipe abort](https://developer.apple.com/documentation/iousbhost/iousbhostpipe/abortwithoption:error:)；P7 的范围来自 [device-request abort](https://developer.apple.com/documentation/iousbhost/iousbhostobject/abortdevicerequestswithoption:error:)。本轮没有调用这些方法，也不从局部请求完成推断所有域已交还。

P9/P10 的文档输入是 [destroy](https://developer.apple.com/documentation/iousbhost/iousbhostobject/destroy()) 与 [interest handler](https://developer.apple.com/documentation/iousbhost/iousbhostinteresthandler)；P12 是 [内核映射数据分配](https://developer.apple.com/documentation/iousbhost/iousbhostobject/data(withcapacity:options:))。其余当前代码事实和精确行号见审计 `source-facts.json`，每一行能力也标明 `documented_partial`、`current_source_behavior` 或 `source_based_inference`。

## 队列与同步取消的边界

Q1 main 把 owner queue 设置为 main queue，SDK interface 也收到 caller queue；owner 的原生回调又 dispatch_async 本地处理。interest 文档明确由另一条内部串行队列交付，代码还会将其转交本地队列。多层队列的前缀不能替代入口关闭。

同步 abort 的 I/O 完成保证不等于“owner queue 上等待一定安全”。本次来源没有建立其内部等待是否依赖被占用队列，因此既不宣布实机死锁，也不把它直接接到 owner queue 或任意后台线程。现有 lease/driver 的异步专用检查也需重新设计，不能只换一个 enum 值。

## 给 Q2b 的最小输入合同

后续可以在电脑上验证本地 slot/generation 归属，且不要求先用无限观察证明“未来永远无事件”。但模型必须明确区分两个问题：

- **逻辑隔离**：旧/重复回调绑定不可变 request token，只接触所属代元数据，不能清新代 pending、读新代数据或释放新代资源。
- **原生访问权**：是否已获 API 与具体事件绑定的 backing 交还依据。本轮仍未完成；模型中若注入该事件，必须标明是条件假设，不能产生 SDK 证明、硬件入口或复用许可。

最小候选应为有限 slot 和有限旧代元数据设置上限，以显式事件推进；覆盖旧/重复回调、指针相同但 generation 不同、证据写入失败、缺失/矛盾交还、队列工作未交还、满池及停止。未知交还保持 retained，并停止新准入。不得通过放松标签、清空历史、自动扩容或延长安静窗口补过。

Q2c 的 trace、身份与窗口容量合同继续独立；本次能力表没有改变 256 trace、32 身份、30s 窗口或部署文件。

## 封存与操作状态

| 材料 | SHA256SUMS 摘要 |
| --- | --- |
| 官方页面与访问记录 | `948fb9e78013f18ea4f13c7bd5b286b6e6097cc78ec7ee8f2102b0d3a7c6fc8a` |
| 14 路径能力审计 | `ebe66c6e2021fd457165f3501215a9f78fa81da422537e3a81ae2c9d3a5beedb` |

审计目录为 `private/analysis/A23-q2a-sdk-handoff-review-20261026`；最终交接为 `private/analysis/A23-q2a-sdk-handoff-closeout-20261026`。机器表保留 `native_buffer_handoff_fully_proven=false`、`all_callback_drain_proven=false`、`current_native_reuse_permitted=false`，14 行均不授予共享 backing 复用或全域 drain 权限。

Q1 actual465/namespace465、旧 actual417/九 namespace、138 件快照和所有原 sealed evidence 保持。remaining=0、acquisition_enabled=false、日志 pending=false、SD 最后已弹出，现场不推定。下一步仅离线 Q2b 最小归属/准入候选，不启动第四轮或新的真实测试。
