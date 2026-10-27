# 最终采样之后的状态表述（2026-10-26）

已完成[终结采样修补](A23_LIVE132_COMPLETION_OFFLINE.md)之后的语义核对，并增加只读归档状态视图。6个原生诊断场景、13项拒绝检查和2种CLI展示通过。结论是：历史采样通过与后来观察到停止可以同时成立，不能把前者显示成当前设备仍健康。

原666来源和接收器build保持，新增tools/a23_completion_status_view.py与tools/audit_a23_postcompletion_semantics.py，共668研究来源。本轮不产生新接收器候选，冻结接收器原件保持；诊断只使用模拟SDK操作，无USB或SD访问。

## 字段必须按其切点解释

| 原字段/材料 | 可以表达 | 不能表达 |
| --- | --- | --- |
| loop.success、completion_accepted | 最后采样与冻结快照一致，终结事实写入成功 | 调用者读取该布尔值时，SDK或设备仍健康 |
| completion.json的current_entry_complete/stopped | 最后采样保存的entry字段；名字中的current指采样当时 | 当前现场状态或采样后的全部变化 |
| consumer.completion.local_completion_cut_accepted | 提供材料符合该历史采样合同 | 生产者认证、实时监控或SDK drain |
| 后来提供的模型entry观察 | 另一明确时刻的模型观察结果 | 此刻真实设备的状态 |
| 当前设备状态 | 本轮没有新现场证据，保持未验证 | 由历史通过、loop标志或模型结果推断出来的健康 |

冻结接收器的fact已经有historical_cut_only、queue_prefix_only和future_events_excluded=false，归档消费者也有current_state_after_sample_verified=false。原始loop.status仍使用通用success布尔值，未来调用者必须按上述范围解释。当前可执行接收器只有文件检查入口，没有正在使用该状态的硬件采集界面。

## 只读展示

新视图先运行完整666接收器消费者，不接受裸loop字典作为通过证据。它分别输出historical_cut、latest_supplied_model_observation和current_device_state，不把它们合并成一个“当前成功”字段。

只有有效归档时：

> 历史终结采样：通过；采样后的模型状态：未提供观察；当前设备状态：未验证。

另有绑定同一终结记录、时间晚于最后采样的模型停止观察时：

> 历史终结采样：通过；随后提供的模型观察：已停止；当前设备状态：未验证。

正常对照的后续观察使用“完整”，也仍保持“当前设备状态：未验证”。所有输出均有current_live_health_verified=false、overall_hardware_success=false、sdk_drain_verified=false、buffer_reuse_authorized=false；后续模型观察自身的is_current亦为false。

可选观察必须明确model_only=true、来源为离线fixture的entry.result getter、时钟为RAW纳秒，并绑定同一终结事实的完整binding摘要。不同记录、早于/等于采样的时间、整数冒充布尔、相互矛盾的complete/stopped、未知时钟或声称来自真实设备均拒绝。它不认证观察作者，因此也不会把提供的模型文件提升为硬件证据。

工具可通过--host、--build、--job读取归档；可选--model-observation只读取后续模型观察文件。它不访问实时SDK或设备，不改写原归档；底层消费者沿用既有临时副本校验流程。两种真实CLI调用的JSON输出均与直接函数结果一致。

## 诊断及结果

使用冻结666接收器、原SDK模拟资源和原完整消费者。诊断编译副本只在exporter中增加两个fixture checkpoint，分别在终结事实写入前、写入后；移除这两行后必须逐字节恢复冻结exporter。fixture另外在最终entry getter之前增加观察切点和RAW时刻。编译副本明确另以摘要绑定，不冒充原receiver二进制。

| 场景 | loop/历史终结 | 后续模型观察 | 归档视图 |
| --- | --- | --- | --- |
| normal | 通过 | 完整 | 历史通过，当前设备未验证 |
| completion_entered注入，尚未最终采样 | 拒绝 | 已停止 | 不存在合格历史通过，消费者拒绝 |
| 最终采样之后、事实写入之前直接interest | 通过 | 已停止 | 历史通过，后续模型已停止，当前设备未验证 |
| 事实写入之后直接interest | 通过 | 已停止 | 同上 |
| 最终采样之后排队整个interest入口 | 通过 | 已停止 | 同上 |
| loop完成后、最终observer之前interest | 通过 | 已停止 | 同上 |

后四项事件发生在新合同的最后采样之后，不能拿它们反推该采样本身失败，也不能拿采样通过排除它们。它们验证了上轮已声明的边界；上轮四个发生在新采样之前的旧反例仍然属于应拒绝的情况，本轮提前注入对照也继续拒绝。

成功历史材料在live getter之前单独保留at-return副本，随后用同一记录绑定后续模型观察。4种后续故障在getter中追加停止日志，最终host材料被完整消费者以entry event inventory differs拒绝；隔离保留的历史副本仍可验收。新视图只并列呈现这些不同切点，不删除停止日志、覆盖旧fact、重开观察或修改历史结果。

诊断copy本身会增加返回后的串行阻塞，两个checkpoint也是模型注入点，不能用于测量真实SDK延迟、发生概率或推断真实交付队列。这里的1次ASan/UBSan编译、6个原生进程和2个CLI进程均由创建者直接wait；6个namespace仅为临时模拟。

13项拒绝由提前故障材料1项、后续探测改变事件清单4项，以及视图输入的8项类型/绑定/时钟/来源/范围反例组成。5份可接受历史材料分别验证仅归档与附后续观察两种输出；每一份均保持现场未验证。

## 收束后的结论

当前离线链已经能区分传输材料验收、终结采样通过、后续一次模型观察和未知现场状态。继续添加观察窗口或完整文件检查，只会把最后一个切点向后移动，不能证明“未来永远没有事件”。本轮不为此扩张通用模型，也不提出重复三轮实测。

视图是新的只读归档工具，尚未作为运行中硬件采集界面接线；冻结receiver和其文件检查入口保持。若未来重新开放硬件入口，调用者必须使用明确的采样范围表述，不能直接把原始loop.success当作现场健康标签。真实SDK交付、排空、释放/复用及持续流仍需独立问题和证据，当前没有对应新授权。

## 封存

审计private/analysis/A23-postcompletion-semantics-20261026-r1，SHA256SUMS摘要40bfbda7b74a7c5b3b056f39c981b9f49c3d781f0a59ef42b7fa3749a4b43cf4。内含诊断改动摘要、编译/原始输出和wait记录、6个模型消耗记录、历史副本、后续模型观察、状态视图和CLI输出。

最终668研究来源、旧666保持、冻结receiver引用、未改actual417、九namespace清单、票据和交接见private/analysis/A23-postcompletion-status-closeout-20261026。正式465..512未保留/授权，remaining=0、acquisition_enabled=false；本轮USB/SD访问、真实SDK对象、正式新范围/namespace/授权均0。SD最后已安全弹出，设备日志不待回收，当前现场未刷新。

本阶段离线语义核对已闭合。后续优先整理现有合同与证据结论，或在有明确需求时接入该状态视图；不再为追求未来无事件增加重复采样。任何新的硬件工作仍须先限定问题、停止条件和新授权。
