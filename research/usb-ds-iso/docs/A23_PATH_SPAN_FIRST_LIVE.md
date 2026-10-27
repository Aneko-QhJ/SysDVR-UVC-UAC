# 路径缓冲候选首次测试（2026-10-17，Asia/Shanghai）

用户明确要求“开始测试”后，核验 233 项来源、旧记录、第 5 代接收器、新包及真实部署/弹出回执，签发并消费唯一一次新记录。主机 WAITING 先于新的 HS 到达，用户随后确认“已开机”；执行一次请求链，无自动重试。

后续离线定位见[ISO错误保留与窗口审查](A23_ISO_RETENTION_WINDOW.md)：首TD CC23及条件窗口错位已从原始STATUS重核，未新增实机测试。

## 主机结果

本地 23:22:11 启动，run 的 UTC 标识为 `20261016-152211`。控制约 **0.390292 ms** 完成，ISO 约 **183.346958 ms** 回调，无超时、无 abort，资源关闭、进程退出 0。但 **960 项 actual 全为 0，184320 字节缓冲全零**；STATUS 从 seq0/state0 变为 seq1/state4（RETAINED），requested3072 / transferred0 / urb_status2。

结果为 **failed_no_retry / remaining=0**。回调状态和退出码为 0 不等于 USB 载荷验收；没有恢复次数或再次触发请求。

主机证据：`private/runs/A-A23-path-span-waiting-20261016-152211-7e95b3a8`，18 条封存。独立主机分析：`private/analysis/A23-path-span-first-live-host-20261016`，保存原始 STATUS、已消费记录快照、保护检查及部署状态前后快照，manifest `b3b5cb8bcc8393aae0fd23552a6e4d907a8cf1785e4f6f2877009490cdf023e8`。

## 设备原件回收与新结论

2026-10-17 初次接卡未识别到磁盘，入口在识别前停止；连接检查已封存。用户随后确认磁盘工具能看到 SWITCH SD 卷，动态识别 UUID `37614F76-3E12-3470-B5C8-52B5A449C213` 后只读回收 **38 个选取原件**，00:21:19+08 安全弹出。四项部署文件匹配新包。与部署前34原件相比新增 diagnostic、EXE3 和两份 LCP1；原有文件仅 NSP（部署的预期替换）和 logfile.txt 有变化，无删除，两份旧 LCP1 字节保持。

| 观察 | 本次结果 | 能支持的结论 |
| --- | --- | --- |
| diagnostic / EXE3 | 4400 / 5456 字节；外置与内嵌 primary 完全一致 | 已取得可解码材料 |
| 两次 file_create | 均返回0；保存返回true，phase9/result0；EXE3内primary收据声明读回、commit确认 | 本次两处未再出现0xD401；尚不足以认证其内核根因 |
| 启动journal | 44条，API均返回0 | 报告的启动链无失败记录 |
| 接口2触发 | SETUP `4154010002000000`，seq1，ISO post返回0，3072字节/id387 | 记录显示请求进入处理并成功提交 |
| 控制ACK | 返回0，约0.120573ms | 本次记录的处理路径完成ACK |
| 窗口结束 | 30秒到期；ISO channel8/id387/status2/active，pending1 | 按冻结的所有权策略仍未终结，拒绝释放；未证明内核状态含义或停滞原因 |
| 所有权检查 | fault=false，guard_denials0、unmatched_reports0、failed_posts0 | 诊断中无对应拒绝/故障记录，ISO缓冲仍保留 |

据此，本次失败的研究重点转到 **ISO端点提交之后的完成报告与实际传输**。不能继续把“接口2没有收到触发”或“本次两处文件创建失败”作为解释。也不能由相同SETUP出现在其他接口推出总线覆盖。

## 多文件关联与边界

四份 LCP1 原件全部保留，没有自动挑选或删除。`ep0-life-3ec99255973181076289cd05fa4b4a53.bin` 有27条，joined_context 的 boot/session 与 EXE3 一致，writer/时钟条件也相符；仅据这些内容显式建立关联。`ep0-life-322a12589c9c8608a23f63fb868604ee.bin` 仅有4条启动记录，无 joined_context，不能归到同次执行，也不能据此推断用户开机次数。另两份为部署前已存在的旧recipe文件。

全文件 collection 保留多文件歧义；另一个 collection 仅供显式上下文关联比较，选择依据见分析包 `explicit-selection.json`。两包 binding/执行内容比较自洽、无分析错误；关联包 lifecycle context/tail 检查通过，但 **supplied_chain_complete 仍为false**，因为主机 `host_observation_complete=false`。不修改判读器以消除这一限制。

trace 84/256条，无丢弃/非法记录，但 `trace_window_complete=false`：只保存静默轮询计数与最后返回值，没有完整时间和返回历史。启动、保存及join结果是设备自报告，不能独立认证物理同次执行、完整STATUS绑定、日志自身commit或跨时钟对齐。所有 hardware/root_cause/usb_strict_pass/cleanup/allow_next_burst 认证保持false。

## 封存与续接

| 材料 | 条目 | SHA256SUMS 摘要 |
| --- | ---: | --- |
| `private/card-cycles/20261016-232422-path-span-first-live-read` | 40 | `f68eeffba5f609afb099a249b218e83634a0e32bda2ce1f8fe1a4187bc7da919` |
| `private/analysis/A23-path-span-first-live-recovery-20261016-232422` | 6 | `1c13d25a74c18f47cfcf1ff1f457bc00f59489edafd5d0af4042c2433ca6071c` |
| `private/collections/A23-path-span-first-live-20261017-all` | 33 | `7c56352a4844ad521da5b57e176e4b7ebb4f6e57182419049bc6938ab5d7d9ca` |
| `private/collections/A23-path-span-first-live-20261017-context-associated` | 30 | `ca60aa9dbf7a75e906016119680db804378461a24d64c2c203c63437e4b5ce35` |
| `private/analysis/A23-path-span-first-live-device-analysis-20261017` | 17 | `7a81b925d3fb03f27a42203c86e642ace9cbe9c63c010751ea8ae101454960fa` |

回收目录名沿用10月16日准备时间，实际回收为10月17日。233项来源、7生产源、3旧票据、3离线记录以及2份旧现场记录均重核保持。分析包保存完整解码、差异、选择依据及当前记录/恢复状态前后快照。

当前记录仍 **failed_no_retry / remaining0**，已更新 recovered=true、device_log_pending=false；恢复状态为 recovered_ejected。SD已弹出，本轮没有写卡、增加USB请求或自动重试。

下一步先离线核查 id387 的报告查询与所有权终结路径、ISO7端点状态的原始含义以及主机接收窗口与设备提交的时序约束，列出可区分的假设与最小观测缺口。完整静默轮询历史和独立物理链认证仍缺失。任何下一次实机测试须另行准备并获得开始指令，不能复用零次数记录。
