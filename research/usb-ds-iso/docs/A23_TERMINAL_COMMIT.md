# A23 局部终态目录同步与最终 commit 候选（2026-10-21）

后续：[纯磁盘缓存只读恢复分类](A23_TERMINAL_RECOVERY.md)完成554来源、87安排和82测试；不接收事件/观察，完整commit仅关联字节，历史目录同步和wait保持unknown。原发布协议保持。以下保留原阶段。

本阶段新增发布IO、actor候选、纯消费者、审计与测试5个来源，总计551，原546来源逐字节保持。新的actor继续执行冻结requester/worker，状态write_status算法AST与原状态候选相同，局部终态内容仍记录0或91/StatusTransportFailure；改变的是文件发布协议。此前guardian事件管道仪器及生产collector/receiver/permit/原launcher均未改。

协议：

1. 先独占role-terminal-use.json，分段写、file fsync，再fsync job目录。use即使为空或半写也保留，后续同目录重试因O_EXCL拒绝。
2. 每份原始失败frame、transport与exit记录先独占写入.part，分段补齐并file fsync；使用os.link把完整part发布为final，不覆盖已有final，然后fsync job目录。正常actor只有exit记录。
3. 所有记录发布后才构造role-terminal-commit.json清单，绑定job、nonce、terminal/failure plan摘要、role/PID及每个final的SHA256/长度。commit也采用part→file fsync→不可覆盖link→目录fsync。
4. 最后发complete事件并返回。清单的process_wait_verified始终false；它确认的是局部记录关联，不能预言进程此后的退出或wait状态。

候选和IO库分别校验摘要。临时stage的actor槽位映射新候选，guardian槽位仍映射冻结的上一阶段仪器；commit-plan与terminal-plan为同字节兼容别名，外部pin经guardian传入actor。IO库作为单独已校验字节放在临时lib目录。摘要没有提供校验到exec输入的原子绑定或OS隔离认证。

独立事件管道在before记录目标字节，其他窗口记录摘要、长度和写入位置。witness在等待guardian checkpoint时同时读取事件，避免正常路径因事件管道缓冲耗尽而相互等待；上限30事件/65536字节，checkpoint仍有固定期限。它不持有actor控制/状态管道端。到目标窗口的actor通过os._exit(73)自行中断，没有按actor/journal PID发信号。

82种安排为58个进程场景和24个缓存坏件。进程场景包括normal、guardian-loss，以及两角色各28窗口：use的created/half/file_sync/dir_sync，三个记录和commit各before/created/half/file_sync/link/dir_sync。guardian-loss和全部局部中断都先在冻结before-worker-release点终止guardian，触发EPIPE；仅normal允许任务完成。

纯消费者先核对实际guardian wait、actor NOTE_EXIT/ECHILD和固定checkpoint，再核对独立事件、磁盘part前缀、final字节和commit关系。目标字节不会补写缺失缓存。记录final只会缺失或完整，半写状态留在part；use文件可为空或半写，仍封住同目录重试。companion角色必须保留其完整局部发布；是否观察到目录同步只由选中角色事件判断，不能从companion文件存在反推历史同步。

两次回放：

| 观察 | 数量与含义 |
| --- | --- |
| 实际Python进程 | 116 guardian、116 requester、116 worker，共348 |
| guardian直接wait | 116；114次SIGKILL、2次0 |
| actor NOTE_EXIT / witness ECHILD | 232；witness actor waits=0 |
| 创建者已wait actor | 4，来自两次normal |
| actor终止但回收未认证 | 228 |
| 发布中断 / 独立事件 | 112 / 1832 |
| 选中角色有效commit文件 | 12；其中8有commit目录同步观察 |
| 仅link可见、未观察到后续目录同步 | 4 |
| commit目录同步后仍中断 | 4，任务均拒绝 |

目录同步后的commit仍不能证明actor按清单91退出，因为仪器可以在该事件之后再中断。73只是源码与事件中的退出请求；对没有被wait的actor，73和局部91均不能冒认为已认证OS状态。所有故障继续拒绝，旧14个孤儿回收也没有追认，orphan_reaping_verified始终false。

116份guardian-use、attempt与单次accept保持，guardian重试/恢复各拒绝116次。232份local-use中4空、4半写、224完整，本地重试/恢复各拒绝232次，证据字节不变。648对本地part/final、2对正常receipt/part在真实临时目录核对同inode、nlink=2和字节相同，封存复制为独立普通文件。两角色合计128份commit文件有效，但有效commit不带wait权限。局部exit记录中4份声明0、148份声明91，其余尚未发布final；这些是记录内容，不是未wait的实际退出码。

新增30项、原发布回归26项、状态回归26项，共82测试无跳过通过。单元测试另用5个目录检查独占use拒绝覆盖、已有final保持、文件fsync失败不link、记录目录fsync失败不进commit、commit目录fsync失败不发complete，以及短写和零/BOOL/越界进展。同步错误使用mock，已有final触发真实FileExistsError；本轮没有非EPIPE IO错误的真实子进程注入。5个单元目录快照另存，无额外实际进程。

551来源搬移使用独立UUID/nonce/PID，82安排确定性语义一致；正确/错误/缺pin的只读CLI返回0/2/2。纯消费者在open/io.open/waitpid阻断下完成，只读verify在Popen阻断下完成。24个坏件涵盖未wait、伪造creator/witness wait、事件尾部/缺失/绑定/BOOL长度/cut码/缺目录同步、commit缺失或半写/part拼接/角色/记录摘要/wait提升、use缺失/重复资格提升、记录缺失/半写/part拼接、companion commit缺失及事件目标字节/job坏件；保持外部plan pin后全部拒绝。

目录fsync调用成功和进程退出后文件视图不等于断电持久性认证。本轮没有电源故障、witness中断、完整进程树回收或通用OS supervisor证明；同步IO仍无独立中断期限。外部pin是调用方信任输入，不是签名；协调修改outer和checkpoint的guardian PID声明仍可模型完成，来源/物理/生产授权全false。搬移hook仅覆盖Python父回放，不继承到guardian/actor/CLI；不证明OS隔离、原子exec输入或全局nonce防重放。SDK材料仍是历史缓存，真实SDK、clock/timebase、quiet drain和生产permit均未认证。

证据：

- review：`private/analysis/A23-terminal-commit-review-20261021-r1`
- review SHA256SUMS：`b06a9e7477c76d40306b04e432d1e97e13f88ceb0e6471d2d206dd1b6127e417`
- validation：`private/analysis/A23-terminal-commit-validation-20261021-r1`
- closeout：`private/analysis/A23-terminal-commit-closeout-20261021`

只读入口：`tools/audit_a23_terminal_commit.py --check <review> --expected-sha256 <review_pin>`。纯入口：`assess(commit_plan_bytes, plan_pin, job_byte_cache, witness_observation, guardian_checkpoints, actor_exit_notes, publication_events)`。commit-plan/terminal-plan为同字节别名，transport-plan/failure-plan/owned-plan/integrated-plan/launch摘要层级不同，沿用既有路径、节点、字节与普通文件封存限制。recover入口始终拒绝，没有从磁盘缓存重建历史同步或wait的分类器。

23项保护文件、实际49/65账本和失败owner/state保持；65已回收/remaining0，81..112未正式保留。USB/SD/context刷新/driver时钟/原生编译/真实SDK/部署/正式记录/保留/消费/claim均0，生产采集关闭。

下一步离线设计纯磁盘缓存的只读恢复分类，区分残留不完整、commit关联完整或冲突。没有独立事件时，历史目录同步和wait必须保持未知，不重新发布、清理、重启或创建现场票据。

前序：[局部终态发布中断对照](A23_TERMINAL_PUBLICATION.md)。
