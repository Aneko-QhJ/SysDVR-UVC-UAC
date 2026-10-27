# A23 fixture 中断发布与恢复拒绝（2026-10-21）

后续：[同步发布接入新离线fixture launcher](A23_INTEGRATED_FIXTURE.md)完成523来源、51安排和64测试；父同步后启动固定child，联合发布与清理准入。仅新离线副本接入，生产与旧launcher不变，父自身中断/断电/全局防重放未认证。以下保留原阶段。

本阶段新增5个来源：文件发布候选、纯字节恢复分析、固定中断worker、audit、tests，总计517，原512来源保持。验证的是临时目录中 attempt 和 receipt 的发布协议；既有 fixture launcher、生产 collector/permit、driver/桥/C 代码均未修改，候选尚未接入 launcher。

发布顺序为：

1. 独占创建 attempt，分两段写入，fsync 文件、关闭、fsync job 目录和其父目录。
2. 记录 fixture 的 payload 屏障，再复制历史 SDK 模型材料，fsync 各材料文件和从内向外的目录。
3. 独占创建 receipt.json.part，分两段写入，fsync 文件并关闭。
4. 通过同目录 os.link 将完整临时文件发布为 receipt.json；已有目标会拒绝，不能覆盖。随后 fsync result 目录，再输出绑定的 stdout report。

临时名保留作为证据。原位置和搬移回放的实际临时目录共有10对已发布 receipt/part，均核对同设备、同 inode、nlink=2和字节相同；封存副本是两个独立普通文件。纯消费者比较字节，不认证历史 inode 身份或现场文件来源。

固定 worker 校验自身源码、发布模块和 launch 摘要，所有工作仅在 `/private/tmp` 下的新 job 中进行。新增 publication-plan 包含 launch 摘要、模块摘要及明确的 cut_after/fail_before，外部必须提供 plan pin。launch 仍携带独立 UUID、随机 nonce 和历史材料清单；新的 report/receipt 绑定本次 fixture 的 launch/attempt/stdout，而嵌套 SDK receipt/epoch/snapshot 始终是 `historical_model_cache`。

43种安排首轮通过：

- normal：完整协议、退出0和 stdout/receipt/材料关联均通过，允许模型完成。
- 18个步骤后中断：从开始、attempt 创建/半写/全写/fsync/关闭/目录同步、payload 屏障、材料同步，到 receipt 临时文件创建/半写/全写/fsync/关闭/发布/目录同步及 stdout 输出；固定子进程在记录步骤后 os._exit(73)。
- 8个步骤前模拟IO失败：attempt 创建、文件同步、job/父目录同步、材料同步、receipt 文件同步、发布与目录同步；错误返回74。这是明确注入的 OSError，不冒充操作系统自行发生的故障。
- 16种纯字节坏件：缺失/乱序/拼接/额外 trace，缺失/BOOL计数/半写 attempt，缺失/不一致 part，缺失/错误job/授权升级的 receipt，缺stdout/材料，未回收或BOOL returncode。保持原 plan pin 后均拒绝。

仅 normal 允许 `publication_model_complete=true`。stdout 已完整输出、receipt 也完整匹配的末端中断仍因退出73拒绝；receipt 已发布但目录同步失败同样不能完成。空/半写/完整的 attempt 都占用原名；两次回放共50次直接重建 attempt 被 O_EXCL 拒绝，字节证据保持。4份开始前或创建前中断/失败未留下 marker，恢复入口依然拒绝。

恢复入口 `recover(job)` 没有文件写入或启动逻辑，始终拒绝恢复运行；纯分析结果的 restart_allowed、automatic_repair_allowed、生产与硬件许可均为 false。marker 尚未创建时，直接绕过恢复入口调用发布器仍可能开始；删除/复制目录也不由此协议阻止。因此这只是保留证据目录上的恢复拒绝接口和独占创建规则，不是 OS 能力隔离或全局 nonce 防重放。

验证：新增22项、前阶段 fixture job 绑定回归20项和 job/receipt 关联回归20项，共62测试无跳过通过。额外检查真实文件API返回 fsync OSError 时保留 attempt 且不进入 payload、短写补全/零进展拒绝、receipt 发布前出现同名目标时原内容不被覆盖。纯消费者在 open/io.open 阻断下分析全部27份缓存；只读 verify 在 Popen 阻断下完成。

517来源搬移后以独立 UUID/nonce 重跑，43安排的语义、恢复拒绝与固定代码摘要一致；只读CLI正确/错误/缺pin返回0/2/2。两次共54个实际 Python publication worker 均由审计 harness 回收，其中36次固定中断、16次注入失败、2次正常退出；没有救援、后代进程、原生编译、完整driver或SDK执行。这些进程由测试 harness 启动，不是发布候选或原 launcher 的运行证明。单元测试另有临时文件操作、前阶段模拟双线程争用，不产生额外实际子进程。

必须保留的限制：

- 实验是进程退出后读取当前文件系统的结果，没有切断电源或重启文件系统。fsync 返回和源码规定的顺序不等于真实断电、磁盘控制器缓存、所有文件系统或故障调度的持久性证明。
- 上游 launch/输入生成的持久发行协议不在本阶段；trace 本身也没有持久日志协议。实际来源、校验到 exec/child 读取的原子绑定、真实 SDK/时钟域/quiet drain 和生产许可仍未认证。
- trace 是固定 fixture 自报的调用顺序，外部 plan pin 是调用方信任输入。负对照把末端中断的 plan 改成 normal、重新给 pin，并将外层退出73改为0，可再次得到模型完成；物理来源、断电恢复和所有生产标志仍为false。
- 同一 launch/nonce 复制到无 marker 的其他目录仍不保证唯一性；前阶段已封存的复制负对照保持有效，本阶段不宣称修复。
- 发布层接受调用方提供的字节，语义检查由 worker/纯消费者承担。部分写入、staging 名和已有目标均保留，不自动删除、修补或重新执行。
- 搬移 hook 对原checkout及/Volumes的文件打开观察0，仅作用于父回放Python，不继承到worker/CLI，也不构成OS隔离。

证据：

- review：`private/analysis/A23-fixture-publication-review-20261021-r1`
- review SHA256SUMS：`466e99d97542f40db2238e935da660d5c89e86b83a7ebcd0d1f4a9d3bf28b860`
- validation：`private/analysis/A23-fixture-publication-validation-20261021-r1`
- closeout：`private/analysis/A23-fixture-publication-closeout-20261021`

只读入口：`tools/audit_a23_fixture_publication.py --check <review> --expected-sha256 <review_pin>`；单case纯消费者为 `assess(plan_bytes, plan_pin, job_byte_cache, stdout, stderr, observation)`。review、publication plan、launch三层摘要不可互换。沿用8192节点及既有单文件/总量/路径/普通文件封存限制。

23项保护文件、实际49/65账本及失败修复owner/state保持；65已回收、remaining0，81..112未正式保留。USB/SD/真实SDK/context刷新/driver时钟/部署/正式发行保留/授权消费/permit claim均0，生产采集关闭。

下一步在新的离线 fixture launcher 副本中接入本发布协议，组合验证启动前同步失败、子进程异常退出、结果发布中断与父进程收集/清理；继续拒绝生产接入和实际硬件执行。

前序：[fixture 启动前绑定与退出后关联](A23_FIXTURE_JOB_BINDING.md)。
