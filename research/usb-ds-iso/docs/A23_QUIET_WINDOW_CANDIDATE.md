# A23 隔离捕获与文本日志的诊断候选（2026-10-15）

已实现上一轮约定的最小设备候选：30 秒诊断窗口只推进 USB 请求，视频和音频工作
线程均不读取生产帧；主线程在启动任何 worker 前设原子静默标志，只有双 join 成功
后才恢复文本日志。正常/失败二进制导出、所有权门禁和失败保留规则沿用 V3。

本轮只构建独立生成树，生产文件不改。新运行 recipe、ELF、NPDM 和主线程配置已
关联，旧接收器明确拒绝这份新设备材料。尚未将接收器或收集器改绑到新候选。
没有签发次数、有效采集、设备执行、USB/SD 访问、打包或部署；原超时根因仍未知。

## 确切改动

[构建工具](../tools/build_a23_quiet_candidate.py)从封存的执行 V3 window-30s 源树生成
新候选，严格要求仅以下四文件有差异：

| 文件 | 变化 |
| --- | --- |
| sysmodule/main.c | 视频只处理请求并以 1ms sleep 避免空转；音频每 100ms 检查退出；启动前设静默，双 join 后解除 |
| core.c | 新增 acquire/release 原子标志；FILE/UDP logger 在格式化及外部 I/O 前检查 |
| core.h | 声明静默标志接口 |
| uvc/ep0_candidate_recipe.h | 新运行 recipe |

视频仍是唯一请求处理 owner，保留调用前/返回后的过期与停止检查、窗口起止记录、
内存 trace 和正常导出。音频保留独立线程及 join，不以“UAC 当前未启用”剪掉可能的
捕获分支，而是让这个专用诊断候选的音频入口只等待退出。生产源中的视频/音频行为
不变；grc:d 启动初始化也仍存在，本轮隔离的是窗口内的生产读取/发送。

1ms 是两次请求处理之间的诊断休眠请求，不是 USB 处理限时或实际调度间隔保证。
正在执行的 UvcDeviceWaitReady / UvcDeviceProcessRequests 仍不能强制中断，窗口
30 秒不承诺墙钟 30 秒内退出。

## 静默边界和失败行为

主线程先设静默，再绑定和启动两个 worker；启动辅助函数和主线程随后的 LOG 同样
受该标志约束。静默不依赖 SD 是否挂载，也没有把 logger 锁当作 I/O 耗时上界。

两个 join 都尝试完成。任一 join 失败，静默保持，原源缓冲不可读取、文件不可打开，
线程/服务不关闭。两者都成功后才解除静默；此后 exporter 身份失败仍保留资源、
不打开文件。正常所有权完成后尝试保存 capture 和 EXE3；任一保存失败均保留。
诊断失败分支尝试保存 diagnostic 和 EXE3，即使成功也不允许 teardown。

静默期间保留有界二进制记录；保存动作仍在 join 后。没有修改 TRC2、OWN2、DIA2、
EXE3 格式，也没有通过取消、强关或重试来取得导出许可。

## 新 ELF 的静默指令路径

13 个工程编译单元重新编译并完整链接，13 个单元的严格格式检查通过；反汇编每条
原始指令字重新与 ELF 绑定。视频/音频直接调用图均没有生产读帧/发帧函数；音频只
能直接到 svcSleepThread。视频保守图仍有 SDK/格式化器间接边，未宣称全图闭合。

另外独立核验新 logger 和 setter 的指令：setter 使用 stlrb，logger 使用 ldarb，
指向同一个一字节静态标志；当读到 true 时，32 条条件路径指令经过 tbnz 直接返回，
不经过格式化、文件调用或其它函数调用。校验会拒绝普通 load 替换 acquire、返回
路径被换成调用，以及标志地址改变。该证据是在有效栈、静默字节为 true 等前提下
对当前实际指令的静态检查，未在 ARM 上执行。

**静默不等于零栈开销。** 编译器在检查标志前仍分配 832 字节 logger 帧并保存可变
参数寄存器。没有重用旧 ELF 的 2592/1904 栈剖面，也未把本轮 832 字节当作线程栈
上界；新 ELF 的其它日志、文件名与 SDK 等待路径尚须按新地址核对。

## NPDM 与新身份

| 材料 | SHA-256 / 值 |
| --- | --- |
| 运行 recipe | ae65e7036adba30cd839152299a51492b13ef0d94952921782fa2b0c938950a0 |
| full.elf | 56778e5733b73e588eb6d31c1bf1ca29c97c6d400f215537ef54bc8c84fcfef6 |
| main.npdm | 30e04ee837a81ce0be116ba90a57f3f085da7f230142568694ac47ba2a5fdcf2 |
| sysmodule.json | f034befa5d4db6a4c955d1ea6649b4e629dcf43eddaf9ade88938877eb006fa1 |
| main stack / priority / CPU 请求 | 8192 字节 / 44 / 3 |

runtime recipe 在 header 与 ELF 两处 32 字节静态对象中逐字节匹配，和旧 V3 运行
04e9…、父输入 a7ae…分开记录。新 schema A23-quiet-device-binding-1 绑定上述材料、
recipe.json、symbols.txt 以及 recipe header，共六项 artifact 摘要；只表达软件材料
一致，host_receiver_rebound=false。

构建明确传入生成树内原字节 sysmodule.json，不依赖 Makefile 的默认或外部 override。
按 [npdmtool 的 META 结构和写入逻辑](https://github.com/switchbrew/switch-tools/blob/master/src/npdmtool.c)
读取 main stack 字段 offset 0x1c、priority 0x0e 和 CPU 0x0f。再仅将栈请求改成 16384
生成独立对照，确认只有对应四字节字段范围发生变化。对照不是待部署配置。

安装的 npdmtool 摘要、两次命令和 stdout/stderr 已保存；原配置的一些可选字段产生
缺省诊断，工具退出 0，未将其隐藏或据此认证全部 NPDM 权限/加载行为。此处新增的是
**候选二进制中的主线程请求绑定**，实际内核线程预算、TLS 扣减和实机加载仍未验证。

## 回放和封存

[12 项新增检查](../tests/test_a23_quiet_candidate.py)运行实际生成的函数体及以下模型：

- 5 组视频窗口：空闲、配置串流、同步处理晚返回、ready 晚返回、bind 在窗口前耗时；
  捕获次数和过期后新请求次数均 0，晚返回样例仍为 46/45 秒。
- 76 组实际退出分支：正常/诊断，主文件与 EXE3 写入/读回/commit 故障，join 和身份
  失败。保留原 CRC、所有权与保存判定，并额外核对静默只能在双 join 成功后解除。
- 40 组实际 FILE logger：静默、恢复、空输出、511/512/1024 长文本，以及格式/文件
  故障。静默的格式化及全部 FS 调用数为 0，恢复后写入仍最多 511 字节，GetSize
  失败不 Write。静默还可安全跳过模型中的无效格式指针。
- 3 组实际启动片段与音频函数：成功启动、第一/第二次 launch 注入失败；静默在
  所有启动调用前成立，失败不解除，音频仅休眠退出。

12 项新增与此前 142 项相关回归合计 **154 项通过，0 失败、0 错误、0 跳过**。
共 124 次原生模型进程；服务、时钟、join、线程启动失败和保存结果为注入，不是
Switch 并发/SDK/设备观测。旧接收器对新材料的负向校验也拒绝，不能把旧构建记录
当作新设备的许可。

冻结 170 份研究输入，包含上一轮 166 份及新工具/测试和补齐的两份 Python 依赖；
原 166 份、七份生产文件、三份实时票据及两个 offline-record 摘要保持。
19 份既有封存共 4963 条重新通过，新审查 548 条：
`private/analysis/A23-quiet-window-review-20261015`，manifest 摘要
`b7cb185481439066a960dc958d0310945799541631aeb1e9502261a8b2ec747c`。
相关回归结果及实时记录在 `private/analysis/A23-quiet-window-validation-20261015`，
12 条验证材料另行封存。

## 下一步

先在新隔离接收器构建中绑定 quiet 候选的运行 recipe、ELF、NPDM/配置与六项材料，
使启动校验、消费回执、SDK 记录和收集器贯通；旧接收器仍只认可旧 V3。对新 ELF
复验诊断 USB 等待和 join 后保存的必要路径，维持窗口、所有权、失败保留及错误材料
收集。不得从本轮源码/模型成功推断接口 2 实机已进入、原超时已解释或可复用旧次数。
