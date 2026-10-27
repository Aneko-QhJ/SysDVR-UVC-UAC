# 当前97件基线的固定三轮候选（2026-10-23）

完整三轮主机入口已编译封存：当前97件原件、623来源、49..176完整消费历史与三个旧namespace进入校验；新scope只允许177..224，最多三轮。原生固定48许可、三组失败owner快照、STATUS判断前留证、checked export双边复核与接受回执及独立收集器均已接入。当前没有新授权、正式namespace、实际once记录或范围保留；等待新的单次最多三轮授权及当前设备状态确认。

新增4来源，总623，旧619逐字节保持：`tools/build_a23_live97_three.py`、`tools/a23_live97_three_workflow.py`、`tools/audit_a23_live97_three.py`、`tests/test_a23_live97_three.py`。生成文件写入新build，旧实测程序、部署、源码闭包和已耗尽票据不改；读取复用候选保持暂停。

## 新构建与证据绑定

97件基线为`private/card-cycles/20261023-live91-first-read`，其完整99项封存清单和只读回收/弹出回执重新核验。四项部署、device binding与recipe沿用当前已部署版本，未编译或写入新固件。完整49..176消费历史由旧记录与81/113/145三个原namespace继承；旧145仍耗尽。新固定48范围独立采用shared48与three-entry schema，不将48段写入旧shared32 namespace。

新build的原生scope和Python scope逐项一致，来源、基线、恢复索引、历史及job在原有明确边界重新核对。新增spent145整树的内容变化、增加和缺失都在下次提交前拒绝；不跨轮缓存来源新鲜度。新driver和Triple SDK lease沿用[三轮核心](A23_THREE_EPOCH_OFFLINE.md)的三组存储、回调状态、前轮STATUS比较和全部历史URB去重。

entry接受固定177..224绑定；原生许可核对48段保留、消费和本次process/SDK claim。controller可导出三组已有owner快照，失败时不重读活跃SDK缓冲区。正常导出先复核、保存载荷，再复核文件与快照，最后保存接受回执；独立收集器同时验证三轮SDK/entry链和接受回执。此协议不证明最后一次检查后的永久新鲜度或回调排空。

## 接线验证

最终23个原生场景均exit0并由创建者直接wait，fixture启用ASan/UBSan且stderr为空；另7项专项检查通过。实际CLI仅执行describe、archive/current文件检查及不存在job的拒绝，不创建SDK对象或访问USB。

| 检查 | 观察 |
| --- | --- |
| 正常及排队延迟 | 三轮177..192、193..208、209..224，9216正确字节、三URB、六次STATUS，entry与双边回执均通过；注入SDK时钟不能按真实时钟接受 |
| 首轮/第三轮STATUS失败 | 分别止于1/3次提交；失败STATUS留证，不补轮 |
| 第三轮STATUS留证冲突 | 停止，保留三组owner已有快照及live-failure；不产生接受回执 |
| 第三轮前来源变化 | 止于两轮，第三轮不提交 |
| 来源/基线/spent145变化、增加、缺失 | 首次ISO前拒绝 |
| 旧32 schema、32宽度scope、count32保留 | 原生许可在打开SDK前拒绝 |
| 坏封存来源、历史、生成器或binary | 初始文件检查拒绝，无SDK打开 |
| pending时退出 | 跳过完整哈希，一次异步abort，失败后保留资源 |
| 载荷写后变化、来源变化或接受回执冲突 | 无有效接受回执，controller失败 |
| 接受回执生成后再改载荷 | controller已历史成功，但独立收集器拒绝，不升级为有效采集 |
| 重复consume、其他job接管 | 两条正常路径均拒绝，拒绝未改变namespace；缺授权issue拒绝 |

两个注入正常路径的导出前/后最后完整检查为10/11次，不能将总检查次数当作轮间次数或实机性能。最终正常路径的单次完整检查约0.49秒；这是本地ASan注入过程，未测真实三轮节奏。

r1的19场景和5项初始检查已通过并保留；r2增加错误许可宽度/计数、缺失历史、重放和收集器反例后，23场景/7项通过。两个版本共4个编译作业、42个fixture进程均由创建者wait；8个原生文件检查模式均按0/2预期退出。没有实机采集、部署或正式保留操作。

## 环境与一次启动计划

最终binary在沙箱外只读`--inspect-context`检查通过：OS26A434、arm64、指定IOUSBHost框架UUID匹配，sandbox查询0；原始stdout/stderr已封存。最初沙箱内检查返回policy false；随后一次只读检查通过，再执行一次以保存原始输出。环境检查不是USB打开权限或硬件成功证明，实际启动仍会重核当前上下文。

一次启动计划为`private/analysis/A23-live97-three-launch-plan-20261023-r2/`。外层启动器固定最终build/receiver摘要，执行需要新的人类授权回执明确最多三轮、177..224和本次关机/装卡/USB就绪；授权文件、actual record和新namespace目前均不存在。无参数仅展示计划；缺授权的execute返回2，未创建记录或namespace。初版计划准备器在保存review子进程元数据时参数数量错误，未调用execute；失败版本封存。修正版review/缺授权两个子进程均直接wait，返回0/2。

授权后的顺序：保持完全关机并装回SD、连接USB，先启动接收器；只有实际报告WAITING后才提示开机CFW。一次最多三轮，任意失败即停，不补轮、不重试，首轮失败也不能复用剩余序号。失败有未决SDK资源时继续由创建者持有；只有用户明确确认Switch完全关机后，才通过现有receipt/保留对象完成正常失败退出和直接wait，不按磁盘PID恢复控制权。

实测停止后还需单独只读回收设备trace/生命周期，关联六次STATUS和三次BURST，核验无容量拒绝、丢失或无效记录。按旧形状三轮预计216/256条trace、19/32身份；额外枚举、其他请求、实际窗口与SDK时序仍可能改变结果。没有原件就保持不可判定，不将主机正确字节追认为设备关联完整。

当前仅准备完成，三轮真实SDK调用、实际节奏、设备容量与30秒窗口覆盖尚未实测；持续流、长期稳定、UAC/视频共存、quiet drain、跨时钟及旧失败根因均未验证。177..224未保留，remaining0，SD最后记录为已弹出，当前实机状态未确认。

## 封存索引

以下相对`private/analysis`，摘要为SHA256SUMS的SHA256。

| 材料 | 摘要 |
| --- | --- |
| `A23-live97-three-review-20261023-r2` | `d9507f2efdae4b66980af33667f46b25d4446e8961901670313031346f5f8067` |
| `A23-live97-three-review-20261023-r1` | `3e3fd90ded5a13d080324db4a8c58a49de474a09b7e69fb260d047c88de0ecbb` |
| `A23-live97-three-validation-20261023-r1` | `ac920b8a27cb06d31f563a0cfeb2c2ed725fa2e17acde2d4f8f5c8949749582a` |
| `A23-live97-three-context-20261023-r1` | `96f7900fdd33c8818c00823d8db0f5f5143f873c216757ecf7fcf4f3d884dc58` |
| `A23-live97-three-launch-plan-20261023-r2` | `c755737a294868fdc3ace74c26363adf965370398a5cbad353461e7fed61722d` |

最终来源、旧保护项、票据和文档快照保存在`A23-live97-three-closeout-20261023`。来源与权限状态以本次closeout及实际票据为准，前文历史阶段的“未实现/待接线”不再代表当前候选。
