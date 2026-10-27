# A23 纯磁盘缓存只读恢复分类（2026-10-21）

后续：[临时目录只读取样入口](A23_TERMINAL_INTAKE.md)完成557来源、83安排和82测试。候选使用固定白名单、NOFOLLOW与两轮观察；仍不声称目录原子性，原纯分类器保持。以下保留原阶段。

本阶段新增纯消费者、审计与测试3个来源，共554，原551来源逐字节保持。复用上一阶段58个封存job的历史UUID、nonce、PID声明和局部发布文件；没有创建新fixture进程或job，没有查询进程。发布IO、actor/guardian仪器、无条件拒绝的recover入口和生产receiver/collector/permit均保持。

接口为classify(anchor_bytes, anchor_pin, local_file_cache)。anchor是调用方给定的job/nonce、terminal/failure/owned-plan摘要及两actor PID声明，外部pin是信任输入，不是签名或进程句柄。anchor没有scenario，也没有期望完成或同步状态。文件缓存仅允许两角色各9个固定名字（use、三记录final/part、commit final/part），单文件最多8192字节、总计最多131072字节；路径穿越、额外文件、非bytes或超限输入直接拒绝。不会按manifest里的名字打开文件。

审计从旧sealed review中取锚点声明及白名单文件，去掉事件、退出通知、内层报告、原场景plan等。新输入保留terminal/failure等摘要，不把包含场景的plan内容交给分类器。原始快照目录名称只用于审计索引，纯函数不接收它。source provenance保存旧同步/wait观察仅供外部对照，不进入分类函数。

分类含义：

| 分类 | 含义 |
| --- | --- |
| absent | 两角色白名单中均没有残留；不代表可以重新运行 |
| incomplete | 有残留，但没有两角色完整且一致的final commit关联 |
| commit_associated | 两角色use、记录final/part与commit final/part的字节、声明和摘要一致；仅为字节关联 |
| conflict | 完整发布声明、锚点、记录关系、必要use或保留part存在可检出的矛盾 |

每角色也分别分类。全局只有两角色都关联完整才输出commit_associated；任一冲突则全局冲突。use的已知合法前缀可保留为空/半写，若后续记录已存在却use不完整则冲突。完整exit只接受原本的0/None或91/StatusTransportFailure声明，失败frame与transport绑定job/nonce/plan/角色及摘要；失败文件和成功exit同时存在会冲突。final必须有相同字节的保留part，完整commit必须绑定所有声明记录。

无法解析的frame/commit part可能只是尚未写完；单靠这些字节无法判断来源或合法性，因此保留opaque_partial_files并分类不完整，不把它们认证为合法发布前缀。完整final无法解析或完整结构绑定冲突则拒绝关联。这里的不完整不表示“内容已验证无误”，也没有修复、补写、重发布、清理或重启分支。事件中的目标字节完全不参与恢复分类。

87安排包括58原始快照、5个边界对照（空缓存、缺一角色、commit part完整但未link、仅空use、无法解释的frame part）及24个冲突坏件。原始58快照中6个全局关联完整、52个不完整；角色级为64关联完整、52不完整。加上对照和坏件后为1 absent、56 incomplete、6 commit_associated、24 conflict。所有结果task_complete=false，恢复/清理/重启和物理授权全false。

所有87结果的directory_sync_status、actor_wait_status、actual_process_exit_status和hardlink_identity_status都为unknown。真实旧观察显示commit-link与commit-dir_sync分别没有/有选中目录同步事件，但两者磁盘分类都只能关联字节；normal曾有两个创建者wait，guardian-loss没有，但两者也只能输出wait未知。记录中的declared_exit_code仅保留声明，不替代OS状态。缓存final/part字节相同不证明它们仍是同inode，不能从字节恢复硬链接身份。

24坏件覆盖缺失/改写/空use与后续记录矛盾，frame job/PID改写后协调重算transport和commit摘要，exit BOOL PID/nonce/成功提升/异常拼接，transport errno/送达/wait冒认，commit job/BOOL PID/wait/记录摘要/路径/BOOL长度/角色，record或commit part缺失/拼接、final记录缺失，以及完整commit不可解析。它们保持原外部anchor pin，均分类冲突。

负对照协调修改外部anchor中的PID声明，再重建use/exit/commit并重pin，可得到commit_associated。它只说明调用方提供的字节与声明一致，record_source_authenticated仍false、task_complete仍false、wait仍unknown，所有物理权限保持false。不能把该控制当作现场进程来源认证。

新26项、commit回归30项、发布回归26项，共82测试无跳过通过。纯消费者在open/io.open/os.open/stat/waitpid/kill/Popen阻断下分析缓存；只读verify在Popen阻断下完成。554来源搬移后输入锚点与文件逐字节相同，历史UUID/nonce保持，87安排确定性语义一致；搬移verify与exercise也阻断Popen，正确/错误/缺pin的只读CLI返回0/2/2。这里重放的是同一历史缓存，没有新的独立硬件运行或新UUID。

本轮fixture进程、fixture job、进程查询均0；另有5个回归单元目录用于已有发布IO mock错误/真实已有final拒绝测试，快照随validation保存。只读CLI本身有3次Python检查进程，不是fixture或硬件执行。旧228个actor和旧14个孤儿回收未认证结论没有变化，orphan_reaping_verified始终false。

当前接口接收调用方已形成的静态字节缓存，还没有面向可变现场目录的取样入口；它不认证收集时的原子目录视图、来源、断电持久性、OS隔离、原子exec输入或全局nonce防重放。搬移hook仅覆盖Python父回放，不继承到只读CLI。没有新SDK、clock/timebase、quiet drain或生产permit认证。

证据：

- review：`private/analysis/A23-terminal-recovery-review-20261021-r1`
- review SHA256SUMS：`bb43317f79a07c686c7278edcbf83ae27f44ccce10ec9a34695b586bb7d2d0fe`
- validation：`private/analysis/A23-terminal-recovery-validation-20261021-r1`
- closeout：`private/analysis/A23-terminal-recovery-closeout-20261021`

只读入口：`tools/audit_a23_terminal_recovery.py --check <review> --expected-sha256 <review_pin>`。纯入口：`classify(anchor_bytes, anchor_pin, local_file_cache)`；review pin、anchor pin和原terminal/failure/owned-plan摘要含义不同。没有生产恢复入口。

23项保护文件、实际49/65账本和失败owner/state保持；65已回收/remaining0，81..112未正式保留。USB/SD/context刷新/driver时钟/原生编译/真实SDK/部署/正式记录/保留/消费/claim均0，生产采集关闭。

下一步离线设计固定白名单的只读目录取样入口，拒绝symlink/非普通文件，限制读取并检测读前后身份/内容变化；仍不声称原子目录快照，不读取硬件卷，不重发布、清理、重启或创建现场票据。

前序：[目录同步与最终commit候选](A23_TERMINAL_COMMIT.md)。
