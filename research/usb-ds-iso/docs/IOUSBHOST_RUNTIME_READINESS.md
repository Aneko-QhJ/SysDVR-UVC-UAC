# 新接口的运行条件准备（2026-10-12）

本页记录当时的纯模拟准备。后续 Mac 接收器和独立一次凭据已经完成本地准备，尚未执行，
当前操作与实机证据边界见[单次实机入口](IOUSBHOST_HARDWARE_ENTRY.md)。

上一轮列出的三项电脑准备已实现并通过模拟：服务引用的获取和释放、帧号采样年龄及入队预算、
pending 请求的退出状态机。这里只证明软件拒绝和资源保留逻辑；没有连接 Switch、访问 SD、
枚举真实服务或发送 USB 请求。真实 operations 仍在任何查询、retain、打开之前被拒绝。
当前阶段与所有入口次数 0 不变，设备仍 A23，UAC/PCM 保持禁用。

## 服务引用

[SDK adapter](../host/io_usb_host_sdk_adapter.m)将候选的 service token 视作借用值。
调用者负责保持它有效直至 openCandidate 返回；provider 在第一次身份查询前取得自己的引用。
引用获取失败不查询或打开；之后任一预检、打开、描述符、pipe 或存储失败都释放自己的引用。
成功后的 lease 持有引用，关闭时先销毁 interface，再释放引用；重复关闭不会重复释放。
pending、取消拒绝、断开或缺 callback 时不提前销毁 interface 或释放服务引用。

真实 IOObjectRetain/Release 实现已编译，但本轮没有调用。19 个 adapter 故障场景用 Mock
核对获取次数、释放次数和 destroy 前仍持有引用的顺序；这些不证明真实 IOKit/SDK 的移除行为。

## 最终入队检查

[runtime guard](../host/io_usb_host_runtime_guard.m)消费一次提供的 Mock 帧号及本机 Mach 时基。
ticks 乘 numerator 使用 128 位整数，除 denominator 向上取整；零时基、逆序或 uint64 溢出拒绝。
最终检查位于 submit_begin 日志持久化之后、转交 enqueue 调用之前。检查与转交之间没有写盘。
采样年龄从查询 begin 计算，包含查询本身和日志延迟；不在已过期的帧号上改 lead 或重试。

| 参数 | 固定的软件准备值 |
| --- | --- |
| firstFrame | 一次 currentFrame + 64，溢出拒绝 |
| 帧号查询时长 | 最多 2 ms |
| 查询 begin 到最终检查 | 最多 16 ms |
| enqueue 调用时长 | 最多 8 ms |
| 帧周期假设 / 保留余量 | 1 ms / 16 ms，仅工程假设 |
| pending 退出等待 | 最多 1 s 后报告资源仍持有 |

前两项超预算时实际转交次数为 0，保存拒绝快照后才释放存储。没有 callback 就不伪造 overall
或 after STATUS；此时只能保存核心失败包与 journal，不能生成要求两次 STATUS 的 collection。
enqueue 已接受但调用超 8 ms 时停止后续工作，保留 pending 请求，可进入一次取消的退出路径。

这些阈值未由实机测得。检查后线程仍可能被抢占，SDK 内部还可能排队；软件预算通过不能
证明总线上的实际提前量、DMA、帧相位或设备时钟对齐。software_budget_verified 只表示提供的
Mock 时钟数据符合预算；software_frame_freshness_verified、hardware_timing_verified、
bus_phase_verified 仍为 false。没有把旧 backend 的 40 ms 等待移植为新接口时序条件。

## pending 退出

预算版会话使用固定 A23-no-td-runtime-plan-2；旧 v1 日志继续可读，冻结材料不原地升级。
requestExit 只接受一次退出请求，阻止新提交；只有仍 Pending 且未 detach 的 owner 才发一次
异步 abort。已经 CancelPending、取消拒绝、陌生指针或设备断开不会再取消。

调用者需在串行队列外异步安排检查，不能在 owner 队列睡眠等待 callback。exitDisposition
返回 0 表示等待、1 表示资源已关闭、2 表示停止等待并报告未解决的资源持有。
1 s 到期或 owner Retained 时返回 2，记录 storage/resources retained，不强制 destroy、reset
或结束进程；这是有界等待决定，不是已经验证的实机强制退出方案。
自己的 callback 后仍需保存完整失败证据并 ack，才能关闭；超时后恢复关闭不会把失败改为通过。
已经保存的干净会话退出可以正常关闭，不凭退出动作制造失败。

## 验证与证据

新增 11 个 Objective-C 场景包括日志拖延、慢查询、慢入队、四类 pending 退出、未提交退出、
保存后退出及超时后 callback；另有 9 组精确时基换算向量。19 个 adapter/reference、10 个
STATUS、18 个旧 no-TD 以及 16 个旧生命周期场景回归通过 ASan/UBSan 和严格编译。
91 项 Python 检查全部通过、无跳过，其中新增 17 项独立重算预算和退出条件、拒绝重哈希后的
伪造字段/关闭/时基及 native 时间错配；21 次独立 CLI 返回预期结果。
4 个预算版 collection 中 2 个 Mock 观察完整，
接受新原生基线仍为 0；allow_next_burst、hardware_entry_enabled、usb_strict_pass 恒 false。

最终材料冻结于 private/analysis/A23-IOUSBHost-runtime-readiness-review-20261012/，含源码、
原始 Mock 输入、完整 journal/失败包/collection、sanitizer 与回归日志、独立 CLI 输出和 provenance。
旧 no-TD 418、SDK 212、session 122 份文件只读核验保持不变。采集状态 SHA256 保持
a592fc6bfe95f34c7a716f37dd0974e6481cfca04686354f1dfd6a77b8615ecd。

```sh
# 仓库根目录执行；只审计已保存的模拟证据。
PYTHONDONTWRITEBYTECODE=1 python3 research/usb-ds-iso/tools/io_usb_host_probe_plan.py
PYTHONDONTWRITEBYTECODE=1 python3 research/usb-ds-iso/tools/analyze_io_usb_host_no_td.py \
  research/usb-ds-iso/private/analysis/A23-IOUSBHost-runtime-readiness-review-20261012/runtime-collections-final/clean
```

## 需要实机确认的范围

这三项离线实现准备已完成。接下来确认真实服务打开/移除、IOBuffer 映射、实际帧号采样和
新 transaction API 空槽完成语义，需要 Switch 实机证据；真实取消、断开和 callback 排空也
只能通过匹配的新 backend 确认。历史三次 native/raw 分歧仍是失败，根因、修复和长期稳定性未知。

第一项应另行准备一次 fresh、无设备 TD 的完整观察，先明确真实入口、拒绝条件和唯一次数，
取得两次原始 STATUS、自己的 callback、960 条原生记录及完整设备日志。本页不开放该入口，
不增加次数，不自动执行或放行 burst；空槽政策须依据新接口证据解释和冻结。
