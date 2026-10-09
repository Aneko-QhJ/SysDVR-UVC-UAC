# 本地验证记录 — 2026-10-01

目标 usb Build ID：`AD8D36F2029822A4C498F055ADBDAA789EB913C6000000000000000000000000`。
SystemVersion Data NCA 确认 HOS `22.5.0-1.0`。地址均为该模块映射地址。

## 已恢复的实验 ABI

| 地址 / 对象 | 实验所用 ABI / 作用 |
| --- | --- |
| `0x30270` | 原 endpoint buffer 提交包装，保留 DMA 与同步路径 |
| `0x302E0` | x0 controller、w1 endpoint address、x2 DMA、w3 size；ISO 分支处 x1 已转换为 endpoint entry |
| `0x30364` | 原 ISO 条件分支；补丁保留 EQ 条件并进入独立 producer |
| `0x31AB0` | 非 ISO 原 Normal producer；未重写 |
| `0x31C74` | 原 device doorbell tail，复用检查及 MMIO 写入 |
| `0x30B50` | 原 context 安装路径；实验 descriptor 使用现有路径 |
| `0x30898` | transfer-event dispatch 调用点，x0 controller、x1 原始 event |
| `0x30F70` | 非实验事件继续使用的原处理器 |
| `0x2A980` | x0 manager、w1 endpoint、w2 result、w3 terminal、w4 raw count、w5 lock；实验匹配终结时调用 |
| `0x2CBE0` | report epilogue hook，x19 DsUrbRing、x20 UsbDsReportData |
| EP83 entry | controller + `0x22270`，index 7；ring base/enqueue/dequeue/Link 为 +10/+18/+20/+28，DMA base +38，cycle +40，doorbell index +42 |
| DsUrbRing | controller +60、endpoint +70；真实 report 槽与 count 保持原 ABI |

公开 `PostBufferAsync` 没有新增参数。状态工具通过 vendor EP0 请求取得客户端
report 与实验诊断；诊断复制到七个未用 report 槽，真实第一槽不变。

## 已完成的本地检查

- A/B/C 注入分别为 632/604/636 bytes，均在 684-byte RX 页尾空白内。
- 13 项测试执行实际补丁后的 AArch64 指令，全通过。覆盖 A/B/C 字段、
  首 cycle 最后发布、HS/SS、Link/wrap、零 DMA 与不支持输入、忙 ring、
  Bulk 原路径、重复事件/双 IOC、未知事件保留 DMA、report ABI、
  Build ID/hash 不匹配及 281-byte configuration 的组装/读取。
- 实验与恢复客户端独立强制构建；生成的 NPDM Program ID/range 已检查。
- macOS libusb 接收工具已构建。无设备 smoke check 正常报告设备不可访问。
- 四个 ZIP 已检查 CRC、NSP 的 main/main.npdm、补丁 manifest 哈希与主机
  工具执行权限；恢复 ZIP 不含 IPS。Git diff 空白检查通过。
- 原始模块、Ghidra 工程、反编译与日志保存在 private，未纳入 Git。

日志：`private/logs/tests.log`、`packages.log`、`exefs-iso-build.log`、
`exefs-rollback-build.log`。每个补丁的原字节、新字节及哈希在包内 manifest。

## 实机验收状态

| 项目 | 当前结论 |
| --- | --- |
| 主机收到可核对的 ISO 数据 | 未运行实机实验 |
| 原 ED completion 可复用 | 未验证；当前采用实验受控终结 |
| remaining length / actual length 语义 | 未验证，保留 raw count |
| 总线 transaction 波形 | 未验证，需要协议分析仪 |
| A/B/C 事件数量及 endpoint 错误状态 | 待实机记录 |
| 100 次重复、取消、断开重连、UVC 开流 | 待首个单 TD 成功后验证 |

诊断只保存提交时 context 首四个 dword、发布的 TRB、地址/tag、前两个
原始事件及总计数；ring 位置/cycle 与固定 doorbell 可由这些值关联。
没有错误后的完整 context/MMIO 快照，尚未实现未经确认的 frame counter。
若 SIA 实验失败，下一步依据这些记录限定分析 device MMIO 时间基准。

按 README 先部署 A，每次切换变体重启并保存新的 JSONL 与 Switch logfile。
没有实机记录之前，不进入 UAC、alt1 或连续 streaming。

## 首次 A 实机采集 — 19:32

已备份原客户端并部署 A，文件哈希与 package manifest 一致，SD 安全推出。
macOS 原生 libusb 成功 claim interface 2 / EP83，枚举为 SS（speed 4），
configuration length 为 188。沙箱内首次打开设备失败，随后原生访问成功。

一次 sequence 1 提交返回 `0x1908C`，状态为 FAILED；512 个主机 ISO
packet 均为 status 0 / actual_length 0，没有匹配测试数据。诊断 magic
与 event_count 均为零，未得到 controller 原始事件证据。主机接收回调已完成。

本次只能确认 vendor 接口可访问、提交被软件拒绝；不能判断 type-5 硬件
是否执行。需要 SD logfile 和实机 usb Build ID/补丁加载信息，区分补丁未生效、
目标版本不匹配或 producer 输入检查拒绝。尚未重投，也没有进入 B/C。

原始记录：`private/runs/A-20261001-193226/host-native.jsonl`，
解码：`summary-native.json`；部署备份：
`private/deployments/20261001-193017-A/`。Switch SD 日志待用户关机后回插采集。

### SD 日志回收 — 19:34

`switch-logfile.txt` 与 `sd-collection.json` 已保存到同一 run 目录。
SD 上 IPS/NSP 的哈希仍与部署记录相同，没有新增或变化的 crash/fatal/erpt
报告。启动配置使用该 SD 的 Atmosphère 与 RAW1 emuMMC。

Switch 日志显示初始化成功、USB 连接及 sequence 1 vendor 请求到达。
普通 UVC interface 0/1 对 wIndex2 的 mismatch 日志属于转发旁路；主机已
取得 interface2 的有效状态响应，不能据此判断 ISO interface 未处理。
本版没有打印提交输入或实机 usb Build ID，文件哈希匹配也不能证明 IPS 在
运行模块上生效。因此当前无法在补丁未加载与严格输入校验拒绝之间定论。
下一轮应先加入实机 Build ID 与补丁入口/拒绝原因诊断，保留单 TD 和 A 组，
不靠切换 B/C 或改 Frame ID 来掩盖尚未确认的软件入口问题。

### A2 诊断构建与部署 — 19:41

保留 A 的 IOC/ED/SIA，增加启动时实机 HOS/usb Build ID 查询及 `0xD1`
report-hook / `0xD2` producer-entry marker。拒绝时记录 DMA、length 和
endpoint entry 前16字节；正常发布恢复原 ISO1 诊断格式。仍无法直接记录
具体拒绝分支；可用输入快照排除 descriptor 校验，剩余检查再限定分析。
14 项实际指令测试全通过，客户端与主机工具重新构建。A/B/C 注入分别为
680/652/684 bytes，未越出验证的 RX 空白区。

A2 已写入 SD 并核对全部部署文件哈希。A1 文件和 logfile 另备份到
`private/deployments/20261001-194156-A2/`。下一次实测仍只触发一个 A TD。

### A2 首次接收 — 19:44

`private/runs/A2-20261001-194418/` 保存完整主机 JSONL、summary 与退出状态。
仍为 SS/interface2/EP83，单次提交返回 `0x1908C`，512 packets 全部零长度。
各次 STATUS 的诊断 magic 均为零，既未观察到 `0xD1` report hook 标记，也
未观察到 `0xD2` producer 入口标记。该结果提高了补丁未加载/目标模块
不匹配的可能性，但还不能排除 report hook 的条件未满足。下一步读取
本轮 SD 启动日志中的实机 HOS/usb Build ID 和查询 result，未再触发 TD。

### A2 SD 回收与 A3 诊断

A2 的 `switch-logfile.txt` 已回收：实机 HOS 22.5.0、usb PID86，模块
Build ID 与目标完全相同，base `0xEB2200000`、size `0x369000`。
模块查询全部成功，SD 的 IPS/NSP 哈希匹配，无新增错误报告。
因此版本不匹配已排除，运行时 IPS 是否生效仍需验证。

A3 保留 A2 controller 补丁，只在客户端启动查询后尝试只读 usb 内存：
hook `+0x30364`、report hook `+0x2CBE0`、注入区 `+0x68D54`。
调试 attach/read 的 result 全部记录，成功时立即关闭 debug handle 后再
执行 USB 初始化；不写目标内存。若权限拒绝，继续正常单 TD 实验。
客户端与恢复包构建成功；controller 指令未变，沿用已通过的14项验证。

### A3 单次接收 — 20:15

`private/runs/A3-20261001-201531/` 保存原始主机日志与 summary。
SS/interface2/EP83 可访问；提交仍返回 `0x1908C`，没有有效 payload，
report/producer marker 均未出现。主机回调已完成，未重投。
需要回收本轮 SD 日志中的 debug attach/read result 与实际指令值，
才能判断运行内存是否有 IPS；主机零诊断本身不构成该结论。

### A3 SD 回收：运行模块未加载 IPS

调试 attach/read 全部 rc0，运行 hook `+30364` 为原指令 `54000180`，
report hook `+2CBE0` 为原指令 `91004260`，注入区 `+68D54` 全零。
实机 Build ID 与布局一致，SD IPS/NSP 哈希匹配，无新增错误报告。
据此确认本轮实际未加载实验补丁；不能据前三轮零数据推断 ISO 硬件行为。
加载链为何跳过 IPS 尚未定位，不将该未知归因于 descriptor 或 frame。

### A4 运行时安装器

为实验引入 Build ID/布局/完整补丁范围预校验后安装同一补丁的运行时路径。
通过已验证能访问 usb 的 debug handle 暂停目标，先验证全 original 或
全 installed 状态，拒绝 mixed/未知状态，再逐范围写入并读回。
失败会恢复已尝试范围；无法确认恢复时保持目标暂停等待重启。
对 NAND 无写入；客户端移除后重启恢复原模块。A/B/C 各编译独立客户端。
源码 `source/uvc/iso_runtime_patch.h`，payload 从已校验模块与 IPS manifest
生成到 private。15 项测试通过，包含实际 C 安装器的重复安装、未知/混合
原字节、部分写失败、读回不一致及恢复失败，尚未在实机验证安装成功。

A4 的 A/B/C NSP 内嵌 payload 均与各自 inject.bin 核对，ZIP CRC 通过。
A 包已部署 SD，文件哈希核对完成，A3 文件和 logfile 备份到
`private/deployments/20261001-202651-A4/`。下一次采集先检查安装结果，
仍只有一个 A 组 device TD；未启用 UAC。

### A4 首个实际 TD — 20:52

`private/runs/A4-20261001-205247/` 保存 JSONL 与解码结果。
首次 STATUS 已看到 `0xD1`，提交 result0、URB387/requested192。
ISO1 快照显示 context EP State1/Type5、Isoch `80001411`（SIA1/IOC0），
ED `00001C21`。事件计数3，仅前2个已保存：

1. `80023000 00000000 170000C0 00078001`：ED0，指向 Isoch physical，
   completion code23/raw count192。
2. `D037D010 00000048 01000000 00078005`：ED1/tag匹配，code1/raw count0。

已有补丁执行及 ring/event 链路证据；512 host packets 全部 actual_length0，
仍无有效 ISO 数据。实验 hook 根据第二个 ED 事件终结 URB（report status3），
但第一条 Isoch 已报告非成功码。因此 terminal report PASS 不表示传输成功，
不能宣称原 completion 可复用。第三个事件未存储，需后续扩大事件诊断。
后续应记录 TD 的错误事件并阻止把随后 ED code1 当作整体成功；本轮没有重投。
SD 启动安装 result、完整日志与错误报告仍待回收。

### A4 SD 回收与 A5/B 构建

SD 日志已保存：运行时 patch result0，22 个范围写入/读回成功，实机身份
匹配，无新增错误报告。收到的 ISO 错误与后续 ED 成功均是真实 controller
事件，A4 的终结逻辑会掩盖前者，必须修正后再评估 completion。

A5 锁存匹配到的错误并保留 URB/buffer，不让后续 ED code1 清除错误；
记录前两个事件加最新事件（复用 ED 快照槽，仍有界112 bytes），以便下一轮
看到第三个事件。移除临时 D2 输入快照给代码腾出空间。16 项验证通过，
包括原 A4 的 code23→ED-success 事件序列不再释放、最新事件及安装回退。
下一轮部署 B，单 Isoch/IOC1/无 ED；SIA/FrameID/descriptor/context 保持原设置。

公开 device-side 参考为 Linux Tegra XUDC 的
[queue_one_trb](https://code.googlesource.com/linux/torvalds/linux/+/9f7853d7609d59172eecfc5e7ccf503bc1b690bd/drivers/usb/gadget/udc/tegra-xudc.c)：
采用 type5、SIA1、FrameID0，单 TRB 结束用 IOC1/Chain0，与本轮 B 相符。
同源的 context 使用原 bInterval，不能套用 host xHCI 的 interval 编码来修改。
参考驱动列出 device MFINDEX +48、frame=(register>>3)&7ff；实机 MMIO
映射与时间增量还未核对，暂不据此排 explicit FrameID。
code23 在 host xHCI 表中为 Missed Service，但该 device 驱动没有定义它，
因此设备侧语义仍待调度实验核实，不当成已确认解释。

B/A5 已部署，最终文件哈希和 ZIP CRC 核对完成；B 不接受任何 ED 事件，
包括零 tag。A4 客户端、补丁和 logfile 备份于
`private/deployments/20261001-210649-B-A5/`。仍待实机单次测试。

### B/A5 单次接收与取消 — 21:31

`private/runs/B-A5-20261001-213136/` 保存主机 JSONL、summary 与独立 cancel
记录。提交 result0、URB387/requested192，Isoch `80001421`，SIA1/IOC1、
无 ED。512 packets 全部零长度；两个原始事件为：

1. `80023000 00000000 170000C0 00078001`：ED0、指向 Isoch，code23/count192。
2. `00000000 00000000 0E000000 00078001`：ED0、code14/count0、指针零。

错误锁存 `80000017`，状态 RETAINED、URB report2，未释放或重投。
B 同样出现首个 code23，排除 ED 串接是该首次错误的必要条件。
保存原始数据后只测一次 CANCEL：exit0，关联 URB387 report4，状态 FAILED
（取消终结），邮箱重置为 D1。现有软件取消路径可终结本次 retained URB；
没有重用 buffer，也不据此宣称 endpoint reset/restart 或持续流稳定。
SD 启动安装日志仍待回收，下一轮依矩阵测试 C。

### B SD 回收与 C 部署 — 21:35

B 启动日志确认 Build ID/布局一致、runtime patch result0；关联 URB387
取消终结 report4，与主机 cancel 记录一致。SD 文件哈希匹配，无新增错误
报告。主机原始事件记录在取消之前已保存，Switch 取消后邮箱清零不影响它。
C/A5 的 IPS、NSP 内嵌 payload、ZIP CRC 已核对，现已部署 C 双 IOC 版本，
四个 SD 文件读回哈希一致。B 文件和 logfile 备份在
`private/deployments/20261001-213531-C-A5/`。C 仍用 SIA1/FrameID0，等待单次接收。

### C/A5 单次接收与取消 — 21:47

`private/runs/C-A5-20261001-214702/` 保存主机 JSONL、summary 和取消记录。
提交 result0、URB387/requested192，Isoch `80001431`（SIA1、IOC1、Chain1）。
512 packets 全部零长度。前两个加最新事件正好捕获本次三个事件：

1. `80023000 00000000 170000C0 00078001`：Isoch pointer/code23/count192。
2. `BBD7D010 0000003A 01000000 00078005`：ED tag/code1/count0。
3. `00000000 00000000 0E000000 00078001`：code14/count0、指针零。

错误锁存 `80000017`，URB report2、RETAINED；后续 ED code1 未误释放。
仅执行一次取消：exit0，关联 URB387 report4、取消终结，邮箱恢复 D1。
没有重投，SD 日志待回收。至此 A/B/C 的 SIA 单次实验全部无有效数据，
且共有第一条 code23；后续限定分析 device MMIO 的 frame 时间基准及
context/ring 调度状态，确认实机单位后再试 explicit FrameID/lead。
仍不能声称 ISO 数据或总线波形成功，原 ED completion 可复用性也未通过。

### C SD 回收与 B/A6 frame-only 准备

C 启动日志和主机取消记录一致：Build ID 匹配、runtime patch result0，
URB387 取消 report4；SD 四个文件哈希匹配，无新增错误报告。
原始日志保存在 C-A5-20261001-214702 目录。

B/A6 增加只读 device MMIO +0x48 的八次采样及系统 tick 前后界，
同时保存 CTRL、PORTSC、MMIO 地址和 report result。仅在 D1/未提交状态
采样；TD 发布后的 ISO1 诊断不覆盖，PENDING/RETAINED 拒绝采样。
主机 `--frames` 不预排 ISO、不触发或取消 TD。时间基准待实机验证，
本轮不提前改 FrameID/SIA/context。17 项真实 ARM64 仿真和安装回退测试通过，
Switch 客户端及 macOS 接收工具已构建，注入长度 A668/B672/C672。

B/A6 frame-only 已拷入 SD，四个文件读回 SHA-256 匹配，ZIP CRC 验证通过，
disk4 已安全推出。C 文件及 logfile 备份于
`private/deployments/20261001-220846-B-A6-frames/`。
下次连接运行 `--frames`，时间单位未确认前不发新 TD。

### B/A6 实机 frame 计数采样 — 22:10 后

`private/runs/frames-A6-20261001/host.jsonl` 与 summary 保存八组原始样本。
SS、interface2/EP83，八次 report result0；MMIO 地址固定 `738464C000`，
CTRL=`20001`、PORTSC=`1003`。MFINDEX 从1223递增至2959，七段按系统
tick 计算的速率为7996.53、7986.42、7996.02、8004.18、8011.74、
7979.45、8030.68 次/秒。设备和主机独立校验均通过：支持 +48 为125us
计数基准，frame 使用 `(MFINDEX >> 3) & 7ff`。本批没有观测硬件计数回绕。
没有预排 ISO、提交或取消 TD；此结果只确认计数时间基准，不是 ISO 数据成功。
Switch 启动/采样日志待下次读卡保存。

下一包 B/A7 lead4 位于 `private/packages-A7-lead4/`，保留原 A6 包。
B 关闭 SIA，在 producer 内读当前 device MFINDEX，再编码
`((MFINDEX >> 3) + 4) & 7ff` 到 bits30:20；IOC1、Chain0、无ED，
单192byte、descriptor/context/错误锁存逻辑维持。A/C 保持 SIA，
本轮只部署 B。为满足 RX 空间限制，显式调度 B 移除提交前的 frame 采样
report hook；原 A6 采样包仍保留。B 注入652bytes，未超过684bytes。

B/A7 客户端及补丁已构建，ZIP CRC、客户端 hash、revision/lead manifest
校验通过。18 项测试中17项通过、1项旧 A6 frame report 测试按变体跳过；
新测试实际执行 B ARM64、覆盖 HS/SS、microframe→frame、FrameID2047回绕，
并确认不写 MFINDEX。ring/cycle/重复事件与安装回退验证通过。SD尚未部署。

### A6 SD 回收与 B/A7 lead4 部署 — 22:20

A6 Switch 启动日志已保存到 `private/runs/frames-A6-20261001/switch-logfile.txt`。
实机 Build ID 一致、runtime patch result0；八组 tick/MFINDEX/CTRL/PORTSC
与主机记录逐字段一致，日志标明 no TD submitted。SD 四个文件哈希匹配，
与部署前基线相比无新增/变更错误报告。

B/A7 lead4 已部署，四个文件 SHA-256 读回一致；ZIP CRC 和客户端 manifest
已核对，disk4 安全推出。A6 文件及 logfile 备份在
`private/deployments/20261001-222024-B-A7-lead4/`。
下次连接执行一个192byte TD，检查主机数据、FrameID/SIA 和全部 controller
事件；失败时先保存观测再取消，不重投。

### B/A7 lead4 单 TD — 22:23

`private/runs/B-A7-lead4-20261001-222343/` 保存主机 JSONL、stdout/stderr、
exit 与 summary。提交 result0，URB387/requested192；Isoch 控制字
`5E901421`，FrameID1513/SIA0/IOC1/Chain0、无ED。controller 两条事件：

1. `80023000 00000000 01000000 00078001`：ED0、指向该Isoch、code1/count0。
2. `00000000 00000000 0E000000 00078001`：ED0、指针零、code14/count0。

首次匹配事件从 SIA 变体 code23 变为 code1；hook 终结一次，URB387
report3/state COMPLETE、terminal1。raw count0 仍原样保存，不解释为传输0
或192bytes。后续 code14 被记录；硬件 reset/restart 及原 completion 可复用性
仍未确认。主机 transfer status1，libusb 警告 `0xe000400e`，所有公开 packet
描述符 length0/status0，没有通过192byte测试数据校验。exit1，未重投，
没有对已终结 URB 再执行 CANCEL。等待 SD 启动日志回收。

本机 SDK USB.h 将该 IOKit 返回定义为 kIOUSBNotSent1Err/Transaction not sent。
核对 [libusb v1.0.30 Darwin completion](https://raw.githubusercontent.com/libusb/libusb/v1.0.30/libusb/os/darwin_usb.c)
发现该 backend 仅在整体结果 success/underrun/transaction-timeout 时复制
isoc_framelist 的逐包状态和长度。上述整体错误不在允许条件，公开的全部
零长度/默认成功状态不足以判定逐包实际情况；此前记录的零长度也应只理解
为 libusb 暴露的值。下一步应保存原始接收 buffer、观察 IOKit frame list，
或用辅助 Linux 接收交叉验证，区分主机接收失败与设备确实未传数据。
仍未达到“主机收到 ISO 数据”，未验证总线波形，不能直接启动 UAC。

### A7 SD 回收与主机原生诊断准备

Switch logfile 已归档到 B-A7-lead4-20261001-222343：target Build ID 一致，
runtime result0；seq1/URB387/requested192/raw-count0/report3/events2，
与主机记录相符。四个部署文件哈希一致，与基线相比无新增错误报告。

为隔离接收侧盲区，本轮不修改 SD 上 B/A7 lead4。独立编译 libusb1.0.30
Darwin backend：原生 frame status/requested/actual 有界输出（最多1024），
整体错误时仍复制逐包证据，保留整体错误/调度/取消逻辑。接收 callback
保存零初始化的原始 buffer 到按序号命名的文件；buffer图案单独标记，
不取代 packet status/length/data 校验。依赖缺少 GNU libtool，本次安装2.6.2。
Homebrew libusb 未替换；otool 确认诊断 executable 只链接系统 frameworks。
原始 tar SHA-256、修改前后 backend 及 executable 哈希保存在
`private/darwin-diag/manifest.json`，构建脚本纳入版本管理。

19 项测试中18项通过、1项 A6 report 测试按变体跳过；实际 callback 测试
覆盖 buffer图案不能掩盖零长度或 packet错误、独立 buffer保存，以及整体
错误时有效逐包证据。所有先前 ARM64/回退测试仍通过。原生诊断工具
已构建，包 `private/packages-A7-lead4/Mac-ISO-native-diagnostics.zip` CRC通过，
包含源码、修改后的 backend 和许可。SD 保持同一 lead4 文件并安全推出。
下一次连接只提交一个 TD，以原生逐包记录和buffer补齐上次观测，不重投。

### B/A7 lead4 原生接收 — 22:45

`private/runs/B-A7-lead4-native-20261001-224515/` 保存 host JSONL、完整 stderr、
512条原生frame记录、98304byte接收buffer、summary及独立payload-evidence。
**主机收到可核对的测试数据已观察到，但无错误的 packet 接收仍未通过。**

原生 packet42 requested192/actual192，buffer同一192byte槽含完整
`ISO1`、序号1及全部测试图案。独立离线逐字节核对：native长度、公开
data_hex、raw allocation 和预期192byte完全一致；其他槽没有测试图案。
原生 packet状态 `e00002ed`（库映射为ERROR/device not responding），
整体 `e000400e`；另外510包为 `e00002e7`/actual0，1包 `e000400e`/actual0。
没有把错误状态改成成功，严格 iso_payload_verified 保持false，exit1。
这意味着此前标准库的零长度确有观测盲区；不能追溯声称此前那次已有数据，
因为此前未保存缓冲/原生frame。

本次 Isoch `0E101421`，FrameID225/SIA0/IOC1/无ED；post0/URB387，
匹配code1/count0事件 `80023000 00000000 01000000 00078001`，
随后指针零code14/count0事件。hook只终结一次，report3/state COMPLETE，
没有取消、重投或启用UAC。剩余是解释实际包状态错误、空ring后事件与主机
接收窗口的关系，再验证错误清除/重启与100次串行；ED复用、持续串流及
总线波形仍未验证。Switch日志待回收。

### 原生接收 SD 回收与64-packet窗口准备

Switch logfile 已归档到 B-A7-lead4-native-20261001-224515。
运行时安装 result0、身份匹配，seq1/URB387/requested192/raw-count0/report3/
events2 与主机一致；SD四个文件哈希匹配，无新增错误报告。

为隔离长接收窗口与空ring的关系，保留同一 B/A7 lead4 补丁，下一轮
主机使用 `--packets 64`（原512）。该参数只改变主机接收窗口，仍提交一个
192byte device TD；原生 backend 新增计划起始 frame/interval/speed 记录，
便于对照 device FrameID 与非零packet索引。设备 patch、context、SIA、lead、
completion 均不改变；若数据帧落在窗口之外应报告未覆盖，不解释为硬件失败。

独立诊断库和标准客户端构建通过，实际callback拒绝零长度/错误packet及
buffer保存验证通过；不支持的窗口参数在访问USB前拒绝。新实验包
`private/packages-A7-lead4/Mac-ISO-window64-diagnostics.zip` CRC通过，旧512
诊断包保留；上轮工具manifest已复制到上轮run，保持证据可追溯。
SD保留原文件并安全推出。下一次连接使用短窗口，只提交一次、不重投。

### B/A7 lead4，64-packet窗口 — 2026-10-02 00:45

`private/runs/B-A7-lead4-window64-20261002-004503/` 保存原始frame、接收
buffer、stderr、工具manifest与独立payload-evidence。单次post0/URB387，
Isoch `3D001421`，FrameID976；controller仍为匹配code1/count0、指针零
code14/count0。hook终结一次，未重投或取消。主机64packet窗口仍整体错误
`e000400e`；packet43 status`e00002ed`/actual192，另外62包`e00002e7`/0，
1包`e000400e`/0。逐字节核对192byte图案、rawbuffer槽、原生长度均一致。
严格接收pass仍为false；窗口512→64没有消除packet错误。

原生计划frame_start=157025189，模2048为933；数据packet43对应
`(157025189+43)&7ff=976`，正好等于设备FrameID。该观测确认本次设备
调度与主机数据frame对齐，且数据位于接收窗口内部；不证明错误原因。
Switch启动日志待回收。

按原计划准备 lead8：新包 `private/packages-A7-lead8/`，B仍为652bytes，
只把FrameID提前量4改8，保持单TD/无ED/IOC1/SIA0/context/descriptor。
下一轮仍用64packet原生接收，先核对目标frame落在窗口内。客户端及IPS
构建成功；19项验证18通过、1项旧采样测试按变体跳过，ZIP CRC、hash及
lead manifest通过。尚未部署，等待读卡回收并替换。

### 短窗口日志回收与lead8部署 — 2026-10-02 01:05

64-packet/lead4 的 Switch logfile 已保存到对应run，Build ID/安装result0
一致，seq1/URB387/requested192/raw-count0/report3/events2 与主机相符。
旧部署四个文件hash一致，无新增错误报告。

B/A7-lead8 已拷入 SD，客户端、IPS、四个文件读回 SHA-256 均匹配，ZIP
CRC验证通过；disk4安全推出。旧lead4文件及logfile备份在
`private/deployments/20261002-010547-B-A7-lead8/`。
下次连接仍用64-packet原生窗口、只提交一个TD，保存主机计划frame、
完整packet状态/数据及controller事件；若目标frame不在窗口内另行标明。

### B/A7 lead8，64-packet窗口 — 2026-10-02 01:09

`private/runs/B-A7-lead8-window64-20261002-010938/` 保存原始记录和独立
payload-evidence。post0/URB387，Isoch `77A01421`/FrameID1914，匹配code1/
count0，后续指针零code14/count0；hook终结一次，未取消或重投。
主机packet38实际192byte，全部测试数据/rawbuffer/原生长度吻合。
host frame_start=158500692，`(frame_start+38)&7ff=1914`，与设备对齐，
目标在64packet窗口内。该packet仍`e00002ed`，整体`e000400e`，另外62包
`e00002e7`/0、1包`e000400e`/0；严格接收pass仍false。
lead4→8未消除错误，不能只凭code1称无错误传输成功。Switch日志待回收。

按既定矩阵准备lead16，单TD/无ED/SIA0/context与主机窗口保持不变，
包路径为 `private/packages-A7-lead16/`；等待实机前核对构建与静态验证。

lead16客户端和IPS已构建，B注入652bytes；19项验证18通过、1项旧采样
按变体跳过。客户端hash、lead manifest、ZIP CRC通过，尚未部署。

### lead8 SD回收与lead16部署 — 2026-10-02 01:12

lead8 logfile 已保存到 B-A7-lead8-window64-20261002-010938；Build ID/
runtime result0匹配，URB387/report3/events2 与主机相符，四个旧部署文件
hash一致，无新增错误报告。B/A7-lead16客户端和IPS已拷入，四个文件
读回SHA-256一致，ZIP CRC/manifest校验通过；disk4安全推出。
lead8文件及logfile备份在 `private/deployments/20261002-011227-B-A7-lead16/`。
下一轮仍用64packet原生接收，只提交一个TD，核对目标是否在窗口内。

### B/A7 lead16，64-packet窗口 — 2026-10-02 01:23

`private/runs/B-A7-lead16-window64-20261002-012345/` 保存原始记录和逐字节
payload-evidence。packet53实际192bytes/全部图案正确；host起始159347257，
`(start+53)&7ff=622`，与Isoch `26E01421` 的FrameID622相符。
post0/URB387；匹配code1/count0后为指针零code14/count0。packet仍
`e00002ed`，整体`e000400e`，其他62包`e00002e7`/0、1包`e000400e`/0；
严格接收false，终结一次，未重投或取消。Switch日志待回收。

lead4/8/16均在目标frame收到完整数据，同时出现同样packet错误。
准备最后一个既定lead32点，B单TD/无ED/SIA0仍保持；主机窗口扩为128
以覆盖可能超过64的目标位置，记录此窗口变化，不能声称只改变一个变量。
窗口512和64的lead4均有相同错误，可作为窗口比较基线。完成32点后不继续
增加lead，若错误仍相同则转向TD结束/空ring后续行为。新包路径
`private/packages-A7-lead32/`，待构建、静态验证及SD部署。

lead32客户端及IPS构建完成，B注入652bytes；19项验证18通过，1项旧
采样按变体跳过，manifest/client hash/ZIP CRC通过。尚未部署；下一轮
用128packet原生工具单次接收。

### lead16 SD回收与lead32部署 — 2026-10-02 01:32

lead16 Switch logfile 已保存到对应run，身份及运行时安装result0匹配，
URB387/report3/events2 与主机相符，旧文件hash一致，无新增错误报告。
B/A7-lead32客户端和IPS已拷入，四个文件读回SHA-256一致，manifest和
ZIP CRC校验通过；disk4安全推出。lead16文件及日志备份在
`private/deployments/20261002-013204-B-A7-lead32/`。
下一轮使用128packet原生窗口覆盖lead32目标，单次提交、不重投。

### B/A7 lead32，128-packet窗口 — 2026-10-02 01:33

`private/runs/B-A7-lead32-window128-20261002-013356/` 保存原始记录和独立
payload-evidence。packet68/native actual192、全部192byte图案正确；
host起始159958440，`(start+68)&7ff=1516`，与Isoch `5EC01421` 的
FrameID1516一致，目标在128packet窗口内。匹配code1/count0后仍为指针零
code14/count0，post0/URB387/report3，未重投或取消。packet仍`e00002ed`，
整体`e000400e`，其他126包`e00002e7`/0、1包`e000400e`/0，严格接收false。
lead4/8/16/32已完成：均收到完整数据且在对应frame，均有相同错误。
不再增加lead。Switch日志待回收；原completion复用、持续流、波形未验证。

### 下一实验：A8 retained completion

核对目标版本 `2a980→2c690`：原终结路径会收尾URB、调用资源释放函数、
报告完成；有后续URB时还可提交下一buffer。本实验只有一个URB。
这不是已经证实的packet错误根因。Linux Tegra device参考的单ISO IN
同样采用末TRB Chain0/IOC1/ISP0/TLBPC0，未据host算法改这些字段。

为了隔离软件终结，本轮准备B/A8：仍lead32、同一单Isoch TRB、128packet
主机窗口。匹配code1只记录`terminal=40000001`并返回，既不推进软件dequeue，
也不调用2a980；buffer/URB映射保留、拒绝重投、后续事件继续有界记录。
客户端将其标为RETAINED，不能冒充正常URB完成。采集结束且主机callback
已退出后显式CANCEL，验证终结再释放；若不确认则保留并要求重启。
错误事件800000xx路径不变。原始A7包保留，新包在
`private/packages-A8-retained/`，B注入628bytes，尚待验证及SD部署。

A8客户端和IPS已构建，20项验证19通过、1项旧采样按变体跳过；测试
实际执行成功事件、重复事件和后续code14，确认不调用manager完成、dequeue
不推进、重投拒绝且ring不改。错误锁存、原A/C路径和安装回退仍通过。
manifest/客户端hash/ZIP CRC通过。尚未部署，等待读卡回收lead32日志。

### lead32回收与A8部署 — 2026-10-02 01:46

lead32 Switch logfile 已保存到对应run，target/安装result0匹配，
URB387/report3/events2 与主机相符，旧四个文件hash一致，无新增错误报告。
B/A8-retained 已拷入 SD，lead32/retain-success manifest和IPS/client hash
校验通过，四个文件读回SHA-256一致，disk4安全推出。旧A7-lead32及日志
备份在 `private/deployments/20261002-014644-B-A8-retained/`。
下一轮128packet单次接收，观察成功事件保持`40000001`/RETAINED且没有
normal URB报告；先保存数据/原始事件，再单独CANCEL，确认report4终结。

### B/A8 retained，128-packet窗口 — 2026-10-02 01:50

`private/runs/B-A8-retained-window128-20261002-015021/` 保存原始frame、
buffer、payload-evidence、summary与独立cancel记录。packet65/native192bytes
图案完全吻合，packet仍`e00002ed`、整体`e000400e`；126包`e00002e7`/0，
1包`e000400e`/0。Isoch `3E301421`/FrameID995，匹配code1/count0后仍有
指针零code14/count0。terminal=`40000001`/RETAINED，URB387/status2，
没有正常终结/资源释放。故立即调用2a980收尾不是该packet错误的必要条件。
本次native start160943009 + index65模2048为994，设备995，相差1frame；
记录这一差异，不声称本次完全对齐；目标offset66仍在128窗口内。

数据/事件保存后仅执行一次CANCEL，exit0，URB387/status4，state FAILED
（取消终结），确认不再pending/retained。没有重投。Switch日志待回收。

下一轮 A9 比较Isoch+ED，仍lead32、单192byte TD、128packet窗口；成功
仍只记录并保留资源到取消。A为Isoch IOC0/Chain1+ED IOC1，C为双IOC；
B的无ED作为A8基线。新生成器 `--explicit-all` 将已验证FrameID数学用于
A/C；成功保留同样扩展到A/C，错误先到时仍锁存。为保持RX容量，等价
折叠context读取偏移及IOC常量，未改变发布顺序、Link/cycle或非ISO路径。
A660/B620/C660bytes，均在684bytes内；先部署A，每次重启只使用一个变体。

A9各客户端和IPS已构建，20项验证19通过、1项旧采样按变体跳过。
真实指令验证显式FrameID、首cycle最后发布、Link/wrap、A/C成功只等ED并
保留资源、重复事件、错误锁存和回退；各manifest/client hash/ZIP CRC通过。
尚未部署，等待读卡回收A8采集与取消日志。

### A8日志回收与A9 A部署 — 2026-10-02 01:58

A8 Switch logfile 已保存到对应run：target/安装result0匹配；单次提交
URB387，取消终结status4/events0，与主机cancel记录一致。取消清空诊断
邮箱不影响先前已经保存的host原始事件。旧部署文件hash一致，无新增错误
报告。A9 A（Isoch IOC0/Chain1 + ED IOC1）已拷入SD，lead32/retain-success
manifest及IPS/client hash校验通过，四个文件读回SHA-256一致，disk4安全
推出。A8文件及日志备份在 `private/deployments/20261002-015831-A-A9-ED/`。
下一轮128packet单次接收，观察ED/tag事件、包状态及buffer，再取消终结；
不把保留状态当成正常completion成功。

### A/A9 ED，128-packet窗口 — 2026-10-02 02:03

`private/runs/A-A9-ED-window128-20261002-020307/` 保存原始接收、buffer、
payload-evidence、summary及独立取消记录。packet67/native192bytes完全
吻合测试图案；packet仍为`e00002ed`，整体`e000400e`。另外126包
`e00002e7`/0，1包`e000400e`/0，不能算无错误的packet完成。
Isoch control=`6B101411`，FrameID1713，IOC0/Chain1；ED control=`1C21`。
native start161709677 + index67模2048为1712，与设备相差1frame。

两个原始事件依次为：
`A457D010 0000001F 010000C0 00078005`，ED=1、tag匹配
`0000001FA457D010`、code1、raw_count192；
`00000000 00000000 0E000000 00078001`，指针零、code14/count0。
本轮证明device接受Isoch+ED并产生可关联的ED成功事件；ED raw_count192
等于实际接收长度，但不能据单次观测推广remaining-length语义。
terminal=`40000001`，URB387/status2、RETAINED；未调用原终结路径，
因此尚不能声称legacy completion可复用。完整总线波形未验证。

保存观察后单独执行一次CANCEL，exit0，URB387/status4、state3，诊断
回到D1/events0；确认取消终结，没有重投。Switch日志待回收。
下一轮部署已构建验证的A9 C，保持lead32及128packet窗口，比较双IOC事件。

### A9 A日志回收与C部署 — 2026-10-02 02:10

Switch日志已保存到A9 A对应run，安装result0、BuildID、单次URB387提交
均匹配。需区分：Switch日志在显式CANCEL请求前已记录status4/events2，
之后主机CANCEL查询为status4/D1/events0；不能把前者改写为events0，
也不能将取消终结归因于后来的显式请求。保留全部时序供后续分析。
旧部署四文件hash一致，无新增错误报告。

已部署A9 C（Isoch IOC1/Chain1 + ED IOC1），lead32、retain-success，
客户端/IPS hash及ZIP CRC通过，四文件拷入后读回SHA-256一致，disk4
安全推出。A9 A及日志备份位于
`private/deployments/20261002-021008-C-A9-ED/`。
下一轮仍只提交一次192bytes，128packet接收窗口，保存全部原始事件后
单独查询/取消，不重投。

### A/A10 原completion，128-packet窗口 — 2026-10-02 02:36

`private/runs/A-A10-completion-window128-20261002-023620/` 保存原始host、
native frame、buffer、summary和payload-evidence。本次packet65实际192bytes
完全匹配，native仍`e00002ed`、整体`e000400e`，另126包`e00002e7`/0及
1包`e000400e`/0。Isoch control=`60501411`、FrameID1541；匹配ED事件
`6197D010 0000002C 010000C0 00078005`，code1/count192，随后仍有
`00000000 00000000 0E000000 00078001`，code14/count0。

原completion已实测返回URB387/status3、requested192/transferred192、
client COMPLETE、diag terminal1，区别于A9的保留状态。说明本次单TD可
复用原URB completion；只观察这一次终结，不推广为连续串流、一般残量
语义或无错误packet验收。summary通用legacy_completion_reuse_verified
仍为保守false，payload-evidence另记single_td_ed_completion_reuse_observed。
URB已经终结，不执行CANCEL、不重投。Switch日志待回收。
后续先核对Switch正常完成日志，再定位packet错误/code14与单TD后的
服务缺口关系；尚未进行100次重复、UVC开流回归或UAC。

### A10日志回收，准备无TD主机基线 — 2026-10-02

Switch正常完成日志已回收到A10对应run，URB387/status3/count192/events2
与主机一致；四个部署文件hash匹配，无新增错误报告。SD保留A10，不改
producer或描述符，已同步并安全推出。

下一轮先做无TD基线：新host `--receive-only --packets 128` 要求fresh
boot的IDLE/sequence0/URB0，只排主机ISO窗口，不发送TRIGGER或CANCEL。
保存原始callback/native状态和零初始化buffer，结束时再次核对设备IDLE；
有必要时仅取消主机transfer，并等待回调后释放。baseline退出0仅表示
采集完毕且无设备提交/无数据，不代表ISO成功，也不归一化native错误。
这用于比较空服务窗口的错误特征，尚不能推断现有packet错误根因。

标准及独立native host构建通过；native backend/static lib未改、manifest
更新receiver hash，旧run保留旧manifest。模式冲突及repeat拒绝检查通过，
真实callback错误/零长度拒绝及raw buffer保存测试通过。测试首次调用
漏传日志参数而断言退出，补传临时日志路径后通过，未涉及USB操作。

### 无TD基线及同次启动单TD对照 — 2026-10-02 02:55–02:56

`private/runs/A-A10-noTD-window128-20261002-025524/`：fresh boot设备
IDLE/sequence0/URB0，128packet接收，未发送TRIGGER/CANCEL。native整体
status0，128包均`e00002e7`/actual0，buffer全零；无需主机取消，自然回调
后设备仍IDLE。exit0仅为基线采集成功。原始记录和comparison已持久保存。

之后同次启动只触发一个TD，未重投：
`private/runs/A-A10-after-noTD-window128-20261002-025605/`。
packet63实际192bytes完整匹配，却仍`e00002ed`，整体`e000400e`；其余
126包`e00002e7`/0和1包`e000400e`/0。device FrameID1000/control
`3E801411`；匹配ED `F9F7D010 0000006E 010000C0 00078005`后仍有
零指针code14。URB387/status3/transferred192、terminal1；正常completion
再次观察到，无需device取消。没有第二次TD，Switch日志待回收。

基线说明空窗口本身不能充分解释整体`e000400e`：无TD时整体成功，有TD
时错误重新出现。不能从此推断SS packet结束、FrameID偏差或code14中
哪一项是根因；下一步调查有数据的服务周期/packet结束语义，而不是
用空窗口掩盖错误或提前宣布音频可用。仍未开始连续串流与UAC。

### 对照日志回收与A11 MPS256准备 — 2026-10-02

同次启动的Switch日志保存到after-noTD run及baseline共享日志，确认
唯一URB387/status3/count192/events2，四文件hash一致，无新增错误报告。

A11只将vendor ISO endpoint的MPS从192改为256；buffer/TRB length仍192，
interval4、SS burst/mult0、wBytesPerInterval192、lead32、A IOC/ED组合
及原completion路径不变。目的是比较length==MPS与length<MPS，结果
尚未观察，不能认定包结束语义就是根因。脚本mps仅允许192/256并在
manifest记录；客户端编译定义来自该manifest，producer校验相同MPS。
host允许这两个实验MPS且记录实际描述符，仍仅接收192，不修改原native
错误映射。公共API参数不变，不加额外TD、ZLP或UAC。

A11 A/C684bytes、B644bytes，原字节及容量校验通过，所有客户端及IPS
构建完成。22项验证20通过、2项不适用测试跳过；新增验证错误MPS拒绝
而不改ring、MPS256仍产生单192byte/TBC0/TLBPC0。标准及独立native
receiver构建通过、receiver manifest更新，旧run保留旧receiver hash。

A11 A已部署，client/IPS hash、ZIP CRC及四文件读回SHA-256通过，
disk4安全推出；旧A10及日志备份在
`private/deployments/20261002-030038-A-A11-mps256/`。
下一次仅提交一个192byte TD，128packet窗口，按actual状态确认终结或取消。

### A/A11 MPS256 单TD — 2026-10-02 03:02

`private/runs/A-A11-mps256-window128-20261002-030232/` 保存原始host、
native packet、buffer、summary、payload-evidence。主机实际descriptor
MPS256/interval4，controller context dword1=`0100002E`，确认修改生效。
TD仍192bytes，Isoch control=`42101411`、FrameID1057。packet71/native
actual192完整匹配，但仍`e00002ed`，整体`e000400e`；另外126包
`e00002e7`/0及1包`e000400e`/0。host frame1056，与设备差1frame。

ED事件`ABD7D010 00000026 010000C0 00078005`，tag匹配、code1/count192，
随后仍有零指针`00000000 00000000 0E000000 00078001`。URB387/status3、
transferred192、terminal1，原completion再次完成；无需取消，没有重投。
Switch日志待回收。

将payload变为小于MPS未消除错误，故不能用满包长度条件解释或修复当前
问题。仍未证明一般ISO残量、无错误packet或总线波形。后续应以HS/SS
交叉观察或原始device服务周期结束语义作进一步区分，不重复同配置。

### A11日志回收，准备HS对照 — 2026-10-02

A11 Switch日志已保存到对应run，target/安装result0、唯一URB387提交、
status3/count192/events2与主机一致，四部署文件hash匹配，无新增错误
报告。SD保留A11并安全推出，没有无依据修改controller字段。

下一轮使用USB2数据线或USB2 hub以High Speed连接，保持A11 MPS256、
192byte TD、interval4、lead32及128packet窗口。客户端及producer已允许
HS，host实际speed必须为3才能作为HS对照；若仍为4不应将其记录为HS。
此步骤依赖用户提供物理USB2路径，尚未实测，不预判结果。先核对实际
连接速度，再提交唯一一个TD，采集完成后按URB状态决定是否取消。

### A11 HS 单TD首次无错误接收 — 2026-10-02 03:10

提交前独立libusb查询actual speed3，确认High Speed；实验保持MPS256。
`private/runs/A-A11-HS-mps256-window128-20261002-031049/` 保存完整原始
数据、native记录、summary及payload-evidence。packet63实际192bytes、
native status0、整体status0，全部192bytes匹配；其余127包
`e00002e7`/0。host帧386，device FrameID387；记录该1frame差异，不据
成功结果删除差异。Isoch control=`18301411`，匹配ED事件
`07D7D010 00000036 010000C0 00078005`后仍有零指针code14。

URB387/status3/transferred192、terminal1；主机payload和原completion
均通过，exit0，无需取消。首次获得native packet及整体都成功的192byte
ISO数据。code14在HS成功时也出现，故不能单独将code14作为SS主机
错误的充分原因。SS失败与HS成功构成速度对照，尚不能排除线缆/端口
路径差异，也不能认定具体SS协议字段根因。总线波形仍未验证。

按原验收计划开始HS成功变体100次串行重复；每次等待正常完成/排空
事件，只有一个device TD在途，失败立即停止。尚非连续音频串流。

### HS 100次串行验收 — 2026-10-02 03:11

`private/runs/A-A11-HS-repeat100-20261002-031125/`，exit0，100/100
packet图案及URB正常completion通过；逐次独立核对native status0、
overall0、actual192、原始buffer和序号图案，payload-evidence记录100条。
每次仅一个TD在途，最后sequence100/URB3523/status3/transferred192。
仍有code14，不影响这轮主机接收。ring从3000到3c80，未回绕。

尝试另一次claim追加30次，
`private/runs/A-A11-HS-wrap30-20261002-031256/`，30/30通过；但ring重新
从3000开始、cycle始终1，故没有覆盖wrap。明确撤回该次的wrap目标，
改为同一claim串行130次。原始数据保留，不将30次标成wrap成功。

汇总工具先前把初始STATUS中的旧sequence100也算新attempt，修复为
仅统计有host transfer或result记录的sequence；30次摘要重算为30，
两个回归测试通过，原始日志不改。这是统计问题，接收工具exit0及实际
30个成功result未受影响。

### HS真实ring回绕验收 — 2026-10-02 03:14

`private/runs/A-A11-HS-wrap130-20261002-031402/`，exit0，130/130
native packet和原completion均通过；逐次核对native/overall0、192byte
图案及raw allocation，全部证据保存。sequence94的Isoch物理指针
`80023F60`/cycle1，下一TD sequence95为`80023010`/cycle0，均正常
接收及URB完成。已实际跨越F70 Link并翻转cycle；边界TD的ED跨到ring
起点，后续仍正常。wrap记录在payload-evidence，未将30次误标为wrap。

本启动共单TD1次、serial100、另serial30、同claim130，261个TD全部
主机数据及completion通过；仍是离散单TD，不是连续音频。最后URB
已正常终结，无需取消。下一步协作拔插USB2做disconnect/reconnect，
再做UVC开流回归及Switch日志回收。SS错误仍未解决，总线波形未验证。

### HS物理重连及UVC尝试 — 2026-10-02 03:17–03:19

用户拔插USB2连接后，再次独立确认actual speed3。
`private/runs/A-A11-HS-reconnect-20261002-031714/`：packet71/native及
overall0、192bytes完整匹配，URB8659/status3/transferred192，exit0。
ring回到80023000/cycle1，ED成功后仍code14；物理重连后可正常提交和
终结，无需取消。payload-evidence独立核对raw allocation。

AVFoundation只列出设备并选择`SysDVR-UVC Capture:none`，不打开其他
摄像头或音频、不保存视频。尝试720p30/nv12、5秒输出null，但20秒
timeout且stdout/stderr均空；子进程已kill/reap。无法确认开流/帧接收，
不将其写成UVC回归通过，也不从空日志认定视频回归。游戏状态及ffmpeg
相机权限需用户确认；设备列表与失败记录保留在reconnect run。

进程结束后单次ISO复查
`private/runs/A-A11-HS-after-UVC-20261002-031904/`，exit0，192bytes
packet及整体成功、URB8675/status3/transferred192，ED匹配后code14。
开流尝试后ISO仍正常；这不能代替视频与ISO同时工作的验收。两次TD
均正常终结，不取消、不自动追加。Switch日志待回收。

### 用户进入游戏后UVC复查 — 2026-10-02 03:20

用户确认进入游戏。
`private/runs/A-A11-HS-UVC-game-20261002-032021/` 保存开流尝试记录。
首个跨exec启动的子进程未在后续检查中存活，因此不能用它判定设备行为；
另以父进程全程在场的ffmpeg复查作为有效观察。指定同一Switch视频接口、
无音频、1280x720/30/nv12、输出null，完整等待20秒，仍无progress帧及
stdout/stderr。TERM未结束后KILL/wait回收，uvc_exit=-9。

帧未出现，按先确认视频再测共存的条件，没有提交新的ISO TD。
不能将其标为视频回归通过，也不能由空日志判定controller回归。请求
用户用此前能正常显示视频的软件做对照，确认游戏画面/相机权限；
Switch EP0/视频提交日志尚待读卡分析。未修改UVC链路。

### 用户确认UVC无画面后的只读诊断 — 2026-10-02 03:26

用户报告此前观看软件也没有游戏画面，UVC回归未通过，暂停推进UAC。
`private/runs/A-A11-HS-UVC-descriptor-20261002-032642/` 保存实际176byte
HS configuration及控制结果。wTotalLength176与返回长度一致，视频
interface1/alt0、Bulk IN地址0x82、MPS512存在，VS Header也指向0x82。
ISO仍为interface2/EP83/MPS256。正确视频端点0x82 GET_STATUS=0000，
未halt；Probe GET_CUR/48byte成功，Commit GET_CUR返回-9/PIPE。
interface1 GET_INTERFACE同样-9；需Switch日志解释，不能仅据此判定
硬件/代码根因。初次误查0x81返回-9，它不是视频端点，其结果不用于
视频判断；随后依据实际descriptor纠正为0x82。

没有SET_CUR、更改配置、endpoint reset或新TD。下一步必须回收现有
Switch logfile，核对控制请求、Commit处理、grc:d及Bulk提交日志，再
选择修复或隔离回归的实验。先保存证据，不将HS ISO成功当作视频成功。

### UVC日志回收，修复实验接口的EP0所有权 — 2026-10-02

189678byte完整Switch日志保存至UVC descriptor run，并复制共享启动日志
至HS单TD、100次、30次、130次、重连、UVC尝试及after-UVC各run。
部署四文件hash一致，无新增错误报告。UVC阶段多次Probe SET_CUR成功，
后续Probe GET_CUR在VC看到，VS有时已经看到下一SET_INTERFACE，未出现
任何Commit received/streaming started；最后显式Commit GET_CUR记录
EP0 write failed `0x25c8c`。此前成功ISO TD及URB报告均在完整日志中。

代码发现明确回归：_handleSetupPacket提前把ISO interface的广播setup
交给_handleIsoSetup，而该函数对wIndex不匹配请求调用StallCtrl；这会
错误地stall另一个interface拥有的共享EP0。原UVC两个interface对
不匹配请求均忽略。A12将ISO不匹配分支改为记录并返回，不发送stage、
不stall，不修改实际UVC协商或视频提交逻辑。该缺陷能够干扰UVC，
修复是否恢复实际画面仍待硬件确认，不宣称全部根因已排除。

测试从源文件抽取完整实际_handleIsoSetup并在C中编译、使用计数stub，
验证UVC Probe/Commit GET/SET、SET_INTERFACE、GET_INTERFACE均无
stall/数据stage/ACK/提交副作用；ISO STATUS仍响应，自己未知请求仍
stall。测试通过。A12所有客户端重新构建，A/B/C controller manifest及
IPS与A11逐字节一致，保留MPS256/lead32和HS已验证的producer/completion。

A12 A已部署，manifest/client/IPS hash、ZIP CRC及四文件读回SHA-256
通过，disk4安全推出。旧A11与日志备份在
`private/deployments/20261002-033233-A-A12-ep0/`。
下一轮重启进入游戏并经USB2连接，先确认UVC帧，再验证ISO共存；不
推进UAC，也不将软件测试冒充视频硬件验收。

### A12视频恢复，HS单TD复查 — 2026-10-02 03:35

用户连接后明确报告“视频恢复了”，支持EP0所有权修复有效。主机工具
只claim vendor interface2，不打开/关闭UVC观看接口。
`private/runs/A-A12-HS-video-coexist-20261002-033529/`：actual speed3，
packet82/native及overall0、192bytes完整匹配，URB387/status3/
transferred192、terminal1，exit0。匹配ED事件
`0217D010 0000006B 010000C0 00078005`，随后仍零指针code14。
原始buffer/native/事件/summary和payload-evidence均保存，无需取消。

视频恢复是用户观察；本次未独立抓取视频帧，不据连接时恢复自动宣称
整个ISO测试期间画面无中断，已请求用户确认。Switch日志待回收。
controller IPS与此前HS100次及wrap通过版本一致，当前仍为MPS256，
SS协议错误尚未在A12重测或解决。未进入UAC或continuous streaming。

用户表示首轮未注意画面，并授权再来一次。已保存该观察限制，首轮
不标为“视频期间无中断”。在用户观察时单次再次测试：
`private/runs/A-A12-HS-video-observed-repeat-20261002-033737/`，actual
HS，exit0，packet72/native及overall0、192bytes完整匹配raw allocation，
URB403/status3/transferred192。ED匹配code1/count192，随后仍code14。
没有更多重投、无需取消；等用户确认本次画面。实验包初版保留首轮
观察限制，最终包需纳入这次记录和最终视频反馈。

用户随后明确回答本次视频没有卡住、消失或明显中断；第二次run的
payload-evidence及video-observation已更新，标注来源为用户观察而非
独立帧抓取。HS最小ISO数据、原completion、100次串行、硬件ring回绕、
物理重连和本次UVC共存均已取得对应证据。A12 Switch日志仍待回收，
SS问题、endpoint reset恢复、连续串流/30分钟、UAC及总线波形仍未验收。

### A12最后日志回收与实验包归档 — 2026-10-02

9264byte完整Switch日志已保存到最后observed-repeat run，首轮共存run
保存共享启动副本。四部署文件hash匹配，无新增错误报告。日志确认
A12安装result0，两次video Commit received及grcdServiceBegin result0，
URB387和403均status3/count192/events2，与主机一致。ISO接口对UVC
wIndex1明确记录ignoring，没有EP0 write错误；EP0修复的硬件行为有
日志支持，用户同时确认画面恢复。

须保留限制：整个日志较早部分有73次Video transfer timeout及对应
Failed to send video frame，均在第二次（最后）视频Commit前。最后
Commit→URB403测试→末尾没有视频超时/EP0错误，且用户确认画面未中断。
日志没有时间戳，不据早期超时推断关闭观看软件或ISO根因，也不将整段
启动标为视频零错误。所有原始记录保持完整。

SD保持已校验A12，sync并安全推出。最终实验包包含A12补丁/客户端、
回退包、native host及源码、构建脚本/测试/研究笔记、HS原始记录与
最后Switch日志；排除固件模块和密钥。已验证的是HS离散单TD及相应
验收项，SS协议错误和连续串流/UAC仍为后续工作，完整波形未验证。

### C/A9 双IOC，128-packet窗口 — 2026-10-02 02:20

`private/runs/C-A9-ED-window128-20261002-022004/` 保存host日志、原始native
packet记录、buffer、summary、payload-evidence及独立cancel记录。
packet70/native192bytes完整匹配，SHA-256与A/B图案一致；native packet
仍`e00002ed`、整体`e000400e`，其余126包`e00002e7`/0和1包
`e000400e`/0。native start162726548 + index70模2048为730，设备
FrameID731，相差1frame，目标offset71在窗口内。

Isoch control=`2DB01431`，IOC1/Chain1。三个原始事件依次为：
`80023000 00000000 01000000 00078001`，Isoch地址匹配、ED0、code1/count0；
`0E17D010 00000078 010000C0 00078005`，ED1、tag匹配
`000000780E17D010`、code1/count192；
`00000000 00000000 0E000000 00078001`，指针零、code14/count0。
三个事件均有界保存，第三事件占用ED TRB快照槽，summary显式标明该替换。
terminal=`40000001`，URB387/status2/RETAINED；没有原completion资源释放，
成功事件未导致重复释放。显式cancel的前置查询仍为RETAINED，后置查询
state3/status4/D1/events0，exit0；没有重投。

A/B/C单TD数据均已在主机观察到；A产生ED成功事件，C产生Isoch和ED两个
成功事件，分别count0和192。三种变体仍有packet错误及code14，故不能
作为无错误串流或正常completion验收。下一步先回收C日志，核对ED
raw_count进入原completion的转换与所有权，再安排completion复用实验；
尚未开始100次重复、UAC或连续串流，总线波形仍未验证。

### C日志回收与A10 completion部署 — 2026-10-02 02:28

C Switch日志核对安装result0、目标BuildID、唯一URB387提交及取消
status4/events0，通过；当前四文件hash匹配，无新增错误报告。
完整日志及sd-collection已保存到C对应run。

核对目标模块2a980→2c690：w2为结果、w3为终结标志、w4为本次传输量、
w5为锁标志。2c690将传输量累加到URB+2c，与requested+20比较，终结后
设置status3并释放映射。A9 A/C ED成功raw_count192与主机实际192一致。
A10采用已有非retained路径，ED成功只调用一次
`2a980(manager,0x83,0,1,192,1)`，推进软件dequeue；plain成功仍等待ED，
错误仍锁存保留，重复事件不再调用。尚未据此宣称硬件completion已验证。

A10 A/C注入684bytes、B644bytes，严格容量检查通过。客户端及IPS构建
完成，21项测试19通过、2项不适用采样/retained测试跳过；新增真实指令
测试覆盖ED count192传参、C先plain后ED、重复成功与后续code14不重复
释放。manifest/client/IPS hash及ZIP CRC通过。A10 A已拷入SD，四文件
读回SHA-256一致，disk4安全推出，旧C备份在
`private/deployments/20261002-022851-A-A10-completion/`。
下一次只提交一个TD，lead32及128packet窗口不变，先保存原始事件/packet
和URB报告，再按实际状态决定是否需要取消；不重投，不进入UAC。


### A13 HS 16-TD有界连续帧实验，本地准备 — 2026-10-02

从A12单TD扩展到一个URB的16个独立Isoch+ED TD，而非跨帧chain一个TD。
仅HS/MPS256/bInterval4/lead32，FrameID每TD递增并11-bit回绕。16个
192byte测试payload逐包使用16-bit sequence+index，保持一个4096对齐buffer。
ED按实际ring位置匹配，支持247slot环与跨Link。bitmap防重复累计；全部
16个精确count192成功后，才调用原completion一次，传输量3072并推进dequeue。
任何匹配ISO/ED错误或ED长度异常锁存并保留URB，后续成功不得释放。
新的request54避免旧单包host/client误触发，SS在host/client/producer三层拒绝。

独立源码iso_burst_patch.S恰占684byte，保持原text padding、非ISO提交路径、
controller doorbell及descriptor patch。ISO2诊断保留bitmap/sum/first pointer/
terminal，因容量限制没有raw event/context capture，不能沿用ISO1解码。
原A12包/交付zip保留；本版未解决code14或SS问题，未改UAC。

实际AArch64指令测试覆盖全部247起点×两种cycle、FrameID跨2048、每TD
DMA/192byte/Chain/IOC及ED self-tag、首cycle最后发布、乱序/重复ED、
每packet错误与短长count保留所有权，拒绝忙状态/不支持长度/SS，及Bulk/
report ABI回归。接收callback C测试拒绝缺包、错误包、重复、host槽间隔、
overall错误和内容损坏；成功case覆盖16-bit sequence回绕。实际setup handler
C测试在单包与burst两模式验证EP0所有权、payload、提交长度、pending/retained
拒绝和burst SS拒绝。summary测试区分ISO1/ISO2并保留逐包证据。
A12原测试22项，20通过、2不适用跳过；新A13包和rollback构建完成。

产物private/packages-A13-burst/，待SD卡与USB2实机单次验证。当前仅是
16ms有界预排，未宣称持续串流、硬件完成量语义、视频共存或音频成功。


### A13部署与安全推出 — 2026-10-02 14:25（Asia/Shanghai）

SD VolumeUUID/外置disk4s1与上轮一致，部署前四文件SHA-256完全匹配A12。
完整备份客户端目录、SysDVR-ISO补丁目录以及当前2078byte A12启动日志至
`private/deployments/20261002-142508-A-A13-burst/`。本次日志确认A12目标
BuildID和runtime安装result0，没有ISO TD记录；未发现新增/变化错误报告。
同BuildID没有其他加载补丁。A13包manifest/client/IPS哈希核对通过。

仅替换包内四文件，写入临时文件并fsync后rename，sync后逐文件读回SHA-256
匹配。记录status=deployed_and_readback_verified，disk4已安全推出。
未运行A13实机实验、未宣称设备安装或16-TD调度成功。下一步完全重启后
用USB2连接，先不开视频，仅一次burst/128packet窗口，保存host/native日志。


### A13 HS实机单次成功，重复时出现接收槽间隔 — 2026-10-02 14:27–14:28

`private/runs/A-A13-HS-burst-20261002-142725/`：actual speed3，首次
3072byte URB387/status3/transferred3072，bitmapFFFF/actual3072/terminal1。
主机payload槽62..77连续，全部16个packet public/native status0、192bytes、
逐字节等于sequence+index，并与独立raw allocation核对。overall0/exit0。
其余112个无payload槽native E00002E7，原样保留，不宣称整个128slot零错误。

独立重复run `private/runs/A-A13-HS-burst-repeat16-20261002-142812/` 原计划
16轮，首次失败自动停止：seq1槽72..87、seq2槽85..100通过；seq3槽为75、
77..91，第一个和第二个payload间空一slot（76），故严格连续验收失败/exit1。
三轮全部16包收到且逐字节正确，native/public payload status0、overall0，
URB403/419/435均status3/3072及bitmapFFFF。没有DMA滞留，无需cancel。
累计4次burst（64个TD），最后首TRB偏移600，尚未碰到F70 Link。
不得将本轮标为ring回绕或稳定连续串流通过，也未进行重连、UVC共存或UAC。

原始JSONL/native记录/raw buffers/summary/payload-evidence均保存；主机槽空档
是原生逐包及allocation共同观察，不能由此确认device调度还是host侧归档
的根因。ISO2原版没有first TRB FrameID，亦无raw controller event。
已停止进一步实机提交，等待回收本次Switch日志。

下一实验A14保持lead32/MPS256/16-TD调度，新增首个已发布TRB的16byte快照
至ISO2 +48，以便将实际FrameID与host schedule及payload index作比较。
两处等价精简释放8bytes以容纳快照，仍684byte原RX padding：slot匹配用
(delta&31)==(EDflag<<2)，完成条件使用16次互异count192累加后sum3072。
duplicate bitmap与错误锁存不变。包为private/packages-A14-frame-snapshot/，
尚未部署或实机测试。第一优先是读卡核对A13安装/提交/完成及错误报告，
随后才安排A14时间基准诊断，不把空档归因于ring wrap。


### A13日志回收及A14部署 — 2026-10-02 14:32（Asia/Shanghai）

5635byte完整A13启动日志已保存至单次和重复run（共享启动副本）。目标BuildID、
runtime安装result0，四次URB387/403/419/435均requested/raw-count3072、
status3，与主机一致；events0是ISO2不计数的占位，不代表没有硬件事件。
未出现EP0写错误或video transfer timeout，也没有视频Commit/实际开流。
不能据此宣称视频共存通过。无新增/变化错误报告，四个SD部署文件与A13
manifest一致。接收槽空档的时序根因仍未确认，没有继续重投。

A13客户端、补丁、完整日志已备份至
`private/deployments/20261002-143206-A-A14-frame-snapshot/`。
A14客户端及匹配IPS四文件原子替换、sync、读回SHA-256通过，disk4安全推出。
A14仍lead32/MPS256/16独立TD；仅增加first published TRB快照及等价精简。
下一步重启、USB2连接，先一次burst，用FrameID快照与host start/index核对。
尚未宣称A14实机安装或调度通过。


### A14帧号快照及无新TD空窗口 — 2026-10-02 14:37–14:39

`private/runs/A-A14-HS-frame-20261002-143712/` 单次，actual HS。首发布
TRB为80030000 00000000 000000C0 30701411（type5/Chain/cycle1/SIA0，
FrameID775）；host start192025285低11bit709，声明首帧相对offset66。
raw allocation内16个payload均逐字节正确，native actual192，但首payload
在index65，随后index67..81；声明offset66..81，观察差为-1、随后15个0。
这只是设备FrameID与主机接收槽的模2048对照，未独立验证两时钟域关系或
总线波形，不能由此定论首TD硬件提前执行。

本轮16个payload native status E00002ED，整体E000400E/public status1，
35个无payload槽E000400E、77个E00002E7。严格data验收失败/exit1，不能将
raw内容吻合当作无错误接收。URB387/status3/transferred3072，bitmapFFFF/
actual3072/terminal1，正常completion通过、无DMA滞留。没有cancel或再提交。

新增host-only `--empty-window`：只在STATUS确认已有URB完整成功终结后允许，
前后核对同一state/seq/urb/count，仅开启host接收窗口，不发device trigger。
原`--receive-only`保持fresh-boot限制，pending/retained仍拒绝所有窗口诊断。
独立receiver编译于private/darwin-diag/iso-probe-empty-window-diag。
`private/runs/A-A14-HS-empty-window-20261002-143916/`：128个native
E00002E7/actual0、overall0、raw全零，设备仍相同COMPLETE URB387、无取消。
exit0表示只读基线采集成功，不是ISO payload验收；本次空窗口未复现数据
路径的E00002ED/E000400E，但这不足以确认device/host/时序哪一层是根因。

原始host/native/buffer/summary及payload/baseline evidence已保存。
A14 Switch启动/提交日志尚待读卡；当前暂停进一步TD提交，不进入UAC或
持续串流，也不安排未经验证的FrameID偏移补偿。


### A14日志回收，下一轮保持设备改主机调度 — 2026-10-02（Asia/Shanghai）

7682byte完整Switch日志已回收至A14数据run和empty-window run（共享启动）。
确认A14 marker、目标BuildID、runtime安装result0；仅一次seq1/URB387
提交与完成，requested/raw-count3072/status3，与主机一致。后续空窗口
没有新submit；无新增/变化错误报告，四部署文件hash匹配。没有视频Commit，
不能作为视频共存证据。设备侧日志没有解释主机packet错误/首包槽偏差。

本地SDK USB.h将E000400E命名为kIOUSBNotSent1Err（Transaction not sent），
IOReturn.h将E00002ED命名为kIOReturnNotResponding。这是错误符号解释，
不是对当前设备/host硬件根因的确认。查看实际isolated libusb1.0.30源码，
GetBusFrameNumber后仅frame+=4即提交ReadIsochPipeAsync；主机提前量尚未
单独验证。因此本轮不生成新的Switch补偿补丁，SD保持已验证hash的A14。

新增build_darwin_diagnostics.py --host-frame-lead 4/32/64 --out，默认4
保留原调度；重新从已验证hash的官方archive解包到独立目录，仅修改显式
host lead并增添queried_frame/configured_lead_frames日志，保留所有native/
overall错误及取消语义。host tool增加--trigger-delay-ms 1..500，默认仍10。
下一轮host提前32frame、trigger delay40ms、128slot、单次16-TD burst；
设备仍lead32/MPS256/相同A14代码。改变触发等待用于保持trigger位于已启动的
host窗口附近，明确记录两项参数，不把结果归因于其中一个参数已被独立隔离。

工具及provenance保存在private/darwin-diag-host32/，官方backend初始hash与
基线一致，静态独立构建、严格C编译、非法delay参数拒绝和接收callback
负例测试通过，未替换Homebrew libusb。实验尚未实机，包为
private/deliveries/A14-host32-timing-experiment.zip。
SD四文件保持A14，sync并安全推出disk4。下一步USB2重连，先运行一次host32；
不用再次部署设备补丁，不提前宣称首帧偏移或packet错误已修复。


### A14 host32单次通过，重复第三轮设备code23 — 2026-10-02 15:07–15:09

`private/runs/A-A14-HS-host32-20261002-150744/`：HS，host frame lead32/
trigger wait40ms/128slot，16个native/public status0、192byte逐字节匹配，
indices107..122，与首FrameID1194相对host start193856575的offset107及
后续递增全部对齐；overall0/URB387/status3/3072/FFFF/terminal1，exit0。
112个空槽E00002E7不计为payload错误。设备保持A14，不标为根因已解决。

`private/runs/A-A14-HS-host32-repeat16-20261002-150841/` 将host窗口扩大
256防止尾部截断，计划16轮，失败时停。seq1/URB403成功，indices97..112
与声明offset97对齐；seq2/URB419成功，indices112..127连续，整体相对声明
offset111晚一槽。收到数据的native/public状态全部0，内容逐字节正确。

seq3/URB435失败：只收到14包，indices109、111..123，首包对齐声明offset109，
后续收到的13包晚一槽，原生状态0/overall0但末尾两包没有收到；bitmap3FFF、
累计2688bytes、terminal80000017（锁存code23）、state RETAINED/urb_status2。
原URB完成量0，不把部分ED累计量当作完整终结量。首TRB偏移600，未到F70
Link，也未发生FrameID跨2048（首311），因此不是该轮ring/frame回绕证据。
计划16轮实际仅3轮，exit1。原始native/JSONL/raw buffer/summary/evidence保留。

显式取消独立run `private/runs/A-A14-HS-host32-cancel-20261002-150946/`：
前status2/RETAINED，后status4/state FAILED、同URB435，exit0，终结确认。
无新TD、无重投。所有Switch日志待回收，不能先宣称endpoint恢复通过。

下一实验A15只增加错误诊断，保持lead32/MPS256/16TD/HS、相同调度与ownership。
仍684byte：保留首control(FrameID/type/cycle)在ISO2 +60；首次匹配错误保存
byte offset(+4，可导出TD index)、raw MFI(+8，不再是event counter)及16byte
原始Transfer Event(+64)。terminal/bitmap/累计量保持原位，后续事件不覆盖
首次错误证据。slot modulo改为等价符号分支，ED构造合并64bit写入，接收匹配
做等价位运算以腾出空间。未做FrameID偏移补偿或改变producer调度。
A15 package为private/packages-A15-error-snapshot/，尚未部署或实机测试。
先读卡确认A14失败/取消及错误报告，再部署诊断；不进入UAC或持续串流。


### A14日志回收及A15诊断部署 — 2026-10-02 21:02

完整Switch日志15967bytes已保存到host32单次、repeat16和cancel三个run，
共享同一boot日志。A14 runtime patch result0；URB387/403/419均status3、
requested/raw-count3072；URB435在显式取消后status4/raw-count0，取消后无新提交。
日志不单独打印pending/error诊断，code23/bitmap3FFF证据来自此前STATUS；
不将取消终结视为endpoint恢复测试通过。相较A14部署基线无新增或变更错误报告。

A14内容目录及SysDVR-ISO补丁目录完整备份到
`private/deployments/20261002-210210-A-A15-error-snapshot/backup/`。
A15匹配NSP+IPS及另外两文件共四项写入并两次SHA-256读回核对，
目标卡UUID/外置设备身份核对通过，disk4已sync、安全推出、mount不存在。
NSP SHA256为da12853aea38bc77c4769167613640688d01ecc5562d4dce69656c1e07c9bd4e。
A15尚未实机；下一步重启后USB2、视频关闭，host32/40ms/256slot单次有界burst，
如出现错误读取首次raw event、MFI和匹配TD位置，不盲目重投。


### A15首次HS诊断：16包终结但一槽空档 — 2026-10-02 21:07–21:08

preflight run `private/runs/A-A15-HS-preflight-20261002-210750/`确认HS/MPS256/
interface2/EP83、初始IDLE/seq0/URB0。旧FRAMES请求输出verified0、result5977，
无有效MFI/MMIO且未提交TD：该handler要求旧REPORT_MARKER/iso_physical，
当前burst诊断布局不满足，不能据此判断硬件帧计数停止。保留原始结果，
不宣称本轮独立帧时基验证通过；此前实际MMIO时基验证不因此扩大结论。

单次 `private/runs/A-A15-HS-error-001-20261002-210828/`使用A15匹配接收器，
host lead32/trigger40ms/256slot。URB387状态3，requested/raw-count3072，
bitmapFFFF/累计3072/terminal1，完整终结，无需取消。
16包原生及public status0、actual192、overall0、按seq1..16逐字节匹配，
接收indices104、106..120：第1/2包间空一槽，因此data验收失败/exit1。
首TRB control 2C501411/type5/FrameID709，首虚拟地址00000066C5F7D000；
host queried215505469/start215505501，声明首槽104，首包delta0，后15包delta+1。
仅control快照符合A15格式；没有锁存设备错误，raw错误event/MFI/TD位置均不可用。
未重投、未进入重复或视频测试，不标为稳定或调度已修复。
原始native/JSONL/rawbuffer/summary/payload-evidence已保存，Switch日志待回收，
下一步读卡确认A15 runtime安装及完成日志/错误报告，再决定调度实验。


### A15日志回收，准备host64单变量比较 — 2026-10-02 21:24

完整3788byte Switch日志回收到A15 preflight及error-001两个run，共享boot日志。
A15标记及runtime patch result0确认，唯一提交URB387/requested3072/
raw-count3072/status3/diag-word2=0，与host终结一致，无追加提交。
SD四文件hash与A15部署manifest一致，无新增或变更错误报告。
采样请求在设备日志同样返回rc1759/mmio0，不当作有效MFI证据。
集合保存在`private/collections/A15-20261002-212433/`；SD四文件保持A15，
复核hash、sync并安全推出disk4，mount已消失。

下一实验仅host frame lead32改64，保持设备lead32/MPS256/16TD及host触发等待40ms/
256slot/单次/视频关闭；未修改任何设备补丁，不根据现有数据补偿FrameID。
工具`private/darwin-diag-host64/iso-probe-native-diag`从既有校验过的官方libusb
1.0.30源码独立构建。源码对比host32仅lead常数与对应日志常数改变，
原生及overall错误、取消语义不变，不替换Homebrew库。严格C编译、hash及非法
delay拒绝检查通过，experiment.json记录单变量、失败停及所有权边界。
host64尚未实机，下一USB2重连运行一次；不重复旧FRAMES无效请求。


### A15 host64：连续槽及FrameID对齐，但原生payload错误 — 2026-10-02 21:28

`private/runs/A-A15-HS-host64-20261002-212810/`：初始HS/MPS256/IDLE/seq0/URB0，
仅host lead32改64，trigger等待40ms/256slot/单次，设备仍A15。
Host queried216686655/start216686719，首control0BE01411/FrameID190，
声明首槽63。全部16包raw逐字节匹配，依序indices63..78，所有slot delta0，
本轮连续且对齐；但16包native status E00002ED、overall E000400E，
public transfer error，matched0/unexpected16/exit1，严格payload验收失败。
不将raw正确或连续槽当作原生成功，也不以一次对齐宣称稳定性改善。

URB387/status3/requested=raw-count3072、bitmapFFFF/actual3072/terminal1，
设备完整终结且没有锁存错误，A15 raw错误event/MFI/TD位置未产生。
不需取消，失败后无新TD/无重复，原始native/JSONL/rawbuffer/summary/evidence保留。
Switch日志待回收。host4、host32、host64已有不同成功/空档/原生错误表现，
继续增大host提前量不足以给出根因；下一步先核对设备日志，再检查设备TD调度
及原生接收的时间基准/错误语义，避免无依据FrameID补偿或进入UAC持续串流。


### host64日志回收及空闲接收对照准备 — 2026-10-02

host64完整Switch日志4574bytes已回收至原run，A15标记/runtime安装result0、
加载base7e1b200000与首TRB7e1b37d000对应，唯一URB387/requested及raw-count3072/
status3/diag-word2=0确认。SD四文件hash一致，无新增或变更错误报告。
集合路径见`private/collections/latest-A15-host64.txt`。A15文件保持不变，
重新核对目标卡及hash、sync、安全推出disk4并确认mount消失。

代码复核：设备MFI>>3+32、16TD FrameID逐次+1，host HS interval4按1ms推进，
未找到能仅凭当前观测确认的计算错误。两端数值对齐不等于独立时间基准或
总线事务验证，不据此归因或修改FrameID。
下一轮host64/256slot/fresh boot/视频关闭的--receive-only对照，不提交设备TD；
要求IDLE/seq0/URB0前后不变、rawbuffer零，并保存native/overall状态。
即使空闲对照无错误，也只能缩小条件，不能证明设备或主机根因。
计划保存在`private/darwin-diag-host64/idle-control-experiment.json`，尚未实机。


### host64空闲及同boot配对burst — 2026-10-02 21:47

`private/runs/A-A15-HS-host64-idle-20261002-214705/`：HS/MPS256/host64/256slot，
--receive-only无设备提交。前后IDLE/seq0/URB0及完整STATUS相同，raw49152byte
全零，256个native槽均E00002E7/actual0，overall0，exit0。
这是无数据窗口对照，不标为空槽status0，也不能确认有数据事务根因。

同boot `private/runs/A-A15-HS-host64-paired-20261002-214738/` 单次burst，
host64/40ms/256slot。Host queried1073862/start1073926；首control35101411/
FrameID849，声明槽75。16包native/public status0/actual192/overall0，内容全部
逐字节正确；indices75、77..91，首包delta0、后15包delta+1，一槽空档导致exit1。
URB387/status3/requested=raw-count3072/bitmapFFFF/actual3072/terminal1，
无设备锁存错误、无需取消，失败后无新提交。raw/native/summary/evidence保存。
先前host64连续槽但native错误，本轮native成功但空档，单一提前量尚不稳定，
不根据两次结果宣称修复或确认主机/设备根因。两run Switch日志待回收。


### 配对日志回收及主机耗时诊断准备 — 2026-10-02 21:50

同boot idle及paired两run完整Switch日志3042bytes已保存；A15安装result0，
base56e6200000与首TRB56e637d000对应，唯一URB387/3072/status3终结。
四文件hash一致，无新增或变更错误报告，SD保持A15且已sync安全推出。
集合见`private/collections/latest-A15-host64-paired.txt`。

下一步保留host64/40ms/256slot及A15设备参数，仅增加主机单调时钟日志：
submit前后、实际pause时长、trigger请求前后/rc、callback入口时刻。
时间戳缓存至trigger返回后统一写入，callback另写一行；该日志仍有观测开销，
不是总线trace，不等同于设备收包/doorbell时刻，也不改变原生错误判定。
工具`private/darwin-diag-host64-timing/`复用已校验host64静态backend，
源码/库/receiver hash记入manifest；严格编译及实际receiver负例测试通过，
callback timing JSON可解析。旧host32/64二进制保留。本版尚未实机。
不继续任意增大提前量或补偿FrameID；先验证实际host耗时与接收槽的关系。


### host64主机耗时实测：触发请求约62ms — 2026-10-02 21:54

`private/runs/A-A15-HS-host64-timing-20261002-215420/`：HS/初始IDLE/seq0/URB0，
A15/host64/40ms/256slot单次。实际submit0.503ms，pause45.057ms，
trigger control request62.198ms/rc0；callback入口距submit前321.776ms。
主机单调时钟日志为软件调用耗时，不代表device doorbell或总线时刻。
设置等待40ms不等于触发控制请求立即被设备处理，后续时间比较必须考虑实测
等待及请求耗时；本轮没有足够证据将这些耗时确定为原生错误或空档的根因。

Host queried1473010/start1473074，control27901411/FrameID633，声明槽71。
16包raw逐字节正确，indices70、72..86，第一包delta-1、后15包delta0，
仍有一槽空档；native16包全E00002ED/overall E000400E，验收失败/exit1。
URB387/status3/requested=raw-count3072/FFFF/actual3072/terminal1完整终结，
无设备锁存错误，不需取消，失败后无新提交。所有raw/native/summary/timing/
evidence已保存，Switch日志待回收。下一步日志确认后需设备提交时刻的诊断，
不可把host trigger返回时刻当作设备FrameID采样时刻或盲目做时序补偿。


### 耗时日志回收及A16设备时间诊断部署 — 2026-10-02 21:56–21:58

host64-timing完整Switch日志2654bytes已保存，A15 runtime result0、
base3ed4000000与首TRB3ed417d000对应，唯一URB387/3072/status3确认，
四文件hash一致、无新增或变更错误报告。日志及collection见
`private/collections/latest-A15-host64-timing.txt`，原run证据已更新。

A16仅客户端新增svcGetSystemTick记录：trigger handler入口、PostBufferAsync
前后、ACK前后，并输出tick frequency、seq及URB。保留原submit日志及ACK顺序，
新增时间汇总日志在ACK后输出；读取时钟/日志有观测开销，不等同于controller
MFI采样或doorbell时刻，host/device时钟不可直接相减。STATUS ABI保持不变。
A16 controller manifest/inject.bin/IPS与A15逐字节一致，所有调度/所有权参数
不变。真实setup handler的single/burst共享EP0/HS/保留DMA负例检查通过，
客户端及rollback构建、NSP hash、git diff检查通过。未重复测试未改的controller。

包`private/packages-A16-device-timing/`，匹配host64-timing工具及provenance已复制。
A16 NSP SHA256为91d87bae7b2963dcf89864164fc3307897f89a5e37363bdb80eee820d6e8baca。
备份A15完整content/patch目录后部署四文件，两次hash读回验证，sync安全推出。
部署路径`private/deployments/20261002-215816-A-A16-device-timing/`。
尚未实机；下一步重启、USB2/视频关闭、host64/40ms/256slot单次，
先保存host证据，再回收设备tick日志比较同侧处理耗时，不提前宣称时钟同步或修复。


### A16首次host64耗时诊断 — 2026-10-03 01:55

`private/runs/A-A16-HS-device-timing-20261003-015536/`：HS/MPS256、初始IDLE/
seq0/URB0，host64/40ms/256slot单次。提交0.394ms，实际等待43.738ms，
trigger67.118ms/rc0，callback入口距submit前321.373ms。
Host queried13132020/start13132084；首control17701411/FrameID375，声明槽67。
16包raw逐字节匹配，indices67、69..83，第一包delta0、后15包delta+1，
一槽空档；native16包均E00002ED/overall E000400E，严格验收失败/exit1。
URB387/status3/requested=raw-count3072/FFFF/actual3072/terminal1完整终结，
未锁存设备错误，无需取消，失败后无新提交。原始raw/native/JSONL/summary/
evidence保留，Switch安装标记及设备trigger/post/ack ticks尚待SD日志确认。
不能先宣称A16设备时间诊断已成功回收、时钟同步或根因已确定。


### A16设备时间回收及A17日志顺序实验 — 2026-10-03 01:58–01:59

完整8091byte设备日志已回收并关联唯一URB387，A16标记/runtime result0，
base2acca00000与首TRB2accb7d000匹配；URB/3072/status3完整终结，
四文件hash一致、无新增或变更错误报告。collection见
`private/collections/latest-A16-device-timing.txt`，原run设备时间证据已补全。
19.2MHz ticks：trigger252555631687、post-before252555632735、
post-after252555636555、ack-before252555848044、ack-after252555851345。
准备0.054583ms、post0.198958ms、post返回到ACK开始11.015052ms、
ACK0.171927ms、handler至ACK结束11.440521ms。
post-to-ack代码包含同步LOG以及状态赋值，测量区间也含调度等待，
只能定位区间，不能把11ms全部无条件归给日志IO；host67.118ms的剩余时间
亦不能仅凭未同步的两侧时钟细分到USB/设备轮询或host调度。

A17只将ISO submit LOG移至ACK完成后，保留原tick字段、提交/应答逻辑，
controller IPS/inject.bin及host64-timing receiver与A16逐字节一致，
lead32/MPS256/16TD/host64/40ms/256slot不变。实际handler测试新增断言：
submit log必须出现在该次post之后的ACK，single及burst均通过；既有共享EP0/
retained/HS拒绝检查仍通过。A17及rollback构建、hash及diff检查通过。

A16完整目录备份到`private/deployments/20261003-015924-A-A17-deferred-log/`，
A17匹配四文件部署、两次SHA读回校验、sync安全推出完成。
NSP SHA256 ebc33a75f68e0ec7f3e1d236543e44b62399e999f61158c3f74dec02f2e1bccc。
包`private/packages-A17-deferred-log/`；尚未实机。下一步重启USB2/视频关闭，
同参数单次，比较post-to-ack及host触发耗时和原生/连续帧验收，
不预先把日志顺序变化宣称为ISO故障修复。


### A17单次成功，重复首轮空档 — 2026-10-03 02:05–02:06

`private/runs/A-A17-HS-deferred-log-20261003-020540/`：HS/MPS256/初始IDLE，
host64/40ms/256slot。submit0.509ms、actual wait43.420ms、trigger58.075ms，
16包native/public status0/overall0、内容按seq1..16正确，indices69..84连续。
URB387/status3/requested=raw-count3072/FFFF/actual3072/terminal1，exit0，
单次严格验收通过。FrameID336/control15001411/firstTRB48e1b7d000。

通过后同boot计划16次有界重复：
`private/runs/A-A17-HS-repeat16-20261003-020604/` 实际仅1次即失败停止。
URB403/status3/3072/FFFF/terminal1，16包内容与状态均正确，overall0；
indices65、67..81，第1/2包间空一槽，严格连续帧验收失败/exit1。
FrameID393/control18901411/firstTRB48e1b7d200，尚未ring wrap。
不需取消，失败后无新提交。原始raw/native/JSONL/summary/evidence保存，
两run Switch日志和device timing待回收。一次成功不证明修复，A17稳定性未通过；
需回收post-to-ACK测量，再判断日志顺序变化是否实现预期延迟改善。


### A17设备时间回收，准备host请求256byte对照 — 2026-10-03 02:12

完整4962byte日志回收到单次和repeat两个run；A17安装result0，URB387/403
均status3/requested=raw-count3072，唯一两次提交，无新增或变更错误报告。
四文件hash一致，collection见`private/collections/latest-A17-deferred-log.txt`。
19.2MHz设备ticks显示：URB387 prepare0.082656/post0.055052/
post-to-ACK0.000365/ACK0.098177/handler总0.236250ms；
URB403 prepare0.051094/post0.114010/post-to-ACK0.000365/ACK0.089219/
handler总0.254688ms。post-to-ACK较A16约11.015ms显著缩短，但第二次仍空档，
因此日志后移实现了缩短该区间，尚未修复严格连续帧稳定性。
两侧时钟未同步，host约54–58ms请求剩余耗时不能直接定位。

下一实验保留A17 controller/host64/40ms/256slot，仅主机每slot请求长度192改256，
与MPS256比较；device actual及payload验收仍必须192，内容及原生/overall成功和
连续槽要求不放宽。此差异只是待验证条件，不预先认定为协议错误或根因。
host buffer/stride变为256，raw保存全分配，检测有效数据仍192；默认构建维持192。
工具`private/darwin-diag-host64-slot256/`复用相同静态backend；manifest记录
source/library/receiver hash。严格编译、实际callback在192及256stride两配置
均通过，丢包/重复/空档/原生错误/损坏及actual256均被拒绝。
尚未实机，旧接收器全部保留。SD保持A17，hash复核、sync安全推出完成。
下一USB2/视频关闭重连运行一次slot256对照，首个失败停。


### A17 host slot256：仍空档，native短包状态保留 — 2026-10-03 02:19

`private/runs/A-A17-HS-slot256-20261003-021905/`：初始HS/MPS256/IDLE，
仅host请求及stride256，payload仍192，host64/40ms/256slot单次。
submit0.674ms、actual wait43.601ms、trigger51.792ms/rc0。
Host queried14541482/start14541546，first control32901411/FrameID809，
声明首槽63；16包raw逐字节匹配，actual192/requested256，
indices63、65..79，第一包delta0、后15包delta+1，仍有一槽空档，exit1。
16个有数据native槽全部E00002E7/overall0；public映射为成功并matched16，
不能用public映射或raw内容宣称native status0，evidence明确native_payload_success=false。
这次与无数据slot的E00002E7/actual0不同，保留请求量与实际量以区分。
URB387/status3/requested=raw-count3072/FFFF/actual3072/terminal1完整终结，
无设备锁存错误、无需取消，失败后无重投。65536byte分配rawbuffer保留。
请求大小改256未消除空槽，不标为稳定或根因修复；device安装及timing日志待SD回收。


### slot256日志回收，转向控制器事件过滤审计 — 2026-10-03 02:23

完整4729byte设备日志已回收，A17标记/runtime result0及唯一URB387/3072/status3
确认，base76ac400000与首TRB76ac57d000一致。四文件hash一致，无新增或变更
错误报告。设备prepare0.054635/post0.153542/post-to-ACK0.000365/ACK0.129635/
handler总0.338177ms，日志后移后的短间隔维持，但host slot256仍空档。
collection见`private/collections/latest-A17-slot256.txt`；SD保持A17且已安全推出。

八组host/device对照汇总到`private/analysis/timing-and-slot-comparison.csv`，
控制器事件审计见`private/analysis/controller-event-audit.md`。
现有过滤在terminal非零、指针未匹配/空指针、错误parity及plain-success路径
不记录事件；完成FFFF只验证16个成功匹配ED，不独立验证总线服务时间。
因此“无锁存匹配错误”不能升级为“控制器没有任何错误事件”。未匹配事件也可能
只是空窗期间正常流量，不能直接作为故障。下一步先设计有界首两TD事件/MFI
诊断，证明684byte代码界限和ownership，host参数冻结，不再盲目切换常数。
本轮未部署新版本，也没有待立即运行的硬件实验。


### A18 有界事件 / MFI 审计：本地实现及实验包 — 2026-10-06

在独立 `iso_burst_audit.S` 实现 ISO3 布局，仍为 112byte diagnostics /
168byte STATUS，terminal/bitmap/actual/首 TRB 地址偏移不变。首两个成功 ED
保留 raw event + 软件 handler 入口的 MFI；另抓首个过滤和首个终结后事件。
匹配错误优先替换 TD1 槽并保留相对 offset、完整 raw event、MFI，后续事件
不能覆盖错误。过滤/终结后采样不改变原错误判定或 DMA 释放条件。
control0 是无效槽标记，其他字节可能陈旧，解码器忽略；字段复制非原子，
错误槽要求与 terminal 的 CC/异常长度一致，暂时的旧 TD1 不作错误证据。
过滤槽不记录具体分支或全量计数，忽略事件出现本身不确认为故障。

注入恰好684bytes，末地址0x69000，不跨 rodata；诊断写入止于 ring+0xFEF。
合并无副作用校验、FrameID 11bit 截断、byte 循环计数及 Link 等价拷贝，
report 复用已验证目标的原 copy 函数。机器码覆盖全部247起点/两种cycle、
wrap/FrameID、首 TRB 最后发布、不同成功 ED、重复/foreign/parity过滤、
任意 TD 的错误保留/拒绝重投、终结后事件、报告边界及寄存器恢复。
最终29个 unittest通过；随后解码器过渡状态标注的9个 summary 回归通过。
真实客户端 polling/EP0 测试、runtime installer 的预检/幂等/部分失败回滚通过；
A18 与 rollback 构建、NPDM校验、git diff检查通过。普通 ISO2 burst重建的
inject.bin与A17逐字节相同，未默认切换到新诊断。

主机冻结 A17 host64-timing 源码与原静态 backend，唯一接收语义改动为
ISO3 magic 兼容；库 SHA256 仍为
`b4f39ceba401c90f5ffe48d938a358a927b391edccab297a5b9c73e415298627`。
接收 callback 仍拒绝丢包、重复、空档、public/overall错误、损坏和 actual256；
原生 status0 仍需独立核对 native.log，退出0或 summary payload_passes 不替代原生验收。
非法CLI在USB初始化及日志创建之前拒绝。没有替换系统库或改变 host 提前量。

包 `private/packages-A18-event-audit/` 含 A/rollback、冻结接收器、来源manifest、
experiment.json和配套解码器；布局与操作见 `EVENT_AUDIT.md`。
A18 NSP SHA256：
`74733c766bdef91c71f262110787a90e0f288be153359d62d4ce690ceeff8fff`。
controller IPS SHA256：
`6eb0da2c9b124195f7d2bc47b8e32372a5efeb467b558a0618b113c05c7f8987`。

本轮未接触SD、未部署、未实机。上次设备记录为 A17。
下一步备份并匹配部署 A18，重启USB2/视频关闭，host64/request192/40ms/
256slot单次、首个失败停；保存native/raw/STATUS后回收Switch安装及tick日志。
MFI是软件处理事件时的计数，尚无总线trace或两侧时钟同步；本轮不宣称
空槽/原生错误根因已确定、稳定性已通过或可以进入 UAC/PCM 持续串流。


### A18 部署前读卡：仍为 A17，仅有启动日志 — 2026-10-06 22:28

SD 卷 UUID 与既有部署记录一致；四个部署文件 SHA256 全部匹配 A17，
同一 USB BuildID 仅发现一份 SysDVR-ISO IPS。完整 857byte `logfile.txt`
保存到 `private/collections/A17-pre-A18-20261006-222822/`，文件时间为
2026-10-06 21:01:50。确认 A17/HOS22.5.0、USB BuildID、runtime patch
result0/record21，日志止于设备初始化及 running，没有 ISO 提交、完成或
设备 timing 记录。本次读卡没有新增传输验收结果，也不是 A18 实机记录。

相对 10-03 02:23 回收基线，新增 3 个报告文件并完整保存：
10-03 15:29:16 的 `ovlloader` 崩溃文本、thread dump，以及一个 erpt 记录。
崩溃 Program ID `420000000007e51a`、模块 `ovlmenu`，Data Abort /
2168-0002；这些报告没有证明与 ISO 实验的因果关系。未发现新增
SysDVR 或 USB 服务 crash/fatal 报告。collection manifest 和 SHA256SUMS
记录读取证据；本轮只读 SD，卡保持挂载，A18 尚未部署。

下一步仍为备份并部署已验证的 A18，然后重启按冻结的
host64/request192/40ms/256slot/视频关闭条件单次采集，首个失败停。


### A18 拷入及安全推出 — 2026-10-06 22:32

按用户指令将 A18 部署到同一 UUID 的 SD 卡。完整包 SHA256SUMS 通过，
确认卡上四文件仍匹配 A17，完整备份模块目录、IPS 目录及 857byte 旧日志，
并在覆盖前校验 A17 回滚副本。四个 A18 部署文件逐个临时拷贝、fsync、
替换、sync 及读回 SHA256 校验全部通过；无新增或变更错误报告。
部署记录及 A17 备份位于
`private/deployments/20261006-223201-A-A18-event-audit/`，
指针 `private/deployments/latest-A18.txt`。`diskutil eject /dev/disk4`
成功，确认 SD 已不再挂载，manifest 记为 ejected=true。

部署完成不代表 A18 已通过实机验收。下一步插卡重启，USB2/视频关闭，
使用 A18 配套冻结接收器按 host64/request192/40ms/256slot 单次采集，
首个失败停，保留 native/raw/STATUS 并回收启动及设备 timing 日志。


### A18 首次 ISO3 实机采集：首两包仍空槽 — 2026-10-06 22:37

`private/runs/A-A18-HS-event-audit-20261006-223706/`：只读预检确认
HS/IDLE/seq0/URB0，冻结接收器及静态 backend hash 匹配部署包；
host64/request192/40ms/256slot，仅一次提交。描述符 MPS256/interval4。
视频关闭为约定条件，未由 STATUS 独立核验。submit0.501ms、actual wait44.788ms、
trigger55.506ms/rc0；queried29153477/start29153541，host lead64。

16 包 raw192bytes 逐字节匹配 seq1..16，全部有数据槽 native/public status0、
overall0；indices68、70..84，缺槽69。首 TRB control14901411/FrameID329，
声明首槽68，首包delta0、其余delta+1。严格连续性失败，exit1，首个失败停，
没有重投。自身 URB387/report387/status3/requested=raw-count3072，
ISO3 terminal1/bitmapFFFF/actual3072 完整终结，不需要取消。

ISO3 成功捕获 TD0/TD1 ED：指针分别为首 TRB+0x10/+0x30，
两事件CC1/ED/actual192，MFI2628→2644，模16384差16。
首过滤槽无效；首终结后事件为CC14/非ED/空指针/MFI2756。
MFI 仅为软件 handler 入口观测，不能当作总线服务间隔；终结后事件也不能
直接归因为早先空槽。没有匹配错误锁存，仍不证明全量事件或根因已确定。
冻结接收器 stderr 的旧标签 `events344986641` 实际对应 ISO3 首 TRB
control `0x14901411`，不能当作事件数；解码器明确 total_event_count_available=false。

raw/native/JSONL/STATUS、逐字节及原生状态证据、summary 和 SHA256SUMS 保存。
下一步回收完整 Switch logfile.txt，核对 A18 标记/runtime安装/唯一提交及
设备 ticks，再分析事件观测。A18 未通过严格传输或稳定性验收。


### A18 设备日志回收：安装及单次提交确认 — 2026-10-06 22:41

完整2767byte日志保存到
`private/collections/A18-event-audit-20261006-224129/`，并关联本次 run。
A18诊断标记、HOS22.5.0、目标USB BuildID及runtime result0/record21确认。
仅一次seq1/HS/length3072/rc0/URB387提交，随后自身URB387/status3/
requested=raw-count3072；diag-word2对应control14901411，与主机ISO3一致。
USB base5c67400000、首TRB5c6757d000，偏移0x17d000一致。
四个部署文件SHA256仍匹配A18，无新增或变更crash/fatal/erpt报告。

19.2MHz设备ticks：prepare0.050052/post0.213594/post-to-ACK0.000365/
ACK0.164010/handler总0.428021ms。post至ACK短间隔维持；设备处理耗时
不足0.5ms并未消除首两包间空槽，也不能用未同步的两侧时钟直接定位
host约55.506ms触发耗时。首两成功ED处理时MFI差16仍是软件观测，未证明总线间隔。

run证据解除设备日志/timing待回收标记，安装、唯一提交和终结与host关联通过；
严格连续性失败结论不变，无取消、无重投。SD文件未改动，保持A18，安全推出成功。
下一步基于这些冻结条件及ISO3快照，审计首两TD的帧调度和事件处理路径；
暂不更换主机常数，不把终结后CC14或MFI差直接升级为故障根因。


### A19 发布阶段诊断：原路径审计及本地验证完成 — 2026-10-06

复核原模块type1 ISO入口、`0x30700`事件循环/`0x30898` hook和`0x31C74`
doorbell tail/`0x31CDC` MMIO写入。事件循环可连续处理已有事件后更新dequeue，
ISO3入口MFI仍不能当硬件事件生成时间。producer保持全16TD建好、DSB、首cycle
发布、第二次DSB、原tail，未发现FrameID递增或ring回绕计算错误。A18首TD
FrameID329边界2632/handler MFI2628，次TD FrameID330边界2640/MFI2644；
这些算术比较不足以确认早发、晚发或根因，未据此补偿FrameID或调整常数。

A19 ISO4使用独立`iso_burst_phase.S`，注入仍684byte/止于`0x69000`。
0..71保留common header、首两成功ED及匹配错误优先替换TD1；72/76/80记录
选帧、发布前、发布后进入原tail前MFI，84为phase_valid。新提交先清sentinel，
保留字节不解释，decoder核对范围及FrameID关系；多字段报告仍非原子。
减少首过滤/终结后采样以满足原空间上限，过滤及DMA判定不变。三锚点只记录
软件阶段，额外读取可能影响耗时，末锚点没有记录实际doorbell写入时间。

29项A19本地测试通过：实际机器码读取顺序/247起点和两cycle/回绕/最后发布、
重复和foreign过滤、错误保留及拒绝重投、报告和寄存器ABI、STATUS/EP0真实
客户端路径、decoder无效及过渡状态、冻结receiver负例。原A18机器码9项回归
通过，默认ISO2/ISO3 inject.bin和IPS与A17/A18逐字节相同。runtime installer
22记录的预检/幂等/部分失败回滚、A19及rollback构建/NPDM检查通过。

冻结host64/request192/wait40/256slot接收器，仅增加ISO4兼容；静态backend
SHA256仍`b4f39ceba401c90f5ffe48d938a358a927b391edccab297a5b9c73e415298627`。
未放宽16个连续正确192byte payload/native/public0/overall0及自身终结URB验收。
包及操作说明见`private/packages-A19-publication-audit/`、`PUBLICATION_AUDIT.md`；
来源、验证日志和完整SHA256SUMS随包保存。NSP SHA256为
`63c3c964c201c52a85c3bf4d74f5e8d321d4c57f80ac47a565c9a39f2e2c85b3`，
IPS为`ffc46dd88242657785c1cee7f30c087ce0675e63f351965d1b607a4b5f1f761c`。

本轮A19未部署/未实机，SD当前未挂载，最后确认内容仍为A18。下一步匹配
部署A19，重启HS/视频关闭，冻结条件下仅一次采集，首个失败停、无重投，
保存native/raw/STATUS并回收设备安装/ticks日志。根因及稳定性仍未确认。


### A19 拷卡及安全推出 — 2026-10-07 16:44

按用户“拷卡”指令部署A19。同一SD UUID `37614F76-3E12-3470-B5C8-52B5A449C213`，
确认当前A18四文件SHA256匹配、相同USB BuildID仅一份目标IPS；A19包27文件
SHA256SUMS及A/rollback ZIP hash通过。完整备份A18模块/IPS目录、3292byte旧日志，
所有回滚文件逐一校验；四个A19部署文件以临时文件拷贝、fsync、替换、sync，
读回SHA256全部一致。相对A18回收基线15份错误报告，无新增或变更。

部署及A18备份位于`private/deployments/20261007-164456-A-A19-publication-audit/`，
指针`private/deployments/latest-A19.txt`，附deployment.json、备份及SHA256SUMS。
再次核对SD身份和四文件后，正常`diskutil eject /dev/disk4`成功，确认挂载点消失，
记录ejected=true/mount_gone=true。SD现为A19；已部署尚未实机，严格验收没有新增结果。

下一步插卡重启、USB2/HS/视频关闭，冻结host64/request192/40ms/256slot，只执行
一次A19 burst；首个失败停、无重投，保留native/raw/JSONL/STATUS。随后回收设备
日志核对A19安装、唯一提交、三阶段MFI和自身终结URB；仅pending/retained时取消。


### A19 首次 ISO4 实机：三锚点相同，首两包仍缺槽 — 2026-10-07

`private/runs/A-A19-HS-publication-audit-20261007-165130/`：只读预检确认
USB2/HS、fresh IDLE/seq0/URB0。A19包/冻结receiver及静态backend hash校验通过；
host64/request192/wait40ms/256slot，仅一次提交，MPS256/interval4。
视频关闭为约定条件，STATUS未独立核验。queried75855411/start75855475/lead64；
submit0.354ms、actual wait42.948ms、trigger60.977ms/rc0。

16个192byte raw全部逐字节匹配seq1..16，与JSONL的data_hex及native actual一致；
256条native记录完整，16个有数据槽native/public status0，overall0，其余raw槽全零。
indices72、74..88，缺槽73；首TRB control6BB01411/FrameID1723声明首槽72，
第一包delta0、后15包delta+1。严格连续性失败，接收器exit1，首个失败停，无重投。
自身URB387/report387/status3/requested=raw-count3072；ISO4 terminal1/bitmapFFFF/
actual3072完整终结，无需取消。stderr旧标签events1806701585对应control，非事件数。

ISO4的frame_select/before_publish/before_doorbell MFI均13533，phase_valid1，
范围及首FrameID关系一致；选帧相位5，编码目标MFI13784，最后锚点至目标
差251（模16384）。TD0/TD1 raw成功ED均CC1/actual192，tag为首TRB+0x10/+0x30；
软件处理MFI13778→13794，差16，相对编码帧边界差值-6/+2。
锚点未显示可分辨的计数变化，但非零耗时证明，也不包含原tail/门铃实际写入
时间；事件处理观测不是总线服务时间，报告仍非原子、计数可能回绕、两侧时钟未同步。
未确认空槽根因，也未通过严格传输或稳定性验收。

原始native/JSONL/raw/STATUS、单次命令/退出码、独立payload-evidence、解码summary、
摘要及SHA256SUMS已保存，指针`private/runs/latest-A19-run.txt`，CSV已追加本次记录。
ISO4运行诊断与A19部署相符；完整Switch启动/runtime安装和唯一提交/ticks日志仍待回收。
下一步读卡核验这些设备证据，再分析三个锚点及首两成功ED；保持无重投。


### A19 设备日志回收：安装及唯一提交确认 — 2026-10-07 17:01

完整2766byte日志保存到`private/collections/A19-publication-audit-20261007-170136/`，
关联A19 run并校验SHA256。A19/HOS22.5.0/目标USB BuildID、runtime result0/
record21（最后一条下标）/last-rc0确认，仅一次seq1/HS/length3072/rc0/URB387提交，
自身URB387/status3/requested=raw-count3072终结，diag-word2对应control6BB01411。
USB base178CA00000、首TRB178CB7D000、相对偏移17D000一致。

19.2MHz设备ticks：prepare0.050573/post0.232135/post-to-ACK0.000365/ACK0.120260/
handler至ACK0.403333ms。设备处理不足0.5ms、发布阶段三个MFI相同，仍未消除空槽；
未同步的两侧时钟不能直接分配host60.977ms trigger耗时的来源。四个部署文件
仍匹配A19，15份错误报告无新增或变更。SD文件未写入，安全推出，保持A19。
run解除Switch日志/timing待回收标记；严格连续性失败、无取消/重投结论不变。


### A20 原门铃tail前后诊断：本地完成 — 2026-10-07

A19末锚点在进入原`0x31C74` tail之前，未包围随后的检查和`0x31CDC` MMIO写入。
原tail读取x1并使用x0/x8/x9/x10，保持x5/x14/sp/callee-saved；正常移位endpoint
index并写doorbell后返回0，拒绝分支在移位/写入前返回1928C。A20从ISO producer
调用完整原tail后再读MFI，最后恢复调用者x29/x30/sp，保留原返回值；原tail字节
与MMIO写入不变，未新增全局hook。去掉A19发布前采样，仍三个读取、684byte RX。

ISO5 magic354F5349，common header/TD0/TD1-or-error及DMA所有权不变；72选帧MFI、
76原tail前MFI、80原tail后MFI、84保存tail返回时w8（正常EP7为700）；88..111保留。
新提交清marker，decoder只在700/范围/首FrameID关系一致时展示锚点。
拒绝分支marker为未移位index、无效；快照仍非原子，不能证明硬件接收门铃。
保留首cycle最后发布/两DSB/FrameID算法，调度和host64/request192/40ms/256slot冻结。

35项本地测试通过（32机器码/客户端/decoder，3冻结receiver）：247起点/两cycle、
三处真实读取顺序、原tail正常及拒绝的返回值、原字节/栈/LR/callee-saved寄存器、
过滤/错误保留/拒绝重投、报告边界、真实STATUS/EP0及receiver负例。ISO2/3/4的
inject.bin/IPS和A18/A19 receiver重建均逐字节相同。runtime installer22条记录
预检/幂等/部分失败回滚、A20/rollback构建和NPDM检查通过。

包及说明见`private/packages-A20-doorbell-audit/`、`DOORBELL_AUDIT.md`。
A20 NSP SHA256 `e0f0f7303ac6aaec4a86a3eb0ec4232a34ab6fdbaa072fbf222ccad0bb851007`，
IPS `c03272099fd321f8f842fb674f261116aede045aeb5439406a950ac98007e105`。
本轮A20未部署或实机，SD保持A19。下一步匹配部署A20并重启、HS/视频关闭，
冻结条件下一次采集。采样可改变执行时长，原tail前后差值只包围软件执行，
不提供精确MMIO或总线服务时间；缺槽根因及稳定性仍未确认。


### A20 部署及后续流程 — 2026-10-07 19:49

核验指定SD UUID和当前A19四文件，A20包27项SHA256、两ZIP及验证来源一致。
完整备份原模块/补丁目录及本次3529byte A19启动日志（runtime result0，无ISO提交）；
该日志来自另一启动，原A19 URB387测试日志保留在既有collection/run，不替换。
15份既有错误报告无新增或变更。A20四文件拷入、sync及SHA256读回通过，disk4正常
安全推出且挂载点消失。记录见`private/deployments/latest-A20.txt`及其deployment.json/
SHA256SUMS。A20尚未实机；下一步插回Switch重启，冻结条件下单次测试。

用户要求后续“读卡—研究—拷卡—推出”一步完成，流程见CARD_WORKFLOW.md。


### A20 首次HS单次：连续帧但原生状态失败 — 2026-10-07 19:54

fresh HS/IDLE/seq0/URB0预检确认。冻结host64/request192/wait40ms/256slot，
仅一次提交。16包seq1..16、exact192 raw逐字节正确，indices68..83连续，
首FrameID1568/control62001411声明首槽68，全部delta0。但所有16包native
E00002ED/public1、overall E000400E/transfer1，严格验收失败，receiver退出1。
自身URB387/report387/status3/requested=raw-count3072，ISO5 terminal1/bitmapFFFF/
actual3072完整终结，无取消和重投。不能把连续raw观察当作错误已解决。

ISO5门铃marker700及header关系有效，选帧/原tail前/后MFI均12290；
首编码边界12544领先末锚点254tick（模16384）。TD0/TD1成功ED的MFI12546/12554，
差8tick，相对编码边界均+2。原tail软件路径已观测，但零计数变化不是零延迟
证明，也不证明控制器接受门铃时刻。报告非原子、两侧时钟未同步，根因未确认。
submit0.505ms/实际等待45.025ms/trigger53.842ms、rc0；视频关闭未由STATUS独立验证。

原始native/JSONL/raw/STATUS/preflight/命令/退出码、解码及独立逐包证据保存并
核验17份SHA256，指针`private/runs/latest-A20-run.txt`；比较CSV已追加。
ISO5运行诊断与部署相符，完整Switch启动/runtime安装/唯一提交/ticks日志仍待读卡。
下一步插读卡器回收日志，按CARD_WORKFLOW.md继续研究、验证下一版、拷卡和推出。


### A20 设备日志回收及 A21 上下文诊断部署 — 2026-10-07

完整5408byte A20日志已回收：HOS22.5.0/目标BuildID/runtime result0/record21
（最后下标，共22记录）、唯一seq1/HS/length3072/URB387提交与status3/3072終结
及control62001411一致。USB base14E7400000、首TRB14E757D000、偏移17D000。
prepare0.052188/post0.221146/post-to-ACK0.000417/ACK0.0925/handler-to-ACK
0.36625ms。四部署文件仍匹配A20，15份既有错误报告无新增或变更。
连续raw但native报错的结论不变；三个相同MFI读数不能确定总线时序/错误根因。
run与collection校验及设备日志待回收标志已更新。

审计原30B50 installer及Linux Tegra XUDC字段定义，确定context表来自
controller+22050，条目index7*64。A21在32个transfer TRB组装后、第一cycle
发布前只读该条目前32bytes；不写原context，也不改原installer/门铃MMIO。
ISO6 common header/首两成功ED或首错误不变，72选帧MFI、76 context_valid1、
80..111原context dword0..7；无效标记/不一致首FrameID不解释陈旧words。
保留原始不匹配配置作为证据，解析类型/MPS/burst/mult/原interval/MaxESIT、
dequeue/DCS/avgTRB/edtla/sequence/partialTD/cerr/progress。DMA上下文和report
非原子，不从sequence推断已确认DATA PID，也不当硬件接受或服务时间。

移出A20的tail前后两个MFI采样，恢复原tail尾跳转，原stack/LR/返回值不变。
lead32/MPS256/16独立TD/FrameID算法/两DSB/首cycle最后发布及DMA规则冻结；
代码680bytes/end68FFC，位于684bytes RX padding内，report112/STATUS168。

39测试通过（36机器码/客户端/decoder，3冻结receiver），247ring起点/两cycle、
真实快照在gate前、原context不被写入、stale拒绝、错误所有权与原调用栈均验证。
ISO2/3/4/5 inject/IPS及A18/A19/A20 receiver回归逐字节一致；runtime installer
22记录预检/幂等/部分写入与readback失败回滚、A/rollback构建和NPDM通过。
包28文件及两ZIP核验，位于`private/packages-A21-context-audit/`。
A21 NSP SHA256 `37267d8bac5989a26e815e129f348d834985c89741c31dd5eb17137eee6c7571`。
部署记录`private/deployments/latest-A21.txt`：2026-10-07T20:09:09.706612+08:00完成A20目录/日志
备份、四文件拷入及SHA256读回，2026-10-07T20:09:10.552677+08:00正常推出disk4并确认挂载消失。
A21尚未实机；下一步插回Switch重启，USB2/HS/视频关闭、host64/request192/
40ms/256slot/单次；验收全部native/public0且连续，完成URB不取消、不重投。
说明见CONTEXT_AUDIT.md；完整执行用户约定读卡—研究—验证—拷卡—推出。


### A21 首次HS单次：配置匹配但首两包缺槽 — 2026-10-07 20:13

fresh HS/IDLE/seq0/URB0预检通过，MPS256/interval4，host64/request192/wait40ms/
256slot/单次。16包seq1..16、exact192 raw逐字节正确，native/public/overall全0。
indices80、82..96，缺槽81，首FrameID1853/control73D01411声明首槽80：首包
delta0，其余15包+1，连续性失败/exit1。自身URB387/report387/status3/3072，
ISO6 terminal1/bitmapFFFF/actual3072完整终结，无取消和重投。

ISO6 context_valid1/MFI及首FrameID关系一致，发布前context words
00040001 0100002E 80023001 00000000 01000C00 00000000 000C0000 00000000。
state1/type5/MPS256/interval4/maxburst0/mult0/MaxESIT256，配置匹配；CERR3/
cerr_count3、avgTRB3072、dequeue80023000/DCS1；edtla/sequence_byte/partial_td/
data_offset/num_trbs均0。选帧MFI14571，首编码边界14824，领先253tick（模16384）。
TD0/TD1成功ED软件MFI14819/14835，差16tick，相对编码边界-5/+3。
配置快照未显示这些字段异常，但DMA及report非原子、缺总线trace和时钟同步，
不能据此定论空槽原因或实际服务时间，也不从sequence推断DATA PID。

submit0.976ms/实际等待45.026ms/trigger66.773ms、rc0。视频关闭为约定条件，
STATUS未独立验证。ISO6运行诊断与部署一致，完整Switch启动/安装/唯一提交/ticks
日志待读卡。原始native/JSONL/raw/STATUS/preflight/命令/退出码、summary/独立
逐包证据及17文件SHA256已核验，指针`private/runs/latest-A21-run.txt`，
比较CSV已追加。下一步插读卡器，按约定回收日志并研究、验证下一版、拷卡和推出。


### A21 设备日志回收及 A22 调度对照部署 — 2026-10-07

完整5654byte A21设备日志已回收，SHA256与卡上相同：HOS22.5.0/目标BuildID、
runtime result0/record21（最后下标，共22记录）、唯一seq1/HS/length3072/URB387、
status3/raw3072和control73D01411均与主机run一致。USB base493CE00000、首TRB
493CF7D000/偏移17D000。prepare0.052865/post0.236927/post-to-ACK0.000365/
ACK0.177969/handler-to-ACK0.468125ms。四文件匹配A21，15份既有错误报告无新增
或变更；run已追加设备日志证据并核验20文件SHA256，collection/run/deployment
待回收标志已清除。缺槽81及首包对齐、后15包+1的结论不变，配置快照不确定根因。

A22检验后续TD逐帧指定FrameID是否与首两包空槽有关：TD0保留显式lead32/SIA0，
TD1..15改为SIA1/FrameID0。Linux Tegra XUDC设备驱动的SIA1/FrameID0用法提供参考，
不证明HOS的混合策略可行；Intel主机规范不作为设备控制器契约。完整依据及源链接见
FOLLOWUP_SIA.md。两条循环指令等长替换，其余代码、symbols和21个IPS记录相同。
ISO6上下文/首两ED/错误优先、16独立TD、192bytes、MPS256、gate/两DSB、原tail、
report112/STATUS168及DMA所有权冻结，代码仍680bytes/end68FFC/上限69000。

43项测试通过（40核心、3冻结receiver），247起点/两cycle、8microframe相位和FrameID
回绕、首包显式/后15TD SIA、两指令差异、错配拒绝、上下文只读、原调用栈、共享EP0
及错误保留均验证。ISO2..6 inject/IPS和A18..21 receiver重建逐字节一致；A22 receiver
与A21完全相同。runtime安装22记录预检/幂等/部分写入/readback失败回滚通过，A/rollback
构建、NPDM及28+6文件/两ZIP核验通过；包位于`private/packages-A22-followup-sia/`。

已备份A21模块/补丁目录及本次日志，四文件匹配写入并sync/SHA256读回。
部署`20261007-203332-A-A22-followup-sia`，20:33:33.827541+08:00正常推出disk4并确认
挂载消失，记录指针`private/deployments/latest-A22.txt`。NSP SHA256
8b1e6f5006b3d505a9449f142488e7c6c25397a2dd281a584fa403cd02866f70，IPS SHA256
baa69cabe05d2ac1fbcf05aa47fbac810cbb6892056fb225ecff0c9c7eb15904。
A22尚未实机；下一步插回Switch重启，USB2/HS/视频关闭、host64/request192/40ms/
256slot单次。ISO6不能单独辨别A21/A22，须保留配套文件哈希和A22启动标记；严格验收
仍需全部native/public0且连续。完成URB不取消、不重投，完整读卡流程已完成。


### A22 首次HS单次：连续raw但原生状态失败 — 2026-10-07 21:44

只读fresh HS/IDLE/seq0/URB0预检通过。冻结host64/request192/wait40ms/256slot，
仅一次提交。16包seq1..16、exact192 raw逐字节正确，indices66..81连续，无缺槽。
全部16包native E00002ED/public1，overall E000400E/transfer1，严格验收失败，
receiver退出1。首FrameID955/control3BB01411推导首槽67，全部相对首FrameID加
ordinal的1ms参考槽delta-1。后续SIA TD无显式FrameID，参考差值不能当作逐TD编码
或总线服务时间。自身URB387/report387/status3/requested=raw-count3072，ISO6
terminal1/bitmapFFFF/actual3072完整终结，无取消和重投。

ISO6 context_valid1、MFI与首FrameID关系一致，context原始words
00040001 0100002E 80023001 00000000 01000C00 00000000 000C0000 00000000。
state1/type5/MPS256/interval4/maxburst0/mult0/MaxESIT256，配置匹配，CERR3/
cerr_count3、avgTRB3072、dequeue80023000/DCS1，edtla/sequence_byte/partialTD/
data_offset/num_trbs均0。选帧MFI7387，首编码边界7640，提前253tick（模16384）。
TD0/TD1成功ED软件MFI7632/7640，差8tick，相对首FrameID和下一1ms参考边界均-8。
DMA上下文/report非原子，时钟未同步，未确认总线DATA PID或根因。

submit0.888ms/实际等待45.024ms/trigger52.773ms、rc0。视频关闭是约定条件，
STATUS未独立验证。部署配套NSP/IPS和receiver哈希已核验；ISO6不能单独辨别
A21/A22，完整A22启动标记/runtime安装/唯一提交/ticks日志待读卡。
原始native/JSONL/raw/STATUS/preflight/命令/退出码、summary、独立逐包证据及
17文件SHA256已核验，指针`private/runs/latest-A22-run.txt`；比较CSV已追加。
下一步插读卡器回收日志，再按约定研究、验证下一版、拷卡和正常推出一次完成。


### A22 日志回收及 A23 interval1 对照部署 — 2026-10-07

22:18完整4948byte A22日志已回收，SHA256与卡上相同。A22启动标记/HOS22.5.0/
目标BuildID、runtime result0/record21（共22条）、唯一seq1/HS/URB387提交和
status3/3072终结及首控制字3BB01411匹配主机run。模块base73F9A00000、首TRB
offset17D000正确；prepare0.056146/post0.191615/post-to-ACK0.000365/ACK0.173698/
handler-to-ACK0.421823ms。四文件匹配，15份既有报告无新增或变更。
run20/collection2文件SHA256已更新，指针`private/collections/latest-A22.txt`。
raw连续但全部native E00002ED/overall E000400E的严格失败结论不变，根因未确认。

A23检验HS服务节奏是否参与缺槽/原生错误，将bInterval4→1，8microframe→1（125µs）。
首包显式lead32/后15TD SIA1、MPS256、16 TD/ED、192byte payload、gate/两DSB/
原门铃tail/context installer及所有权保持A22。仅68D70输入interval比较与68DAC
ISO7标记两指令改变；680byte/end68FFC/其余21 IPS记录和符号相同。
SS描述符仍interval4，burst仍拒绝SS。ISO7复用112byte report/168byte STATUS，
context解码期望interval1，FrameID仍是1ms标签、每帧8名义采集槽；快照非原子。

原256槽在125µs下只覆盖32ms，名义host64起点下将在A22推导的首包时刻前结束。
A23扩大为960槽/120ms，名义提交后64..184ms，保留host64/request192/40ms/单次。
这是有意的第二项测量调整，不能作为严格单变量因果证明，覆盖推算也未独立同步时钟。
接收器仅ISO7兼容/interval1检查/CLI上限及提示修改；callback、原生错误判定、取消/
定时和静态backend保持冻结。高槽索引和末端有效包仍必须满足全部严格条件。

47项测试（核心43/接收器4，无跳过）通过，涵盖256输入interval、8相位/帧回绕/
两cycle、实际HS/SS描述符体、ISO7非原子/错误优先规则、960槽184320byte原始buffer
与indices520..535及944..959、缺包/重复/缺槽/原生错误/损坏/长度异常拒绝。
ISO2..6/A22 inject/IPS、A18..22 receiver重建逐字节一致；A23receiver有明确的窗口/
interval适配。22记录安装器预检/幂等/混合/部分写入/readback失败回滚通过，A/rollback
构建/NPDM及28+6文件/两ZIP校验通过。见[INTERVAL_EXPERIMENT.md](INTERVAL_EXPERIMENT.md)。

部署`20261007-224645-A-A23-interval1`已核验指定SD身份和旧A22四文件，备份完整
模块/补丁目录及4948byte日志后匹配拷入A23，sync与四文件SHA256读回一致。
22:46:46.798593+08:00正常推出disk4并确认挂载消失，无新增错误报告。
记录`private/deployments/latest-A23.txt`；NSP SHA256
`e3bcec30c06e67ca3ce61db5740d99aa63e587206653e45c7a7e3a25b1eccb7d`；IPS SHA256
`80991e082dda79da38f016b635715cec0bae4ec7c4963820a769cde17280416f`。
A23未实机。下一步插回Switch重启、USB2/HS/视频关闭、host64/request192/40ms/
960slot只执行一次burst；保存全部证据，完成URB不取消/不重投，再读卡确认ISO7/
A23完整启动及提交日志。软件MFI和context不能证明硬件服务时间、DATA PID或根因。


### A23 首次HS单次：16包连续且原生状态通过 — 2026-10-08 00:01

已验证配套包/接收器/冻结静态backend哈希。只读预检确认HS、EP83/interval1/MPS256，
fresh IDLE/seq0/URB0。host64/request192/40ms/960slot/名义120ms窗口，仅一次调用/
提交。16包seq1..16、exact192 raw逐字节正确，indices456..471连续；全部有效包
native/public0、overall0，严格验收通过，receiver退出0。完整184320byte raw保存，
其余槽全零。960条native记录均保留，944个空槽actual0/status E00002E7，未归一化。

自身URB387/report387/status3、requested=raw-count3072，ISO7 terminal1/bitmapFFFF/
actual3072完整终结，无取消/重投。首FrameID808/control32801411，按8槽/帧换算
声明首槽456，所有payload相对该首槽加ordinal的delta0。后15TD使用SIA，无显式
逐TD FrameID，因此参考差值不能证明逐TD编码或总线服务时刻。

ISO7 context_valid1/选帧关系一致、配置匹配，context words：
00010001 0100002E 80023001 00000000 01000C00 00000000 000C0000 00000000。
state1/type5/interval1/MPS256/maxburst0/mult0/MaxESIT256、CERR3/cerr_count3、
avgTRB3072/dequeue80023000/DCS1，edtla/sequence_byte/partialTD/data_offset/num_trbs0。
选帧MFI6215，首编码边界6464，领先249tick（模16384）；TD0/TD1成功ED软件MFI
6464/6465，差1tick，相对首FrameID和下一125µs参考边界均0。快照非原子、时钟未同步，
不证明DATA PID或根因。submit1.323ms/实际等待42.054ms/trigger45.932ms、rc0。

原始native/JSONL/raw/STATUS/preflight/命令/退出码、summary和独立逐包证据已保存，
指针`private/runs/latest-A23-run.txt`，SHA256核验及比较CSV已更新。ISO7和interval1
运行配置已观察，完整A23启动/runtime安装/唯一提交及ticks日志待读卡；视频关闭
是约定条件，STATUS未独立验证。此次仅单次通过，稳定性未验收；同时调整的采集窗口
也阻止将结果单独归因于服务间隔。下一步回收完整Switch日志，再确定后续验证。


### A23 完整日志核验及复现阶段准备 — 2026-10-08

00:14完整5228byte日志已回收，SHA256与卡上相同：
`a3798921faacaafe21e1f82bb796d7eda511dce6966d282d80d7752550d3063f`。
A23 HS ISO7 bInterval1启动标记、HOS22.5.0/目标BuildID、runtime result0/record21
（22条）、唯一seq1/HS/3072/URB387提交及status3/3072终结、首控制字32801411
全部匹配主机证据。模块base122600000、首TRBoffset17D000；prepare0.048750/
post0.107813/post-to-ACK0.000365/ACK0.164167/handler-to-ACK0.321094ms。
完整日志包含连接/断开与共享EP0的非目标接口忽略记录，没有额外ISO提交或取消。
四文件匹配A23；15份既有错误报告无新增/变更，运行revision身份已确认。
run20/collection3/deployment11文件SHA256已更新，指针`private/collections/latest-A23.txt`。

本次16包单次严格成功已得到完整日志支持，保留A23二进制和冻结参数；47项既有
本地验证的源码哈希及包校验保持一致，无代码变更、无重复拷卡或额外USB测试。
下一阶段先做另一独立启动后的单次复现，host64/request192/40ms/960slot/repeats1。
暂以三个独立启动各一次为复现检查（已确认第一轮），每次等用户发出“测试”。
首包索引/具体FrameID/MFI不能硬编码为首轮值，仍核验连续16包、全部有效包native/
public0、overall0、exact192、自己的URB及ISO7有效配置，并保留所有raw/native数据。

现有接收器的循环停止依据public payload/completion，独立native核验在保存后进行。
为确保首个严格失败后不重投，本阶段不直接启用16次循环；后续先准备逐轮原生结果
核验及停止控制，再验证串行ring回绕。方案见[REPRODUCIBILITY.md](REPRODUCIBILITY.md)，
可执行单次脚本及冻结哈希记录在`private/analysis/A23-next-test.json`。
本阶段不是同启动串行/回绕或长时间稳定性验收，根因及DATA PID未确认。

00:22:02.862955+08:00重新核验指定SD身份、四文件/日志及唯一目标IPS，sync后正常
安全推出disk4并确认挂载消失。SD写入0/USB提交0，最终状态保存于collection及
deployment的latest_card_cycle记录。下一步插回Switch重启、USB2/HS/关闭视频，再测试一次。


### A23 第二独立启动复现：连续raw但原生状态失败 — 2026-10-08 00:39

配套文件、接收器/冻结backend哈希保持相同；只读fresh HS/interval1/MPS256、
IDLE/seq0/URB0预检通过。host64/request192/40ms/960slot，仅一次提交。
16包seq1..16/exact192 raw逐字节正确，indices522..537连续，无缺槽，但全部有效包
native E00002ED/public1、overall E000400E/transfer1，严格验收失败，receiver退出1。
960条native和完整184320byte raw已保留；944空槽原生E00002E7/E000400E未归一化。

自身URB387/report387/status3/requested=raw-count3072，ISO7 terminal1/bitmapFFFF/
actual3072完整终结，无取消/重投。首FrameID1754/control6DA01411对应声明首槽520，
16包相对首FrameID乘8加ordinal参考槽delta均+2；该差值不代表总线时间戳。
ISO7 context_valid1及首FrameID关系一致，interval1配置匹配，8个原始words与首轮相同。
选帧MFI13778，首边界14032，领先254tick（模16384）；首两成功ED MFI14032/14033
差1tick，相对首边界/下一125µs参考边界0/0。DMA/report非原子、时钟未同步。
submit1.070ms/实际等待45.052ms/trigger51.865ms、rc0，视频关闭是约定条件，未独立验证。

本次17文件原始证据、summary及独立逐包核验保存于`private/runs/latest-A23-run.txt`；
首次成功及完整日志的证据保持原文件不变，复现阶段在首个严格失败后停止，未进行
第三次采集、串行ring回绕或UAC。ISO7运行诊断已观察，本轮完整启动/runtime安装/
唯一提交及ticks日志待读卡。根因未确认，不能以首次成功宣称interval1已修复问题。

2026-10-08 01:24已回收第二轮4551byte完整日志，安装result0/22条与唯一URB387/3072终结匹配；
四文件未变，15份旧错误报告无新增。A23严格失败及首次成功证据均保留，根因未确认。
下一步保留A23，不重复拷卡；已构建并验证仅增加主机只读微帧观察的隔离工具，
见[HOST_MICROFRAME_AUDIT.md](HOST_MICROFRAME_AUDIT.md)。下次重启后仅一次诊断采集。

2026-10-08T01:37:28.095740+08:00再次核验四文件和4551byte日志后，正常推出disk4，
确认挂载消失。本轮SD写入0、USB测试0；下次重启后使用主机微帧观察工具单次测试。

2026-10-08 01:41主机microframe-audit-1单次HS采集严格通过：16包seq1..16/exact192，
indices536..551连续、有效包native/public0及overall0；URB387/status3/3072完整终结，
无取消/重投。四处只读微帧查询均成功，但读数均为8的倍数，真实微帧相位未解析。
新backend增加只读观察，不能将本轮视为原冻结backend的纯复现。稳定性和根因未确认；
本轮完整设备日志待读卡，当前下一步读卡，停止继续提交。

2026-10-08 01:49本轮2631byte完整日志已回收并SHA256核验，A23/HOS22.5.0/目标BuildID、
runtime result0/22记录、唯一seq1/URB387/status3/3072及首控制字51A01411与主机匹配。
模块base743E400000、首TRB偏移17D000匹配；四文件仍为A23，15份旧错误报告无新增/变化。
设备prepare0.049375/post0.374427/post至ACK0.000417/ACK0.117708/handler至ACK0.541927ms。
本次单次严格成功得到完整设备日志支持；post和handler时间比上一失败轮更长，
现有少量样本不能建立这些软件耗时与native失败的因果关系。主机四查询读数均为8的倍数，
真实微帧相位、总线服务时间和根因仍未确认。
下一步保持A23及同一microframe-audit-1工具/host64/request192/40ms/960槽/repeats1，
重新启动后做一次独立复现并停止提交，继续读卡核验。失败立即保留证据，不串行重试。
已重验原主机工具/receiver/backend/library/helper哈希，沿用通过的本地验证，不重复构建或测试。
本轮SD写入0、USB采集0；01:49:44.085333+08:00正常推出disk4并确认挂载消失。

2026-10-08 01:59同一microframe-audit-1工具第二次fresh IDLE/HS单次采集严格通过：
16包seq1..16/exact192/raw正确且indices567..582连续，native/public0、overall0。
URB387/status3/3072与ISO7 terminal1/FFFF完整终结，无取消/重投。四查询成功且计数均为8倍数，
FrameID1295推算首槽568而实际567，参考delta全-1，仍不能解析真实微帧相位。
工具/参数哈希与前轮相同，已有两轮严格成功；前轮2631byte日志已匹配，本轮完整设备日志
待读卡，暂不继续提交。稳定性与根因仍未确认，当前下一步读卡。

2026-10-08 02:05已回收第二轮主机诊断的完整2391byte日志，安装result0/22记录及唯一
seq1/URB387/3072正常终结与主机一致；无新增错误报告。两轮microframe-audit-1单次严格
成功均已完整日志核验。17E000环偏移按端点动态环指针/模块范围和ED标签验证，修正旧脚本
固定17D000假设；原检查中止时的日志也保留。稳定性、真实微帧相位和根因未确认。
已构建[逐次原生状态核验的串行工具](NATIVE_SERIAL_VALIDATION.md)，本地11个callback、
3个完整CLI模拟、3个分析器及3项参数拒绝验证通过；每次native/raw/ISO7完整终结
通过后才可提交下一次，最多16次，任一失败停止。本轮没有实机执行该阶段。
SD四文件保留A23，未重复拷入；02:20:17.555537+08:00正常推出disk4并确认挂载消失。
下一步重启、关闭视频、USB2/HS，执行一次最多16次串行的接收器会话以检查环回绕。
