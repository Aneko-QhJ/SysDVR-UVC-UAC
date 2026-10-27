# 生命周期候选首次实测及读卡（2026-10-16，Asia/Shanghai）

用户在部署完成后要求“继续”，核验 213 项来源、旧记录、新包/接收器及真实部署和弹出回执后，签发独立的一次记录。主机先进入 WAITING，用户随后开机进入 CFW，捕获唯一一次 HS 到达并执行一次请求链。没有复用旧 quiet 记录，没有自动补次或重试。

## 主机结果

本地 14:28:46 启动，run 的 UTC 标识为 `20261016-062846`。控制请求约 **0.464875 ms** 完成；ISO 约 **183.1795 ms** 回调，无超时、无 abort，资源关闭、进程退出 0。然而 **960 项 actual 全为 0，184320 字节缓冲全零**。STATUS 从 seq0/state0 变为 seq1/state4（RETAINED），requested3072 / transferred0 / urb_status2。退出 0 和回调状态 0 不等于有效载荷通过，当前仍 `failed_no_retry / remaining=0`。

主机证据：`private/runs/A-A23-lifecycle-waiting-20261016-062846-7a045fd1`，18 条封存，manifest `379067b1eff700c3e95924a47166ec70fc0ca6a4d1d1b82b828b2f22129d9bc8`。独立分析：`private/analysis/A23-lifecycle-first-live-host-20261016`，5 条，manifest `f35a2be492c84b4a0bc2a011fa96bdf01285d557b9bb91329aaeb97affab68af`。

## 只读回收的新证据

按提示保留开机时间后，用户完全关机取卡并确认接入。重新核对 UUID 后只读挂载，保存 33 个选取原件并读回；**14:31:48+08 安全弹出 disk4，挂载消失**。四部署文件匹配已部署生命周期新包。与部署前快照相比，新增一个 LCP1；NSP 为已知部署变更，日志基地址更新；没有删除原件，21 个报告和旧失败临时文件保持。

取得 `ep0-life-ea16d9847fef29b6f5be9b32dc0858ac.bin`，3968 字节，SHA256 `71129a74863d1153cbe80aacae0e4d8c8955af1844aab7704369a7ba189707d3`。recipe 和文件名 nonce 匹配，27 条有效连续阶段记录、零尾部、解码无错误。没有 EXE3、主结果或 trace。日志仍止于 UVC device initialized，不能只看日志末行判断设备没有继续运行。

记录内容依次包含准备、USB 初始化返回 0、进入静默窗口、离开主循环、cleanup_result=1、video/audio join 返回 0、exporter/context、owner finish、两路结果保存及 retain。两次 SD 打开都返回 0，随后：

| 保存路径 | 创建字节数 | file_create_result | 保存结果字段 |
| --- | ---: | --- | --- |
| diagnostic 主结果（arg0=2） | 4400 | 54273 / `0xD401` | phase2 / rc54273 |
| EXE3（arg0=3） | 5456 | 54273 / `0xD401` | phase2 / rc54273 |

按当前本机 libnx `result.h` 解码，`0xD401` 的 module=1、description=106，对应 `KernelError_InvalidMemoryState`；该头文件已随设备分析保存。这里是 SDK 返回值的名称，不等于已经定位到某个地址、IPC 缓冲、栈或具体系统分支。

这将缺少 EXE3/主结果的调查收敛到记录中的文件创建失败：不能再仅因缺文件猜测 main 没退出、join 没返回或 SD 打开失败。与此同时，LCP1 的最后有效槽不证明实际最后执行点；其自身提交和 join 结果尚无独立认证。没有 EXE3，无法建立完整的设备 context 与主机 nonce/请求链关联，因此不得将内容自洽提升为同一次物理运行或 ISO 根因证明。

| 材料 | 路径（相对 research/usb-ds-iso） | manifest SHA256 |
| --- | --- | --- |
| 只读原件，35 条 | `private/card-cycles/20261016-143132-lifecycle-first-live-read` | `9425f16002267da2c66f9bd8fea058e6c031e8343fea71d25ecf81d68bbfbd7a` |
| 操作，6 条 | `private/analysis/A23-lifecycle-first-live-recovery-20261016-143132` | `dbd3aa9a3e3280cbfd5406e00a2006871b89b2ece808baca3110cefbcef7dbfc` |
| 缺证收集，28 条 | `private/collections/A23-lifecycle-first-live-20261016` | `4b522945b34c4ce874a6ab9b9643731a092fe499e3f06ba231adc32e228ad563` |
| 设备分析，4 条 | `private/analysis/A23-lifecycle-first-live-device-analysis-20261016` | `3129470c0b482d21763a265b6006587c07bac307026d4aeff3f35f00b02dfea6` |

收集器重核材料/设备绑定、进程和 SDK claim 一致；完整执行链和物理来源认证保持 false。新现场记录只补回收/收集位置及 recovered，不改变失败或零次数；旧三票据、三离线记录和旧 quiet 现场记录保持。

## 下一项研究

先做离线文件创建路径审查：对比 USB 初始化前成功预创建 LCP1 与退出后失败的 diagnostic/EXE3，核对实际链接的 fsFsCreateFile/IPC 实现、路径地址和内存属性、调用栈及 TLS/服务对象生命周期。两路 SD 打开成功和 LCP1 可持续保存，已不支持直接把现象概括为所有 SD 写入均失败；但仍不能排除特定调用路径问题。

优先建立能够区分内存映射、服务状态和调用条件的最小离线模型，再决定是否需要新的隔离候选。不要无依据改超时、扩大栈或重复这次实测。卡已安全弹出，可装回但先保持关机；下一次硬件动作需要基于新材料和明确启动指令，旧次数不恢复。
