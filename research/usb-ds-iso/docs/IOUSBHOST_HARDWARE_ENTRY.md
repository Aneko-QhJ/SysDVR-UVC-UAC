# 新接口的一次无 TD 实机入口（2026-10-12）

19:41 已在正确执行环境完成第一次实际空窗口：1次提交/1次callback、overall0，960槽
status均0、completeCount均0、raw全零，两次原始STATUS有效，正常关闭退出0。
主机观察完整、14项run哈希通过，stage=captured_logs_pending、remaining0。
完整设备日志及新原生空槽政策待核验，不自动放行burst；见[首次空窗口](IOUSBHOST_FIRST_EMPTY_WINDOW.md)。

最新诊断已确认 open_failed 来源于执行沙箱拒绝 IOServiceOpen；SDK 覆盖了底层
E00002E2 为 E00002C9。同一准备诊断在沙箱外成功打开、验证描述符、获取pipe及分配映射，
随后关闭。STATUS/ISO均0，采集凭据仍0。详情见[SDK打开诊断](IOUSBHOST_OPEN_DIAGNOSTIC.md)。
下一次采集必须重新准备单次凭据，并在有 USB 访问权限的执行环境中运行。

19:13 更新：匹配修正后的构建已单独冻结并执行一次，新接收器唯一匹配接口 2（registry
result 0），随后 SDK 打开/准备返回 IOUSBHostErrorDomain/-536870199，即 E00002C9
（本机 SDK 定义 kIOReturnInternalError）。因此停止，STATUS 0、ISO 提交 0、callback 0；
接收器退出 1，resources/storage 均未持有，无重试。这个码不能独立证明权限或占用问题；
当前未确定失败发生于 user client 创建、SDK 初始化还是 provider 后续打开步骤。
run 为 private/runs/A-A23-HS-IOUSBHost-no-td-20261012-111329-8cb31072/，9 个文件哈希已核验。
构建为 private/host-A23-IOUSBHost-no-td-corrected-20261012-111308/，独立凭据剩余 0。
下一步先诊断 open_failed，尚未得到真实映射或空窗口完成记录，SD 未访问。

19:06 更新：两次用户请求的观察均在服务选择阶段结束，匹配数 0、STATUS/ISO 提交均 0，
接收器已退出，无资源持有。第二次 IORegistry 已确认 Switch 及 HS 诊断接口 2 可见。
只读排查定位到 SDK 平面字典直接用于 IOService 匹配返回 0；将全部同一筛选字段置入
IOPropertyMatch 后匹配数为 1。源码已修正，ASan/UBSan 只读枚举、114 项 Python 回归和
修正二进制的 5 项设备访问前防护检查通过。新二进制 receiver-unarmed 未准备采集凭据，
材料在 private/analysis/A23-IOUSBHost-matching-fix-20261012/；原冻结构建及失败证据未改。
当前独立凭据 failed_no_retry，剩余 0；下述 prepared/1 是此前准备时点记录。
尚未观察真实 SDK 打开/映射或空窗口完成。不要重新执行已消耗的入口。

Mac 接收器及独立的一次观察入口已准备、构建和冻结。本轮仅本地验证，真实 registry/SDK/USB
调用为 0，SD 访问为 0。设备继续使用 A23，无需拷文件或重新部署，UAC/PCM 保持禁用。
原阶段 host_serial_clock_logs_verified_target_met 和原有入口次数 0 不变；新 backend
iousbhost-no-td-1 的独立凭据已准备 1 次，尚未执行。

## 执行条件与入口

下一步需要 Switch 实机：关闭视频，从全新启动进入 A23，使用 USB2/HS 连接 Mac。
接收器检查唯一候选、身份、实际描述符、fresh IDLE/seq0/URB0 STATUS，任何不符都停止。
本轮没有执行以下采集命令；连接并准备好实机后才运行一次。

从仓库根目录执行：

```sh
# 只读校验构建、当前源码、固定计划与剩余次数；不启动接收器，不消耗次数。
PYTHONDONTWRITEBYTECODE=1 python3 research/usb-ds-iso/tools/experiment.py test-sdk-no-td --dry-run

# 唯一一次实机观察。包括启动或预检失败在内，调用后次数即为 0。
PYTHONDONTWRITEBYTECODE=1 python3 research/usb-ds-iso/tools/experiment.py test-sdk-no-td
```

不要用旧 test/test-no-td 入口替代，也不要手工改阶段或次数。固定计划不接受运行参数覆盖。
构建位于 private/host-A23-IOUSBHost-no-td-20261012/；独立凭据为
private/analysis/A23-IOUSBHost-next-test.json。构建包含源码快照、验证报告、严格编译结果和
SHA256SUMS；入口核对每个文件、当前源码及协议头。代码变化会拒绝启动，须重新评估准备。

## 单次操作与停止

工作流先持久化消耗凭据，再启动已冻结接收器。接收器检查自身哈希及固定计划，独占创建
RECEIVER_CLAIMED 后才允许创建真实 operations 或枚举。并发或第二次调用在设备访问前拒绝。
独立 hardware 格式只由明确的 SDK 会话产生；旧 simulation 分析器仍拒绝这种格式。

唯一一次接收请求为 960 个槽，每槽请求 192 bytes，raw 缓冲区 184320 bytes，映射记录
26880 bytes。一次软件帧号查询后以 currentFrame + 64 提交。查询/采样年龄/入队调用预算为
2/16/8 ms；帧周期与保留余量仍是工程假设，不能证明实际总线时序。SDK frame_time 原值保留。

设备 vendor 控制只允许 c1/51 STATUS：正常路径在提交前及自己的 callback 后各一次。
提交拒绝不会伪造 callback 或补发 after STATUS。没有设备 TD、burst trigger、第二窗口、
reset、seize 或配置/alt 切换；SDK 读取描述符可能涉及标准 GET_DESCRIPTOR。
960 条原生记录、整体错误、raw、两个原始回复及时间、选择错误和生命周期 journal 均照实保存。
完整核心包 fsync、读回核对并 ack 后才释放映射和 interface。

请求等待预算 2 s；退出最多一次异步 abort，等待 1 s 后报告仍持有资源。
断开、拒绝取消、陌生 callback 指针、未完成保存或缺 callback 时保持资源，不重投。
SDK 调用阻塞可能延后检查，不能承诺在固定墙钟时间内完成退出。
工作流 20 s watchdog 到期会留下独立进程会话中的接收器，记录 PID，不 kill/terminate；
次数保持 0。这时保留未解决状态，不能当作成功或再次调用。
正常关闭后的 250 ms 迟到事件观察只是软件监测，不能证明 SDK callback 已排空。

## 证据回收与判读

实际 run 会写入 private/runs/A-A23-HS-IOUSBHost-no-td-*。成功退出后仍需要回收完整 Switch
启动及设备日志；这是后续只读日志回收，无需给 SD 部署新文件。

```sh
# 仅主机证据审计；还没有完整设备日志关联。
python3 research/usb-ds-iso/tools/analyze_io_usb_host_hardware.py run /absolute/run
# 将完整设备日志与该 run 封装到新的目录，失败样本也保留。
python3 research/usb-ds-iso/tools/analyze_io_usb_host_hardware.py freeze /absolute/run /absolute/device-log /absolute/new-collection
python3 research/usb-ds-iso/tools/analyze_io_usb_host_hardware.py audit /absolute/new-collection
```

观察完整只说明证据链和空窗口完整。所有原生空槽状态保留，baseline_accepted、hardware_verified、
usb_strict_pass、allow_next_burst、empty_status_policy_verified 和 callback_drain_verified 均为 false。
不能将旧 backend 的 Underrun 接受政策直接移植；需先解释新 API 的实际空槽语义并冻结政策。
首次实机目标是打开/映射、帧号采样及空窗口完成语义。真实取消、断开和排空另需相应证据，
本次空窗口成功也不能代替这些故障路径验证。

## 本地验证与冻结

114 项 Python 检查全部通过、无跳过；92 个 native 模拟场景及 9 组精确时基向量通过
ASan/UBSan。新增 18 个注入 SDK 形状的 Mock 场景覆盖 fresh/过期帧号、慢查询/入队、短回复、
取消拒绝、断开、陌生/迟到 callback、保存失败、模式拒绝及预检中断。它们不是实机结果。
生产二进制只运行了 --describe 和设备访问前拒绝路径；未运行有效的新鲜采集凭据。

验证材料冻结到 private/analysis/A23-IOUSBHost-hardware-entry-review-20261012/；Mock 数据均有
来源标记，hardware 形状用于分析器验证，不作为真实硬件证据。此前四批冻结材料共 1294 个
文件及原采集状态哈希保持不变。历史三次 native/raw 分歧仍为失败，根因、修复和长期稳定性未知。
