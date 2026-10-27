# A23 临时目录只读取样入口（2026-10-21）

后续：[取样独立期限与子进程直接wait](A23_TERMINAL_DEADLINE.md)完成562来源、两轮67安排和82测试。原取样器保持；新监督器提供非阻塞管道与独立IO截止时间，未认证硬实时返回或调用者中断。以下保留原阶段。

本阶段新增取样器、审计与测试3个来源，共557，原554来源逐字节保持。新入口为capture(directory, anchor_bytes, anchor_pin)，只在规范绝对路径/private/tmp的子目录工作；不接生产或硬件卷。原只读恢复分类器、发布IO、actor/guardian、receiver/collector/permit和旧恢复拒绝入口均保持。

取样步骤：

1. 在任何目录打开前验证anchor pin及输入结构，再验证路径。拒绝相对路径、..、非规范路径和/private/tmp以外路径。锚点仍是调用方声明，不是签名或现场进程身份。
2. 从根目录逐级以O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC打开，保留目录句柄与身份链。不用resolve跟随符号链接。
3. 只尝试上一阶段固定18个名字；额外文件不读取。对每个存在的名字先nofollow stat，拒绝非普通文件和超限大小，再以O_RDONLY|O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC相对目录句柄打开，fstat复核类型、身份及元数据。NONBLOCK用于降低FIFO替换窗口的阻塞风险，打开后仍必须立即复核类型。
4. 每文件正文最多8192字节、每轮缓存最多131072字节，正文读取最多32次API调用。每文件先读到EOF，再lseek回头重读；比较正文、读前后fstat和最终名字的nofollow stat。mode、uid/gid、nlink、size、mtime/ctime和dev/ino进入指纹；atime排除，避免自身读取造成漂移。
5. 再完整取一轮，比较包括缺失项在内的文件集、正文与元数据，复核原目录元数据，并重新打开路径身份链对照。任一拒绝抛出错误，不返回部分缓存。
6. 只有全部检查完成才把已取字节交给冻结纯分类器。报告包含当前观察到的文件元数据、数量/字节数及身份链；atomic_directory_snapshot_verified和historical_sync_or_wait_inferred均false。

这是一套有界观察，不是原子目录快照，也不是OS能力隔离。最后一次校验后的变化无法被这次观察排除；真实文件系统调用仍可能阻塞，有限API调用次数不是独立时间期限。只接受/private/tmp路径也不认证内容来源。测试fault hook是受信任的临时目录变更仪器，默认取样路径不写、link、unlink或fsync目标目录。

83种安排包括58份历史文件快照和25个控制场景。五种可返回缓存的控制为：空目录、白名单外symlink、真实hardlink pair、稳定但矛盾的final内容、最终校验后的内容变化。二十种拒绝覆盖白名单symlink/目录/FIFO、root与ancestor symlink、单文件及总量超限、stat/open间替换或FIFO替换、读间修改/截断、打开后增长、FD验证后名字替换、两轮间新增/删除/修改、目录被替换、mock读错误、EINTR预算耗尽和路径策略拒绝。

| 每轮安排结果 | 数量及含义 |
| --- | --- |
| 返回缓存 | 63；9 commit字节关联完整、52不完整、1无残留、1冲突 |
| 拒绝 | 20；没有部分缓存或分类结果 |
| 原58历史快照 | 字节保持；6关联完整、52不完整 |
| 实际fixture进程/fixture job/进程查询 | 全部0 |

取样通过与完整性分类是两个不同结果：稳定的损坏final可以被读到，但仍分类冲突。真实hardlink控制记录两个当前打开对象相同的元数据与nlink=2；纯分类器继续把历史hardlink身份设为unknown。元数据没有进入旧分类器作为历史同步、来源、实际退出或wait证据；任务、清理、重启与物理权限全部false。

关键负对照在validated检查点之后改变target。两轮独立目录控制均显示：返回缓存仍是原字节，可得到commit_associated；harness随后观察到target的实际摘要已不同。缓存正确保存了取到的字节，却不能证明返回时目录仍相同，atomic_directory_snapshot_verified保持false。这个控制没有重新发布或修复目标，也没有升级任务完成。

新30项、恢复分类回归26项、发布回归26项，共82测试无跳过通过。除全套控制外，单元测试检查所有open为只读/nofollow且无create/truncate，阻断write/link/unlink/fsync仍可取样；模拟读错误后所有已打开句柄完成close；短读和首次EINTR可在预算内继续；真实close完成后再注入错误时拒绝，并继续清理其余句柄。单元测试另用4个目录，无额外fixture进程。

557来源搬移使用相同58个历史UUID/nonce与锚点/文件字节。两次83安排的归一语义一致，真实inode与时间保存在各自报告，不要求跨位置相等。目录变化的directory_changed/directory_path_changed归为同一拒绝组，实际错误码另存。verify和exercise阻断Popen，正确/错误/缺pin的只读CLI返回0/2/2；verify在取样函数被阻断时仍可重验封存，不再次接触旧临时目录。

两轮共166个离线文件case上下文，另4个单元上下文。它们只复制历史模型材料并注入文件变化，没有新现场job、进程fixture、进程查询、原生编译或SDK执行。拒绝案例里的FIFO、目录和symlink留在临时测试上下文，不复制进封存包；封存只保存普通文件的输出、接受缓存及报告。三次只读CLI为普通Python检查，不是fixture执行。

边界仍保留：外部anchor pin是信任输入，协调重pin的来源声明不能因此认证；当前观察没有认证目录原子性、持续稳定、断电持久性、全局nonce、原子exec输入或OS隔离。最后检查到返回之间仍有窗口，同步读取没有独立wall-clock deadline。搬移hook仅覆盖Python父回放，不继承到只读CLI。旧228个actor和旧14个孤儿回收未认证结论不变，orphan_reaping_verified始终false；真实SDK、clock/timebase、quiet drain与生产permit均未认证。

证据：

- review：`private/analysis/A23-terminal-intake-review-20261021-r1`
- review SHA256SUMS：`39abf3216cb012e2578074564484e43ad6421c218c033a3bcee33a9dc4c5a577`
- validation：`private/analysis/A23-terminal-intake-validation-20261021-r1`
- closeout：`private/analysis/A23-terminal-intake-closeout-20261021`

只读入口：`tools/audit_a23_terminal_intake.py --check <review> --expected-sha256 <review_pin>`。取样API：`capture(directory, anchor_bytes, anchor_pin)`返回缓存、观察报告和原纯分类结果；异常不返回部分缓存。没有生产入口。

23项保护文件、实际49/65账本和失败owner/state保持；65已回收/remaining0，81..112未正式保留。USB/SD/context刷新/driver时钟/原生编译/真实SDK/部署/正式记录/保留/消费/claim均0，生产采集关闭。

下一步离线覆盖取样阻塞与独立期限。如使用子进程，调用者必须直接持有实际句柄，并分别记录期限到期、终止和wait；不能按journal PID清理，不能把超时升级为成功或已回收，不接硬件卷或生产入口。

前序：[纯磁盘缓存只读恢复分类](A23_TERMINAL_RECOVERY.md)。
