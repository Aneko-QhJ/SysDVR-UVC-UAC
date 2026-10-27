# A23 首次 SDK burst 的 EP0 路径审查（2026-10-13）

首次 burst 仍为失败。电脑审查进一步缩小了设备停止位置：在同一设备实例、前后 STATUS 有效且
没有另一次 trigger 改写序号的前提下，单独的 TD 提交失败或 EP0 ACK 失败无法解释前后 seq 都为 0。
源码在这些操作之前就写入 seq=1。接口 2 是否取得并识别 BURST、速度检查结果仍缺实机记录。

## 证据与部署代码绑定

新增只读工具 `tools/audit_a23_ep0.py`，输出到新的目录，拒绝覆盖已有证据。复核：

- 原始 run 17 项、读卡证据 45 项、失败 collection 14 项、A23 部署包 28 项 SHA256 全部匹配。
- 当前 `uvc_device.c`、`source/sysmodule/main.c` 和协议头的 SHA256 与冻结 A23 validation 完全一致。
- 回收的 exefs.nsp 与冻结包逐字节一致，SHA256
  `e3bcec30c06e67ca3ce61db5740d99aa63e587206653e45c7a7e3a25b1eccb7d`。
- 从 NSP 的 PFS0 提取 main，与旧构建 NSO 完全一致。NSO SHA256
  `3d650399fee85d477e0bb2478ff1de997ad8ec3c8eb0c4ed5e4ad981bbca5c1a`。
- 旧 ELF 的三个 load 段与部署 NSO 的解压段逐字节一致，因而可以使用该 ELF 的符号与反汇编
  研究部署机器码；修改 .text 的测试会拒绝绑定。此绑定不等于主机/设备采集来源认证。

反汇编保存了 VideoStreamThread、LogFunctionImpl、UvcDeviceProcessRequests、
`_serviceSetup.part.0`、`_ctrlAck`、GetSetupPacket 和 GetSpeed。
BURST 路径在 0x1e4c 写入 sequence，0x1f8c 调用 endpoint PostBufferAsync，0x1fc8 调用 ACK，
0x1ff0 才输出 submit 日志。顺序与冻结源码一致。

## 设备分发与潜在时序阻塞

EP0 由 VideoStreamThread 单线程同步处理。服务顺序为接口 0→1→2；接口 0/1 各输出
setup 和 ignoring 两条日志。匹配接口 2 直接进入 ISO handler，不输出通用 EP0 行。
`LogFunctionImpl` 每条日志同步 open→GetSize→Write(Flush)→close，四次 SD 刷写位于 ISO handler 之前。
刷写耗时没有记录，不能从四行文本推出耗时已经超过 16ms。

视频不在 streaming 状态时，设备线程在每轮 ProcessRequests 返回后 sleep 50ms。
处理过请求后，ProcessRequests 内部用 waitMulti 最多等待 20ms 的后续 SetupEvent。
wait 返回后仍检查全部接口；这里的 20ms 是等待上限，不是必然先睡 20ms 再处理请求。
事件在等待中到达可提前返回。

当前主机 journal 的 Mach 时基为 125/3，直接换算保存值：

| 主机观察 | 耗时 |
| --- | ---: |
| 前置 STATUS 请求 | 79.373417ms |
| 前置 STATUS 完成→BURST 调用开始 | 1.290375ms |
| BURST 调用开始→控制 callback 入口 | 16.395292ms |
| 后置 STATUS 请求 | 3.660250ms |

BURST 在前置 STATUS 完成后约 1.29ms 就发出，名义上处在设备 20ms 后续等待窗口内。
这削弱了“这一请求必然等待完整 50ms idle sleep”的解释，但主机完成时刻不等于设备 waiter
入口时刻；没有跨时钟对齐、总线抓包或设备侧阶段时间戳，不能排除调度迟延。
前置 STATUS 的 79ms 也不能全部归为 sleep 或 SD 日志耗时。

[libnx usbds 上游源码](https://raw.githubusercontent.com/switchbrew/libnx/master/nx/source/services/usbds.c)
显示 SetupEvent 为手动清除事件，GetSetupPacket 通过接口 IPC command 2 读取 setup；
[event 实现](https://raw.githubusercontent.com/switchbrew/libnx/master/nx/source/kernel/event.c)
的 eventWait 委托给 waiter，eventClear 重置事件信号。
这些客户端操作并不证明 HOS 服务在控制超时后保留、清除或替换接口 2 的 setup。
上游 master 只作 API 语义参考，部署机器码与本地冻结字节是本次代码绑定依据。

## seq=0 对解释的约束

BURST 识别后的执行顺序为：poll→pending/retained 检查→GetSpeed/HS 检查→清空 STATUS
并写 seq→构造数据→PostBufferAsync→更新 URB/state→ACK→日志。
sequence 没有在 report 处理、取消或断开路径清零；普通断开仅把 pending 改为 retained。

| 候选路径 | 能否保持 seq=0 | 当前证据限制 |
| --- | --- | --- |
| 接口 2 事件未被服务，或读到不同请求 | 可以 | 0/1 广播行不证明 2 的实际读取值 |
| GetSetupPacket 返回错误 | 可以 | 通常会输出错误行，本日志没有；缺行不是绝对排除 |
| pending/retained guard | 可以 | 前置 fresh IDLE 且没有此前提交记录，缺少进入 guard 的依据 |
| GetSpeed 错误、Full/None、burst 不接受 Super | 可以 | 主机 HS 身份不证明设备调用当时的结果 |
| PostBufferAsync 返回失败 | 不可以，已写 seq=1 | 若后置 STATUS 有效且实例连续，不能单独解释此次证据 |
| 仅 ACK 提交/等待/report 失败 | 不可以，已写 seq=1 | 同上；1s 等待上限与 16ms timeout 差异本身不是根因证据 |

没有 submit 日志单独不能排除 PostBufferAsync：日志在 ACK 之后。
与后置 STATUS 的 seq=0 合起来才能得到上面的条件性约束。仍保留实例变化、服务回复语义异常等
未验证限制，不把 host STATUS 视为独立证明设备每条指令执行的 trace。

## 实际源码注入验证

`tests/a23_ep0_dispatch_fixture.c` 插入实际 EP0 helper、ISO handler、通用 handler、serviceSetup
和 ProcessRequests 源码编译，USB/事件/时间由 stub 注入。17 个场景通过 ASan/UBSan：正常分发、
ISO 无事件、GetSetupPacket 错误、三种速度检查、pending/retained、post 失败、四种 ACK 失败、
三种日志延迟/事件处理假设、post 后断开。每个场景检查实际数据、序号、stall、post 和日志。

每行日志注入 5ms、四行共 20ms 时：

- 若保留原 BURST setup，handler 仍会提交，seq=1；日志延迟本身不能解释始终 seq=0。
- 额外假设 ISO 事件在 deadline 后消失，或接口 2 读到后续 STATUS，可保持 seq=0 且无 submit。
  这些是假设模型，仅证明路径可以产生相似现象，不是 HOS 超时行为或本次根因的证据。

相关 Python 回归使用首次实机后 BOOL 修正版本的 native fixtures，共 229 项无跳过通过。
默认全库 discovery 另有未配置的历史 native fixtures 和 Unicorn 依赖，不能据此称全库通过。
初次相关回归误选更早冻结 fixtures 时复现已记录的 finished 数值类型问题，改用修正后的
fixture 路径后通过；未修改旧 fixture 或放宽 BOOL 检查。

## 下一步需要的区分证据

优先在电脑设计设备内存中的有界 trace，不在关键路径增加同步 SD 输出。至少保存：
每接口事件观察与 GetSetupPacket 前后 tick/rc/8 字节 setup、ISO handler 入口及 state、
GetSpeed 前后 tick/rc/speed、STATUS 改写前后序号、post 前后 tick/rc/URB、
ACK 的 post/wait/report/parse 结果，以及 timeout 后是否读到后续 STATUS。
增加 dropped-record/overflow 与 boot/session 身份，避免无记录被误解为无执行。
导出放在请求完成之后，不能改变原始 STATUS ABI、重投规则或 DMA 所有权。

需要先离线核对服务的 timeout/setup 保留语义或实现 trace 原型，再评估是否需要新设备诊断版本。
不能只增大主机 timeout：还必须重新检查 lead64 窗口、设备提交时刻和停止后潜在迟到 TD。
本轮没有新部署、新凭据、实机重试或 timeout 调整；burst remaining=0。

证据输出：`private/analysis/A23-EP0-dispatch-review-20261013/`。
复核工具和原生 probe 可再次输出到新目录：

```sh
python3.12 research/usb-ds-iso/tools/audit_a23_ep0.py --output /private/tmp/a23-ep0-new-review
python3.12 -m unittest discover -s research/usb-ds-iso/tests -p test_a23_ep0_dispatch.py -v
```

当前状态和下次续接见 [STATUS.md](STATUS.md)、[PROGRESS_HANDOFF.md](PROGRESS_HANDOFF.md)。
