# A23 STATUS计数语义修正与判断前留证（2026-10-22）

最新实测结果（2026-10-22）：[同接口两轮成功及时间线](A23_LIVE75_FIRST_RESULT.md)已核对。一次采集完成113..128和129..144，两个新URB387/403共6144正确字节，STATUS/ISO7通过，接收器exit0并由创建者直接wait。唯一150条设备trace与两轮状态/序号/URB一致，关联27条生命周期报告正常返回；SD91原件已只读回收并安全弹出。
本次许可与113..144整段耗尽、remaining0，不补次。另有一份生命周期仅4条有效记录、末条quiet_enter，无明确上下文，保留为未归因；此前81失败字段仍未知。已确认有限串行复用观察，持续流、长期稳定、跨时钟及quiet drain仍未验证。
电脑时间线显示两次触发相隔1.639秒，首轮保存至第二轮STATUS意图1.476秒；冻结调用链在轮间至少执行六次完整校验，尚无单次哈希独立计时。下一项在电脑上设计校验去重与计时，保留每轮提交前变化拒绝；以后真实节奏需新有界实验及新授权。本次旧75件候选只可归档验证，不能重启。以下未执行/未保留/待授权表述均为此前阶段历史。

最新实测候选（2026-10-22）：[当前75件基线的两轮CLI](A23_LIVE75_TWO_EPOCH_READY.md)已编译封存。STATUS修正已接入真实入口，绑定597来源、75原件及旧81..112完整消费记录；只允许新范围113..144。19原生场景、6归档拒绝场景、10项专项测试通过；沙箱外context通过，USB打开及真实两轮尚未验证。
新后继namespace、正式记录、保留和消费均未创建；旧592来源和既有证据保持。一次启动脚本已准备，等待新的单次最多两轮授权及当前完全关机/装卡/USB确认，再先WAITING后提示开机。失败即停、不补次、不复用81..112；不继续扩展通用框架或模拟矩阵。以下为此前阶段历史。

独立候选已修正首次两轮实测暴露的软件问题：终态STATUS允许最新报告查询条数为0或1；第二轮前仅忽略该字段在0/1间的变化，其余168字节必须保持。每次STATUS读取后，先保存原始字节、SDK观察和失败字段，再决定是否继续。原587来源、81..112实测及SD原件保持，新加5来源，总计592。

本次是电脑上的软件修正验证，尚未形成绑定75件基线和新序号范围的正式实测CLI；没有发行、消费或追加任何实测。原81..112许可仍耗尽，本次失败及缺失STATUS没有被补造或追认为通过。

## 判定规则

部署候选的GetReportData查询会消耗当前报告，后续空查询把STATUS.report_count覆盖为0，同时保留已匹配URB和ISO7终结结果。因此当前条数不是累计终结条数。

| 条件 | 修正后行为 |
| --- | --- |
| 首次before | 保持原新鲜状态要求，report_count仍须0 |
| 每轮after | report_count允许0或1；大于1仍拒绝 |
| 第二轮before | 只允许report_count在0/1间变化；其余字节与第一轮after完全相同 |
| URB、state、结果、传输量、速度、端点 | 保持原判定；COMPLETE、成功终结、ID匹配、3072字节等均须通过 |
| ISO7 | 保持原terminal/bitmap/actual/context/MFI/TRB类型/SIA/FrameID条件 |
| 第二轮URB | 仍必须区别于首轮 |

原生头文件给出23项after谓词对应的失败字段名。独立Python分析器保留原STATUS/ISO7约束，仅修改条数及第二轮相等比较，并强制验证四份STATUS留证与epoch内容和元数据相同。

## 判断前保存

派生SDK driver在每次readStatus返回后复制该回复，不读活动SDK ISO缓冲区。它在STATUS语义错误、短回复或SDK观察错误触发停止前，将以下文件写入各自的 `status-before-epoch-N` / `status-after-epoch-N`：

- `raw.bin`：收到的原始字节，含短回复；限定保留2048字节以内的NSData，超限或错误类型明确标为未保留。
- `observation.json`：SDK回复观察的JSON副本；不可序列化时保存空对象，并标记 `observation_json_retained=false`，不伪造原观察。
- `verdict.json`：绑定SDK会话、设备身份/描述符、epoch、阶段、原件摘要和具体失败字段；所有物理认证保持false。
- `SHA256SUMS` / `COMMITTED`：沿用原有独占创建、写入读回、fsync和封存顺序。

保存失败立即以 `status_evidence_save_failed` 停止，保留碰撞或部分目录，不覆盖、不重试、不提交下一轮。保存成功但验收失败时，停止原因包含具体字段，例如 `status_validation_failed:transferred`。成功留证也必须存在，独立分析器不能接受缺失、损坏或与epoch脱离的副本。

首次before留证发生在新鲜frame查询之前；after留证发生在已返回STATUS之后。本次仅验证软件顺序及注入预算，没有测量这些文件同步操作在新实机两轮中的延迟影响。

## 验证结果

真实编译并链接派生SDK driver、现有entry及live controller，SDK/IOKit操作使用既有注入provider，没有真实设备对象。最终一次37场景通过，使用AddressSanitizer和UndefinedBehaviorSanitizer：

- 4个成功形态：count始终1、始终0，以及第一轮after到第二轮before的1→0、0→1；均完成两轮共6144字节并通过独立分析。
- 29个STATUS拒绝形态：原23项after字段、错误SDK观察/不可序列化观察/短回复、第二轮before越界条数或其他字节漂移，以及第二轮URB复用。原始STATUS与可序列化观察在失败后仍完整落盘。
- 4个停止形态：before/after目录碰撞、错误载荷、控制超时。before保存失败时ISO提交0，其他首轮失败不进入第二次提交；全部资源保留，SDK destroy0。

3个真实历史成功STATUS原件（lead32首次、repeat1及序号65）不改字节地通过新Python检查，旧解析器均因count0拒绝；序号65原件也通过新的原生谓词。另6个历史坏件对照保持拒绝，4个封存包缺失/损坏/重声明后脱离/第二轮漂移对照保持拒绝。8项专项测试全通过，独立CLI验证count0成功包返回0、缺留证包返回1。

开发版本完整保留：r1、r2因fixture的assert宏逗号及未调用静态辅助函数导致编译失败；r3的37个原生场景完成，但Python消费者拒绝把数字1当作BOOL true。r4显式编码BOOL后通过。开发和最终共4次编译尝试、74个原生注入场景；r1..r3整体不追认通过。专项测试复用最终封存审计，没有再编译或重复运行原生矩阵。

## 封存与后续

| `private/analysis`下材料 | SHA256SUMS摘要 |
| --- | --- |
| `A23-status-capture-revision-review-20261022-r4` | `041eabbb4891cb31257c1959892a6f7de8fdcbd429608d7e116c7be7debbc187` |
| `A23-status-capture-revision-validation-20261022-r4` | `a2cc1e9cdd644e48df2c46db808d1b9f0eb9f12cef7f4a2ab1e8d0b72fcfa3ac` |
| `A23-status-capture-revision-closeout-20261022` | 引用最终与开发包、原实测和卡快照；保存保护摘要、pending及文档快照 |

重查命令：`python3.13 -B tools/audit_a23_status_capture_revision.py --check <review绝对路径>`。新的原生主程序只有注入fixture入口；本页不提供可执行的实测命令。

已确认的软件缺陷不等于已确认[81首轮](A23_LIVE_TWO_EPOCH_FIRST_RESULT.md)的唯一根因：那次完整after仍缺失。真实两轮复用、完整设备日志关联、跨时钟对齐、quiet drain及持续流仍未验证。

下一步最小接线是把此修正纳入绑定当前75件只读基线、已消费shared32历史及新序号候选的实测build，并以原有一次许可/失败停止边界审查。113..144仅是按已有保留范围推导的候选，尚未保留、发行或获新授权。完成接线后，实机对“第二轮真实URB能否完成”有新的信息增量；届时再申请新一次实测，不继续扩展通用进程框架。
