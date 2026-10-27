# 第一次 SDK 单 burst 实机诊断（2026-10-13 17:02，Asia/Shanghai）

后续：17:43已完成只读回收及安全推出，见[读卡复核](IOUSBHOST_FIRST_BURST_CARD_REVIEW.md)。下文为测试时记录。

已按本次“测试”签发并执行一次新 SDK 单 burst 诊断，失败停止，没有重试或访问SD。
控制请求被SDK接受，但约16.395292ms后回调 `0xe00002d6`（kIOReturnTimeout）；协调器
记录控制deadline/失败并请求一次异步abort。ISO约19.877667ms后返回自己的回调，整体
`0xe00002eb`（kIOReturnAborted），未收到有效数据包。core保存/ack后，after STATUS完成，
interface和映射资源关闭，接收器退出1。250ms关闭后观察不证明callback排空。

## 原始观察

| 项目 | 结果 |
| --- | --- |
| 连接/选择 | SysDVR 1209:ca57，USB2/HS，唯一vendor接口2/alt0/ff49 protocol1；诊断接口无exclusive owner |
| 视频条件 | 读到UVC映射buffer分配0；要求视频关闭，未独立认证设备视频状态 |
| STATUS | 前后168bytes，原文和journal绑定；均fresh IDLE/seq0/URB0，两个原文完全相同 |
| 帧号 | current1497478，first1497542，lead64 |
| ISO软件预算 | query6.959µs、age364.584µs、enqueue432.209µs，原固定预算通过 |
| 控制入队 | 一次41/54/1/2/0，SDK accepted=true；gap202.209µs、age999µs，请求timeout16ms |
| 控制完成 | 一次回调，bytes0、0xe00002d6；原始native ingress时刻保留 |
| ISO/abort | 一次ISO提交、一次异步abort、一次自己的ISO callback；没有陌生指针或重新提交 |
| 原生槽 | 960条均0xe00002eb，actual均0；184320byte raw全零、有效包0 |
| 退出 | core/final已commit、resources closed、无storage retained、进程exit1 |
| 凭据 | 新burst凭据failed_no_retry/remaining0/acquisition_disabled；旧no-TD及原serial凭据不变 |

SDK头文件定义上述Timeout/Aborted码，不能用旧backend的Underrun政策解释这次取消。
core的 `timed_out=true` 来自owner请求abort时记录停止状态，并非ISO已经等待到2秒deadline。
当前已观察到控制超时及停止后的ISO取消；不能仅凭after仍IDLE证明请求从未到达设备，
也不能证明设备补丁、SDK实现或总线调度中的哪一项是根因。

## 入口类型错误与离线修正

原始 `entry-result.json` 的finished字段为JSON数字1，而非布尔true。Objective-C逻辑OR
表达式返回C int，直接box导致此字段类型错误。严格工作流保留
`entry result contradicts process/host`，没有放宽字段检查或把实机结果重写为通过。
独立host审计仍能验证journal/core/final字节关系（host_binding_verified=true），同时按
原始控制错误、整体取消和缺少payload判定host_observation_complete=false。

`A23BurstEntry.result` 已在电脑显式转BOOL后box；原生入口测试新增全部布尔字段CFBoolean
类型检查，Python同时检查导出的JSON类型。修正后12个原生入口注入场景通过ASan/UBSan，
221项Python回归通过、0跳过，修正接收器严格编译通过。本轮修正后的接收器没有再访问USB。
既有已消耗构建、run、原始失败报告及finished=1保留；源码变更后，旧构建不能重新签发，
后续如果需要新诊断必须审查新的冻结构建。

## 证据与下一步

run：`private/runs/A-A23-HS-IOUSBHost-burst-20261013-090224-3c3789da`，17个manifest文件
及outer commit核验通过。构建：`private/analysis/A23-IOUSBHost-burst-entry-20261013-133849/dormant-build`。
签发、连接快照、进程检查、原始凭据前后、独立host分析和离线修正证据：
`private/analysis/A23-IOUSBHost-burst-test-20261013-170016`，修正输出位于 `offline-fix/`。
旧冻结材料未改变，没有新的NSP/IPS或SD部署。此前空窗口的成功观察仍单独保留。

下一步关闭Switch并回收本次完整启动设备日志，核对A23/Build-ID安装记录、三组控制分发、
是否发生burst提交/终结或错误，以及STATUS关系。不要用旧日志或合成ISO7补齐本次样本。
没有设备log时不冻结宣称设备关系完整的collection，不再次测试，不调整16ms政策或重试。
hardware_verified、usb_strict_pass、baseline_accepted、allow_next_burst、callback_drain_verified
仍为false；原生空槽政策、同次采集来源及根因仍未确认。
