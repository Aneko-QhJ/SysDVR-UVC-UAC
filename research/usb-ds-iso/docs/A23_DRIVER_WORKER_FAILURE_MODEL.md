# A23 完整隔离 driver 的 worker 故障与收集边界（2026-10-20）

后续：[独立supervisor收集候选](A23_SUPERVISOR_CANDIDATE.md)在不重跑driver下验证18种固定Python进程安排；60测试与493来源搬移通过，进程退出0且driver完成仍需缓存worker资格，外层退出观察来源未认证。以下保留原阶段。

本阶段把15种指定 worker 故障接入现有完整 driver 隔离模型，与此前72场景合计87场景。仅改变生成的 model_main.m；driver 候选、Objective-C 桥、C helper、driver diff 和受保护代码片段保持原字节。原483来源保持，新增 fixture、renderer、纯字节消费者、audit、tests 共5来源，总计488。未接入生产 receiver。

| 窗口 | 安排与观察 |
| --- | --- |
| Capture 调用内部、读取 ticks 前 | worker 异常返回7 / pthread_exit 9，未改 store 时 driver 仍能完成；未完成写入、错误票据令 Capture Busy，输出清零；无效 Finish / 耗尽令 Capture Poisoned，输出清零 |
| Capture 返回后、BeginCommit 前 | worker 留下奇数版本或注入耗尽；采样已经成功，但 BeginCommit 失败，没有完成事件，也没有可释放的 driver 票据 |
| 持提交票据、append 内 | worker Begin 返回 Busy、ticket0；随后异常返回7时 driver 仍完成；替换 clock 时 post-guard 拒绝完成，原 owner 票据仍3→4释放 |
| 释放后 | worker 留下版本5，或注入最大偶数版本并耗尽毒化；guard 撤销完成，历史 quiet_end 保留，保存当前失败 receipt |
| receipt 已保存后 | 同样的未完成写入/耗尽令 guard 撤销完成；旧成功 receipt 标为 stale，消费者核对其旧快照 |

12个新增场景由 driver 拒绝。3个反例（capture-worker-error、capture-worker-exit、gate-worker-busy-error）保留 driver_complete=true：它们没有改动有效时钟状态，driver 不知道外部 worker 是否健康。新增消费者对15场景均令 completion_admitted=false；完整失败证据可以保存，不能变成完成声明。这是离线材料消费规则，尚未接入生产 supervisor/permit。

每个新增安排创建并 join 一个 pthread，旧72场景含14线程，所以每次有效 fixture 共29线程。worker 只操作注入 C store；诊断在 join 后读取，clock owner 在 join 和后续 driver 检查期间保持存活。极值版本通过测试代码直接注入，不是正常发布 API；正常写入使用 Begin/Finish，不绕过版本。对象替换由串行 journal 在 worker join 后执行，未测试对象释放或回收竞争。未测试 pthread_cancel、进程崩溃、永久阻塞或全部交错；模型子进程有60秒上限，没有增加自动恢复/重试。

新场景的纯字节消费者要求精确25成员：原24份 result/version/facts/worker/session、两 epoch 和 receipt 材料，加外层派生的 worker-materials.json。该清单记录其余24文件的字节数和 SHA-256，要求清单本身为确定格式；核对 schema/case、全部18个 worker trace 字段、17个 version 字段、18个 facts 字段、terminal result、事件与 payload/STATUS、receipt 快照。材料由外层读取 native exports 后缓存，消费者不打开文件。清单只证明所给字节内部一致，不认证原始来源、原子目录快照或现场时钟。

验证结果：

- 87场景在优化/UBSan两版及488来源搬移重建中一致；正确/错误/缺失摘要的只读 CLI 返回0/2/2。
- 新增20、旧并发20及独立 worker20项，共60项无跳过通过。消费者 open/io.open 均被阻断时仍通过全部15新场景，外层正常读文件。
- 270次 trace、255次 version、270次 facts 字段篡改均更新对应 export 和外层清单后仍被拒绝，共795次。375次成员缺失、25次逐文件截断被拒绝；还有额外成员、跨场景、非字节材料与重算 receipt/外层清单后的 stale 快照伪造拒绝测试。
- 原有未参与版本的 profile ABA 负对照仍可通过，不强制写入契约或来源认证。

失败与中间材料均保留。r1 的校验预期误把停止后的 epochs_saved_complete 当作 true；原 driver stop 会清除此资格，但 saved_epochs 保持2。r2 两版原生回放已通过，封存时撞到旧4096节点上限；仅新 audit 的 review 封存/读取上限明确扩为8192节点，文件64MiB、总量256MiB、路径深度18、合法路径、非符号链接/普通文件等旧约束保留，旧审计模块未修改。r3 截断测试发现移除末尾换行仍能解析，r4 补逐文件字节清单。r3 的搬移回放也保存在单独 intermediate-validation 中。此类扩大清单不能替代来源认证。

含失败及中间搬移，本阶段共11份隔离模型、33个 compiler jobs、11次有效原生模型进程、10次无参数拒绝、319线程。最终 r4 原位置及搬移分别两版，共4模型/12 compiler jobs/4有效进程/4无参数拒绝/116线程。执行前检查符号和链接库，未链接真实 USB factory、IOUSBHost/IOKit framework 或实际时钟/context 实现。Python 搬移回放阻止原 checkout 与 /Volumes 的文件打开；hook 不继承到 clang/原生子进程，不证明 OS 能力隔离。

最终证据：

- review：`private/analysis/A23-driver-worker-failure-model-review-20261020-r4`
- review SHA256SUMS：`64e842cd32025f5cf947af2e035ea33885d8ba5fe7075b0698896a95babf0c48`
- validation：`private/analysis/A23-driver-worker-failure-model-validation-20261020-r4`
- closeout：`private/analysis/A23-driver-worker-failure-model-closeout-20261020`
- 中间验证：`private/analysis/A23-driver-worker-failure-model-intermediate-validation-20261020-r3`

只读入口：`tools/audit_a23_driver_worker_failure_model.py --check <review> --expected-sha256 <pin>`，不执行原生模型。新 audit 的8192节点限制仅作用于本阶段 archive helper；历史模块的4096限制保持。

23项保护文件、实际49/65账本及失败修复 owner/state 保持；65已回收、remaining0，81..112未保留。USB/SD/真实SDK/context刷新/部署/正式发行与保留均0，生产采集关闭。

下一步继续离线研究：把外层 worker 成功/失败声明与完整 driver 资格分开的规则，整理为独立的 supervisor 收集候选；覆盖未产生 stdout、缺材料、异常进程退出和超时的确定行为。当前 pthread 线程返回码与缓存材料不等于现场进程来源认证。实际时钟域映射、SDK runtime、quiet/drain、生产 permit 仍未认证。

前序：[独立 worker 失败与材料完整性](A23_WORKER_FAILURE_MODEL.md)、[提交并发与诊断](A23_COMMIT_CONCURRENCY_MODEL.md)。
