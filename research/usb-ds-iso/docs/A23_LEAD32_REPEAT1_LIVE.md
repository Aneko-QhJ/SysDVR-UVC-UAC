# lead32 独立复现及设备只读回收（2026-10-17）

用户明确确认“SD已装回、USB已接Mac、Switch完全关机，可以开始这一次新测试”后，签发并消费一条全新repeat1记录。主机确认WAITING后才提示开机；用户已回复“已开机”。本次只启动一次接收器、提交一次ISO、触发一次，没有自动重试。

**主机再次得到16×192=3072字节，内容和序号精确匹配；本次新增EXE3/primary/LCP1也已回收，保存及正常返回记录完整。** 共只读保存51个原件，四项部署文件匹配，13:41:16.168121+08安全弹出。相对前次45原件新增6份诊断文件、无删除，既有原件仅logfile改变；8份既有ERPT全部字节保持，没有新增保存的错误报告。此结论不等于运行期间绝无错误。

| 观测 | 本次独立复现 | 前次有效样本 |
| --- | --- | --- |
| 固件/接收器/预算 | 与前次相同 | path-span / lead32 |
| 进程及回调 | 退出0，无超时或abort | 退出0，无超时或abort |
| 有效数据 | 连续索引8..23，16包准确 | 连续索引4..19，16包准确 |
| 原始事务状态 | 全部960项native/public状态0 | 全部960项native/public状态0 |
| STATUS | seq0/state0 → seq1/state2 | seq0/state0 → seq1/state2 |
| ISO URB | 387/status3，requested=transferred3072 | 同左 |
| ISO7 | terminal1/bitmapFFFF/actual3072 | 同左 |
| 控制完成 | 0.504667ms | 0.408375ms |
| ISO完成 | 151.421750ms | 151.922042ms |
| 设备保存/生命周期原件 | 新增原件已显式关联，保存及main_return完整 | 已显式关联 |

本次主机首帧28487316=current28487284+32，低11位1684；设备目标FrameID1685。仅在帧域可比较的条件下，目标晚于窗口首帧1帧，对应名义8个槽。实际有效索引8..23落在窗口内；这不是独立帧域对齐或物理总线时序证明。自己的TD0/TD1 ED标签及CC1原始事件已保存，回收log的module/ring范围、上下文及完成字段检查匹配；仍不认证物理同次来源。

当前得到两个独立lead32主机成功样本，各有本次新增文件的显式关联及完整所供设备链，继续支持窗口覆盖方向。文件比较不独立认证物理来源，错误报告归因、根因及长时稳定仍未确认。

## 本次设备文件与保存

新增两组EXE3/primary及两份LCP1，全部保留，不由数量推断开机次数或用户操作。其中 `ep0-383d…execution.bin` 5440字节及对应ownership4384字节具有本次三条接口2目标SETUP、前后状态和序号；仅 `ep0-life-4d7b…bin` 的boot/session上下文与其匹配。

该组启动44条API结果均0，7条URB均status3、无未匹配URB；primary receipt phase9/result0、读回和commit确认成立。LCP1有27条、zero tail，join及owner完成，两次create返回0，primary和EXE保存成功，最后main_return。静默轮询历史不完整的trace_window_complete=false仍保留。

另一新增 `ep0-7fde…` 组合没有本次接口2目标请求；对应ownership2976字节/EXE3 4032字节，也有自己的27条main_return生命周期，仍不归入本次主机。

## 旧成功原件对照暴露的关联限制

5份EXE3均逐个比较。旧 `698c…` 成功记录的相同三条SETUP和seq0/state0→seq1/state2也能匹配当前主机，不能仅用这些字段判定新旧。当前显式选择额外依靠前后快照中新出现的原件及其自身上下文；不会把旧698c当作本次设备证据。

为把这一限制落实为可复核材料，另外冻结一个明确标注的静态对照：当前主机材料配上已知前次698c EXE3/primary和1ff8 LCP1，现有收集器仍返回supplied_chain_complete=true。这证实该标记仅描述现有有限比较的自洽性，不提供独有的跨端会话新鲜性绑定；所有physical/source/root_cause等认证保持false。没有启动硬件对照或修改旧原件。

| 收集包后缀 | bound执行链完整 | 所供完整链 | 解释 |
| --- | --- | --- | --- |
| all-lifecycle | true | false | 全部8份LCP1，保持歧义 |
| context-associated | true | true | 本次新增383d + 4d7b |
| unassociated-new | false | false | 另一新增7fde组合，与本次主机不符 |
| prior-successful-control | true | true | 已知旧成功原件静态对照，不是当前运行证据 |

下一步优先离线审查独有的跨端会话绑定及旧成功记录重放判别，再设计串行提交/持续流，避免把可重复状态值当成唯一会话凭据。此处尚未实施新协议、改动设备包或安排下一次测试。

## 已保存材料与恢复状态

- 正式记录：`private/analysis/A23-lead32-once-20261017-repeat1.json`，保留采集时stage=captured_logs_pending；当前remaining0、acquisition_enabled=false、device_log_pending=false、recovered=true。不得因历史stage再采集。
- 前置签发：`private/analysis/A23-lead32-repeat1-live-preflight-20261017-133727`，manifest `1ce6f6c29f87a6a5189857e8fb55f5fc58915d44865d56bdd1a35febedd29a19`。
- 主机run：`private/runs/A-A23-lead32-waiting-20261017-053747-70aa8f79`，18条，manifest `3dfb3f18092b676eb3b89a84af9ddfca5e8b623c8e41315f236d746ea469f7aa`。
- 主机分析：`private/analysis/A23-lead32-repeat1-live-host-20261017`，10条，manifest `3f7b581da8545226d2b23b6bbbf846139d6c914e9793b2ef8d2f5e634a2e419e`。
- 回收续接：`private/analysis/A23-lead32-repeat1-live-pending-recovery.json`，stage=recovered_ejected；主pending为repeat1_recovered。
- 只读快照：`private/card-cycles/20261017-133944-lead32-repeat1-live-read`，53条（51原件），manifest `78032e70de2a05d60fa816766db4280a4322cb47e306f0e8f77c69bc8b08b493`。
- 设备分析：`private/analysis/A23-lead32-repeat1-live-device-analysis-20261017`，39条，manifest `12ea29e4eaa2bdddd1dc663436f9b60354098371ee0e546a581967dcbcf9f4cf`。
- 四份收集包均在 `private/collections/A23-lead32-repeat1-live-20261017-*`；条目数37/30/30/30，摘要与全部候选列表见设备分析。原始记录及相互比较可搬移后离线复核。

251来源、7生产源、3旧票据、3旧离线记录、3旧现场记录以及两条先前lead32记录均重核保持。未改源代码，未重复运行此前已通过的80项离线回归。只读恢复没有写卡或发USB诊断，所有次数已消费，不增加或补发次数。

用户回复“已接好”后已完成动态识别、只读挂载、全原件回收和安全弹出。下一项仅离线研究会话绑定限制；当前没有新测试授权或现场操作需求。先读取本页及 `private/analysis/A23-lead32-pending.json`。
