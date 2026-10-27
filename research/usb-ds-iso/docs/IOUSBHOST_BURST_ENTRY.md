# 单次 SDK burst 入口与零次数准备（2026-10-13）

后续17:02已执行[首次实机诊断](IOUSBHOST_FIRST_BURST_TEST.md)：控制Timeout、ISO停止后
Aborted；入口finished数值类型错误已离线修正，未重跑。本文以下保留13:38准备阶段记录。

电脑实现和冻结已完成：独立接收器、SDK准备包装、单次消耗工作流及构建工具。
221 项 Python 检查通过、0 跳过，其中17项新增入口/工作流检查；12个原生入口注入场景
通过 ASan/UBSan。构建接收器以 Wall/Wextra/Werror 严格编译，4项工作流路径检查通过。
真实 SDK 设备对象、registry、USB、SD 访问均为0；没有新实机样本或设备部署。

冻结目录：`private/analysis/A23-IOUSBHost-burst-entry-20261013-133849`。
`dormant-build/` 保存已校验来源的接收器、源码、验证报告及独立 seal；`native-fixtures/`
保存12个注入结果。原生及完整Python输出为 `native.log`、`python-full.log`，环境见
`python-environment.json`。中间检查失败也保留，最终221项结果为通过。

## 入口与准备失败

`host/io_usb_host_burst_main.m` 是独立入口；`--describe` 只输出固定诊断计划。
`--acquire-once` 必须先验证 consumed receipt 并完成 exclusive/fsync claim，才能实例化
真实 operations、查询 registry 或打开 interface。缺少收据、旧 no-TD schema、二进制hash
不符、计划/诊断范围改变、布尔冒充计数、浮点计数、重复JSON键、非规范序列化、symlink、
超大文件及重复claim均拒绝。收据不是签名或实机来源认证；它约束受控的本地工作流。

receipt 固定 `iousbhost-single-burst-1`、当前receiver hash、build manifest hash、准备UUID、
单burst计划及诊断范围。范围要求fresh A23、runtime record21、关闭视频、HS；这些是执行
条件，不能仅凭收据证明设备实际满足。原样STATUS、完整设备日志和collection仍须核验。
hardware_verified、baseline_accepted、allow_next_burst和callback_drain标记保持false。

`A23BurstEntry` 只接受筛选后的候选和provider，不自己枚举。候选必须唯一；开始前创建独立
host journal，再用现有SDK provider验证身份/描述符并准备映射。打开失败和准备中断保存
独立entry结果，不触发ISO或控制；准备后、协调器启动前的失败只关闭没有I/O的资源。
协调器成功建立后，所有取消/迟到/持有/保存规则继续由既有SDK协调器负责。

主程序每10ms poll，SIGINT/SIGTERM只设置退出请求；Pending时不直接销毁interface或退出。
未完成请求另存 `entry-retained.json` 并继续驻留，晚到完成仍保留失败。只有协调器finished
且最终结果保存成功才正常结束。匹配和准备失败的结果及selection独立保存；失败不重试。

## 构建和单次工作流

`tools/prepare_io_usb_host_burst.py` 验证当前源码hash、离线检查及真实I/O计数0，冻结源码后
编译并核对 `--describe`，最后封存构建。它只创建独立记录：

```text
private/analysis/A23-IOUSBHost-burst-next-test.json
stage = offline_build_ready
remaining = 0
acquisition_enabled = false
```

没有提供续次数或签发prepared/1的命令。再次prepare遇到现有记录会拒绝，不覆盖或续签。
旧no-TD及原serial-clock凭据保持其stage、次数、plan、run和receiver hash。

`tools/workflows/capture_io_usb_host_burst.py --dry-run` 只校验文件，不消耗次数或启动进程。
当前直接运行采集工作流会在创建lock/output之前拒绝。将来另行签发一次诊断后，工作流
仍须校验独立prepared/1记录、构建seal、当前/冻结源码、二进制及固定plan/scope。
先持久化 consumed/0/acquisition_disabled，再写收据并唯一启动；启动、收据保存或预检
失败也不能重复使用。源码变更需要重新审查构建。

20秒watchdog或wait接口错误只记录 `unresolved_no_retry`、PID和remaining0，保留进程；
不kill、不terminate、不强制解除DMA映射。结果回收独立审计host journal/core/checkpoint，
entry结果必须与最终checkpoint、进程退出码、失败数组和policy一致；成功只进入
`captured_logs_pending`，随后仍需完整设备日志/ISO7/控制关系审计。不会接受基线或放行下一次burst。

## 验证与后续实机条件

12个原生注入场景覆盖正常路径、缺失/歧义候选、打开前/后中断、打开失败、缺少burst能力、
journal冲突、控制/ISO未完成、断开及陌生指针。所有准备失败均ISO/trigger/status0；未完成
场景保持resources，正常场景保存core/final后关闭。21项native收据/命令检查覆盖14种非法
收据、有效claim及重复拒绝、describe和4种非法命令；这些检查不进入真实SDK。

新增Python检查覆盖先消耗后启动、读盘预检、锁并发、零次数拒绝、源码/build变更、seal/
symlink/重复JSON/路径损坏、收据保存和启动失败、watchdog驻留、主机完成及失败分类。
测试发现进程exit1与主机成功结果矛盾时可能仍报告host完整，已改为拒绝该矛盾；221项
最终回归通过。实际冻结构建另做4项CLI检查：dry-run通过、0次采集拒绝、describe通过、
缺失收据拒绝。本轮没有执行有效收据的真实接收器路径。

基础电脑实现已齐：SDK适配、协调器、独立保存/collection及单次入口均完成。下一项实际
传输观察需要一次明确的新SDK诊断签发和fresh A23实机：USB2/HS、视频关闭、固定960×192、
lead64、仅一次41/54/1/2/0，失败停止、不重试。无需新NSP/IPS或拷文件。
实际SDK timeout粒度、总线调度余量、有效包/空槽原生状态、同次采集来源和DMA/callback
排空仍未知；本轮不会从电脑注入结果推定这些结论，当前可用实机次数仍为0。
