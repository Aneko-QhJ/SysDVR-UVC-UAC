# A23 隔离候选的落盘与停止窗口（2026-10-13）

后续[控制buffer与退出审查](A23_CONTROL_BUFFER_CLEANUP.md)确认：最终排空不排除此前复用，原样__appExit未受正常路径门槛保护；本页保留该阶段实现与验证记录。

[实际 handler 候选](A23_EP0_HANDLER_CANDIDATE.md)的隔离副本现增加一次性文件 sink，及默认
关闭的本地停止窗口。21 个 native 文件接口场景、16 份封存 capture 的 80 次文件回放和
11 个窗口算术/边界检查通过 ASan/UBSan。默认关闭与 30 秒样例各完整链接 7 对象 libnx
ELF；均未执行、打包或部署。275 项相关 Python 回归无跳过。

生产源码、USB 协议/timeout、部署及三份凭据不变；本轮 USB/SD 访问为 0，remaining=0，
根因未知。native 只模拟文件服务与身份/join；真实 SD 行为、持久性和停止延迟尚未验证。

## 一次性落盘流程

[ep0_candidate_file.c](../device/ep0_candidate_file.c)调用真实 libnx ABI，但只在隔离 ELF
中编译。main 在视频/音频线程 join 成功、exporter 身份取得且 Finish 放行后调用一次；
API 再核对内存 capture 存在、joined/stopped、fault=0、pending=0。未交接/占用未知时不调用
任何文件系统接口，不把冻结、timeout、cancel 或连接关闭当作排空。

文件名为 `/ep0-<process nonce><session nonce>.capture.bin`，使用两组各 16 bytes nonce，
不是已认证的系统 boot ID。先独立打开 SD filesystem，CreateFile 后才 OpenFile；已有文件
或创建错误不走删除、截断、open-existing 或覆盖回退。创建/open 的失败也可能留文件，
状态保留 file_may_exist。本机模型验证碰撞不会写旧内容；真实 HOS 的创建冲突行为未实测。

[ep0_candidate_sink.h](../device/ep0_candidate_sink.h)按以下次序执行，输入最大 6640 bytes：

1. 一次性预分配文件并打开，写入完整不可变 capture，然后 flush。
2. GetSize 必须与 capture 长度相同；按最多 256 bytes 的块读回，逐字节比较全部内容。
3. 成功短读允许前进；零读、超出请求长度、错误或不一致均失败。每次 read 的 count 先置零，
   失败输出不使用。libnx Write 不返回字节数，预分配 size 相同也不能排除静默短写。
4. 文件 close 后调用 FsCommit；只有 Result 成功才设置 commit_acknowledged。

文件名从创建开始可见，没有 rename/发布标记、原子发布或断电持久性承诺。即使内容完整且
decoder 通过，commit 仍可能失败；磁盘上的 capture 本身无法证明 commit 曾返回成功。
content_verified、commit_acknowledged、phase、Result、verified_bytes 分别保存在内存状态。
失败既不删除部分文件，也不重写、重试或丢弃冻结内存。失败时正常退出 main 保留其余资源
并 sleep；文件/FS handle 按已成功打开的范围关闭。Core 仍负责 fsInitialize/fsExit。

该实现没有新增 USB 查询，也不使用 FS 成功替代 HOS URB 所有权证明。异常退出、外部进程
改文件、实际卡故障、供电中断和 runtime 来源认证仍未验证。

## 本地停止窗口

[ep0_candidate_window.h](../device/ep0_candidate_window.h)在视频 owner 初始化后取起始 tick，
配置单位为 ms，0 关闭，算术支持最多 60000 ms。tick 频率必须非零；转换向上取整，并检查
乘加溢出。初始化不能重做；到期不可撤销。回退/回绕 tick 也触发停止，不能无限延长窗口。

生成的 main 只在原有 WaitReady 返回或整个 ProcessRequests 返回后检查到期，并设置现有
atomic stop API。不会截断 helper、强制冻结 processing、cancel URB 或添加报告查询。
持续请求/同步调用可能拖延边界，**30 秒是请求停止的阈值，不是已经验证的停止上限**。
128 条 trace 仍保留最早记录，窗口不重置 trace/账本，槽容量仍为 16 个会话身份。

[build_a23_trace_sink.py](../tools/build_a23_trace_sink.py)只生成默认关闭和 30000 ms 两个
电脑编译样例，没有执行或部署入口。每个样例有单独配置 recipe digest，再写入实际候选
Start 所读的 header；配置与 ELF SHA256 关联，但不认证运行来源。本轮没有启用实机窗口
或签发硬件次数。只有保存完整 capture 后的正常路径才继续原资源关闭。

## 检查与封存

[ep0_candidate_sink_test.c](../tests/ep0_candidate_sink_test.c)编译实际 candidate runtime、
实际文件 adapter 与 portable sink，仅将 Fs 接口替换为 modeled ABI；writer/exporter、
join、文件故障及 nonce 都是注入。21 场景覆盖正常/短读、FS open、create/碰撞、file open、
write/静默短写/损坏、flush/size、短/多 size、read/零/超长 count、commit，及缺 Finish、
pending、fault、失败 join；检查重复调用无新 IO、内存不变与合法 handle 关闭。

16 份上一阶段有效 capture 各在正常、短读、静默短写、第二块 read 失败、commit 失败下
回放，共 80 次。正常/短读/commit-failed 文件与输入逐字节相同并独立解码；迟到 read 错误
保留已核验前 256 bytes。它们是旧 native capture 的 sink 回放，不是新 ARM ELF 产生的
记录，也不把旧 recipe 改标成新 recipe。调试 sink 输入路径明确标记 debug_sink_input。

[Python 检查](../tests/test_a23_trace_sink.py)包含 9 项语义检查（含 native 与封存 ARM runtime 源码漂移拒绝）；11 个窗口场景覆盖默认关闭、
临界 tick、向上取整、频率/范围/溢出、不可重设、回退/回绕及空指针。实际 main 的线程与
调度未 native 执行；只核验唯一源码插入点、join→Finish→save→close 顺序及 SDK 完整链接。

- `private/analysis/A23-EP0-candidate-sink-review-20261013-final`：native 输出、80 次回放、完整两份
  source/ELF/object/map、总 recipe、各配置 recipe、audit 与 SHA256SUMS。旧 handler review
  417 项清单作为只读输入核验，不原地重建。无 final 的初步 sink review 保留，交付以 final 为准。
- `private/analysis/A23-EP0-candidate-sink-validation-20261013`：源码快照、275 项回归、旧证据/
  三份凭据/生产 hash/链接核验与独立 validation。所有 ARM ELF 都只编译，从未执行。

下一步电脑审查 timeout 后原共享 control buffer 的实际复用，及正常/异常退出资源路径。
账本只控制记录导出，没有修复共享 buffer 的未知 DMA 占用；还不能准备实机部署结论。
实际接口 2 setup、速度/post/ACK 的观察与开销仍缺失，seq0 的根因未确认。
