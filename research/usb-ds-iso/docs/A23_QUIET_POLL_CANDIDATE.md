# A23 独立quiet轮询与deadline适配候选（2026-10-20）

后续：[driver隔离副本与时钟桥验证](A23_QUIET_DRIVER_COPY.md)已生成完整driver补丁并编译对象，27个Foundation桥场景及58测试通过；完整SDK模型尚未执行，profile读取原子性和来源仍未认证。以下保留原阶段。

接续[原生精确时钟候选](A23_NATIVE_CLOCK_CANDIDATE.md)，新增C quiet适配层，将精确最短等待与完成事件/guard状态转换结合。该层只接受injected-driver域用于quiet，guard和append结果由mock提供；没有接入冻结Objective-C driver或真实SDK。

## 已验证的顺序

当started和epochs_saved声明有效、且quiet起始ticks非0时：先检查guard，再精确比较250ms；不足阈值仅等待，达到阈值后先尝试append完成事件，再次检查guard，最后才能标记settled。事件轨迹编码能区分各次调用和成功/失败，不能仅凭事件写入成功就认定quiet完成。

| 情形 | 结果 | 后续轮询 |
| --- | --- | --- |
| 未开始或epoch尚未保存 | idle，不写完成事件 | 可继续等待 |
| 2/3 timebase不足250ms | waiting | 阈值等号时才完成 |
| 完成事件append失败 | journal_failed，撤销完成资格 | 不重试 |
| 完成事件成功、post-guard失败 | 保留事件声明，但不settled | 停止，不重试 |
| 停止事件append也失败 | journal_failed | 不重试 |
| 曾settled，之后guard失败 | 撤销settled | 保留旧settled_at作诊断 |

`epochs_saved` 在此候选中表示原driver的实时 `_complete` 资格位，失败会清除这个位，不表示删除已保存epoch文件。`settled_at` 历史值单独不能作为完成证明。未知/跨域/实例变化/timebase变化、倒退、溢出、未开始sentinel和不一致的初始完成标记均不得产生新的完成声明。

本适配只建模quiet分支。原driver的资源管理、epoch调度、abort、callback入口、回执和日志持久化均不在执行范围；停止/journal-failed的快速路径和无epoch时的idle也不是完整driver的所有行为，因此 `quiet_state_machine_matches_full_driver=false`。

## deadline策略保持

独立deadline入口接受显式的has_arrival及选好的end样本，不自行查询now。保留冻结实现的策略：

- 已有arrival：ceil(ns)大于limit才超时，等号允许。
- 尚无arrival的poll：ceil(ns)大于等于limit即超时。
- 起始ticks为0或时钟无效：按超时处理。

例如2/3 timebase下47 ticks为31又1/3ns，ceil为32ns。在limit32下，arrival仍在界内，而poll已按原有保守策略超时。这一最大时限策略未被误替换成quiet的精确最短等待规则。调用方仍需正确把原arrival=0 sentinel映射到“尚无arrival”，不能把该0当成实际到达样本。

## 结果及封存

604个quiet场景、1720次轮询和166个deadline边界，在优化/UBSan两版中与Python状态参考及Fraction算术一致。包含全部64种初始标志组合、明确故障顺序、不同ratio阈值以及512组固定种子的状态序列。每版还验证空指针/状态失效与12种坏协议输入。

新增20项、原生算术18项及旧缓存时钟16项共54测试，无跳过通过。447来源搬移后重新编译两版，全部向量/状态/轨迹/坏协议结果一致；正确/错误/缺失pin的只读CLI返回0/2/2，检查时不执行C二进制。

首轮r1原生结果已通过，但单测误写deadline数量应超过400，实际边界集为166；首轮19通过、1项数量断言失败。仅修正该断言后生成r2，C实现和fixture字节未改；r1及失败日志保留。r1、r2和搬移合计6份离线fixture构建、90次fixture进程执行。

- 最终审查：`private/analysis/A23-quiet-poll-review-20261020-r2`，451清单成员，摘要 `5764388c817d2c1f586f6248be38d911a3dd70ac6240d811661903bec9ba169f`。
- 初轮审查：`private/analysis/A23-quiet-poll-review-20261020-r1`，摘要 `a8b05c4aedb190d276700d1c28ff8a82861f9d6ca89861522a13dfd64167c8ab`。
- 验证：`private/analysis/A23-quiet-poll-validation-20261020-r1`，含54项最终测试、初轮失败日志、搬移重编译、源规则及顺序证据。
- 收口：`private/analysis/A23-quiet-poll-closeout-20261020`，含447来源、票据/文档快照、23保护项及真实账本摘要。

候选文件为 `host/a23_quiet_poll_candidate.h/.c`、`tests/a23_quiet_poll_candidate_fixture.c`、`tools/audit_a23_quiet_poll_candidate.py` 和对应Python测试。原442来源、时钟候选和冻结driver均保持原字节，仅增加5份来源。

guard成功和append成功都是mock返回值，不证明资源健康、日志持久化、实际quiet或callback drain。原生产实现未接入修复；未构建/启动生产receiver，USB/SD/真实SDK/context刷新/正式发行/保留均0。65仍已回收、remaining0，81..112未保留，采集关闭。

下一步离线准备冻结Objective-C driver的隔离副本补丁和回放方案，明确quiet起点的clock实例/timebase快照及生产域的适配要求；先审查fixture的mock和构建输入，再决定可执行的纯模型范围。原receiver及真实SDK入口继续保持关闭。
