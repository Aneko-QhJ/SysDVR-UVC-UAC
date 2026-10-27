# USB设备侧ISO实验指南

## 当前入口与版本范围

最新事实见[当前状态](STATUS.md)：A23串行测试首轮原生失败，完整3365byte设备日志已核验，
无TD基线及完整日志已核验；20:34单次burst及2630byte完整设备日志验收通过。
新[同backend串行工具](MATCHED_SERIAL_VALIDATION.md)22:34执行4轮，第4轮失败后停止，完整设备日志待读卡。
后续推进条件见[测试计划](TEST_PLAN.md)。
目录/恢复见[DIRECTORY_LAYOUT.md](DIRECTORY_LAYOUT.md)，读卡/部署见[CARD_WORKFLOW.md](CARD_WORKFLOW.md)。

| 范围 | 参考与已知结果 |
| --- | --- |
| A/B/C..A12，单192byte TD | 本页保留早期ISO1技术细节；A12仅HS单包路径通过100次串行、回绕、重连及视频共存 |
| A13..A17，16个独立TD | 单次曾通过，重复时仍有空槽或原生错误；逐次证据见[RESULTS.md](RESULTS.md) |
| A18..A22，ISO3..6诊断 | [事件](EVENT_AUDIT.md)、[发布](PUBLICATION_AUDIT.md)、[门铃](DOORBELL_AUDIT.md)、[上下文](CONTEXT_AUDIT.md)、[SIA](FOLLOWUP_SIA.md) |
| A23，HS interval1/ISO7 | [服务间隔](INTERVAL_EXPERIMENT.md)、[独立复现](REPRODUCIBILITY.md)、[主机观察](HOST_MICROFRAME_AUDIT.md)、[串行验收](NATIVE_SERIAL_VALIDATION.md) |

本页下方的A13及早期A/B/C命令是版本特定的历史参考，不能替代当前阶段检查或作为下一次采集指令。
冻结包内说明记录其构建时状态；后续实际部署、run和collection才决定实机验收范围。
早期文件匹配但运行模块未加载IPS的问题已有A3实机证据，A4起增加Build-ID特定runtime安装器；
必须核对完整启动/安装日志，不能仅凭SD的IPS哈希认定运行时补丁已生效。

## A13的16-TD历史接口与采集参考

A13使用独立request `0x54`，旧单包request `0x50` 不会触发它；旧包也不会接受
新触发请求。STATUS仍168bytes，诊断magic改为`ISO2`：context四字改为
完成bitmap、累计actual以及首TRB虚拟地址（64-bit）。受684byte RX注入空间
限制，本版不抓取raw Transfer Event/context快照，不能沿用ISO1解释这些字段。
`terminal`保留错误code；code14/SS问题未修复或宣称解决。

包在 `private/packages-A13-burst/`，一次只部署A，与A12同样需要同时替换
客户端及IPS并重启。2026-10-02 14:25已备份A12、部署A13并安全推出SD，
四文件读回SHA-256一致；随后已有实机单次成功及重复失败，详见[历史结果](RESULTS.md)。
以下为A13历史单次命令（不用于当前A23）：

```sh
research/usb-ds-iso/private/packages-A13-burst/A/iso-probe-native-diag \
  --burst --packets 128 --log research/usb-ds-iso/private/runs/A13-burst-001.jsonl \
  2>research/usb-ds-iso/private/runs/A13-burst-001-native.log
```

成功需16包依序且在连续host packet槽内、每包native/public status0和192bytes、
内容逐字节对应`sequence+packet_index`（16-bit回绕）、overall0；设备URB
status3/requested3072/transferred3072、bitmapFFFF/actual3072/terminal1。
单次成功后才逐步做重复、wrap及视频共存。失败保留日志，先STATUS确认所有权，
不要盲目重投；取消沿用现有`--cancel`（不要同时指定`--burst`）。

重建A13：

```sh
python3 research/usb-ds-iso/tools/build_patch.py --burst --frame-lead 32 \
  --explicit-all --mps 256 --out research/usb-ds-iso/private/packages-A13-burst
python3 research/usb-ds-iso/tools/package_experiment.py --burst --revision A13 \
  --packages research/usb-ds-iso/private/packages-A13-burst
ISO_PATCH_PACKAGES="$PWD/research/usb-ds-iso/private/packages-A13-burst" \
  research/usb-ds-iso/private/venv/bin/python -m unittest discover \
  -s research/usb-ds-iso/tests -p test_burst.py -v
```

Unicorn需要允许JIT的环境。它验证实际补丁机器码，不能替代硬件调度证据。
TD按服务周期分离的参考是 [Intel xHCI 1.2b §3.2.11](https://cdrdv2-public.intel.com/625472/625472_xHCI_Rev1_2b.pdf)；
这里只借鉴格式与调度算法，device controller实际执行仍需实测。

## 固定目标与持久产物

- 固件版本已从本地 SystemVersion Data NCA 确认：`22.5.0`，`22.5.0-1.0`。
- usb Program ID：`0100000000000006`。
- Build ID：`AD8D36F2029822A4C498F055ADBDAA789EB913C6000000000000000000000000`。
- 原始 main NSO SHA-256：`08e0c60a2879e59bb7ace77a17418f7fc0d18058e90a2f12516ff8b1ebe62dfb`。
- NSO text：`0..0x68D54`；rodata：`0x69000..0x8D594`；data：
  `0x8E000..0xD20A8`；data+BSS 结束于 `0x369000`。
- `private/module/`：NCA、ExeFS、ELF、分段二进制、module.json、固件索引、
  disassembly.txt、decompiled.c。Ghidra 工程在 `private/ghidra/usb-ds.gpr`。
- `private/packages/{A,B,C}/`：controller IPS、实验 exefs.nsp、macOS receiver、
  补丁与客户端 manifest。`private/packages/rollback/` 是无实验端点的视频客户端。
- 同目录的 `SysDVR-ISO-{A,B,C,rollback}.zip` 可直接解压部署；每包附有 `INSTALL.txt`。
- `private/logs/`：构建和仿真日志；`private/venv/`：Unicorn 测试运行环境。
  这些全部持久保存、排除 Git；未复制密钥到项目。

`tools/nso2elf.py` 与 Ghidra 导出脚本复用自本机同属用户的
`DGLAB-NX/tools/ble-re/`。hactool 构建位于 private，版本提交为
`1d64a83450e025622f3468c28fc4164dad2c5ef6`。Ghidra 12.1.3、Java 21、Unicorn 2.1.4。

## 早期A/B/C的历史部署与单TD采集

1. 在 SD 卡上备份现有 `atmosphere/contents/00FF0000A53BB666/`。
   在 `atmosphere/exefs_patches/` 下检查相同 usb Build ID 的其他补丁，
   将会重叠的旧 descriptor/ISO 补丁移出加载目录，保存备份。
2. 将 `private/packages/A/atmosphere/` 的内容合并到 SD 卡的 `atmosphere/`。
   一次仅部署一个变体；切换时复制整个对应包的 atmosphere 内容并重启，
   同时替换 IPS 和带有相应运行时补丁的客户端。
   不要同时安装原版 SysDVR。
3. 重启 Switch，等 sysmodule 接管 USB 后，用数据线连接 Mac。
   新设备仍是 `1209:ca57`，UVC 保留，另有 interface 2、vendor `FF/49/01`、
   alt0 ISO IN `0x83`。首次实验保持视频关闭，不必启动游戏。
4. 在仓库根目录执行：

   ```sh
   mkdir -p research/usb-ds-iso/private/runs
   research/usb-ds-iso/host/iso-probe \
     --log research/usb-ds-iso/private/runs/A-001.jsonl
   python3 research/usb-ds-iso/tools/summarize_run.py \
     research/usb-ds-iso/private/runs/A-001.jsonl \
     --out research/usb-ds-iso/private/runs/A-001-summary.json
   ```

5. 保存 JSONL、summary、SD 卡的 `/logfile.txt` 及新 crash/fatal 报告。
   若有 payload 或 completion 失败，保留记录并停止重投；先不要接音频。
   为测试 B/C，分别部署对应 IPS，重启，再使用新的 `B-001` / `C-001` 日志名。

macOS 工具只 claim vendor interface，不 detach UVC driver、不改变 configuration。
若 macOS 拒绝 claim，日志/错误要与 Switch 事件一起保留；这不证明 device
engine 不接受 type-5。可用同一 C 工具在 Linux 虚拟机交叉检查 USB passthrough。

早期单TD阶段在成功后用 `--repeat 100` 串行验证，再用 `--repeat 150` 覆盖真实ring wrap。
A12已取得这些单TD结果；该次数和旧工具不能套用到A23最多16次burst阶段。
随后断开/重连并重跑，最后在 UVC 正常开流时重复实验。每次使用新的日志文件名。
主机工具一次预排 512 个 1ms 接收周期，10ms 后发触发请求，只有一个 device TD。

若上次 URB 仍 pending，可单独请求取消并 reap：

```sh
research/usb-ds-iso/host/iso-probe --cancel \
  --log research/usb-ds-iso/private/runs/A-cancel-001.jsonl
```

取消后仍为 RETAINED 时不要复用 buffer，保存日志并重启。主机退出必须等
libusb 取消回调；macOS 取消一个请求会取消同 endpoint 全部请求。
[libusb cancellation semantics](https://libusb.sourceforge.io/api-1.0/group__libusb__asyncio.html)

## 早期ISO1单TD实现与诊断约定

- ISO 条件分支 `0x30364` 跳转 `iso_enter`，非 ISO 仍进入原提交路径。
  保留原 `0x1908C` 返回用于不支持的输入。仅 EP83、192 bytes、MPS192、
  interval4、HS/SS、burst/mult=0 被接受；要求 enqueue==dequeue。
- 新 producer 位于原 text 最后一页的 `0x68D54..0x69000` 空白区。
  保留原 NSO 布局、host producer、MMIO 和 device doorbell tail `0x31C74`。
  IPS32 偏移按映射地址加 `0x100`，生成前验证完整 NSO 哈希、Build ID、
  原指令及注入范围，拒绝预先修改的输入。
  [Atmosphère IPS mapping](https://github.com/Atmosphere-NX/Atmosphere/blob/master/stratosphere/loader/source/ldr_patcher.cpp)
  loader 先清零段间空白、再加载 IPS，最后将 text 页对齐设为 RX，
  因此该空白页尾可执行。
  [loader loading and permissions](https://github.com/Atmosphere-NX/Atmosphere/blob/master/stratosphere/loader/source/ldr_process_creation.cpp)
- 一个 packet 的数学为 `ceil(192/192)=1`，故 TBC=0、TLBPC=0；SIA=1、
  FrameID=0、ISP/BEI=0。A：Isoch IOC0+Chain，ED IOC1；
  B：Isoch IOC1 无 ED；C：Isoch IOC1+Chain，ED IOC1。
  首 TRB cycle 最后发布，前后各有 DSB；Link 的 Chain、TC 和 cycle 按跨越位置更新。
- 此 ISO ring 的 Link 从 `+0xFF0` 前移到 `+0xF70`，可用 247 个 TRB 槽；
  `+0xF80..+0xFF0` 为 112-byte 有界邮箱。只改该 ISO entry 的 Link 指针。
  reset 后若 HOS 恢复原 Link，则下一次提交重新安装邮箱布局。
- transfer-event dispatch `0x30898` 进入 `iso_event`。非实验事件原样走
  `0x30F70`。记录前两个原始事件及总事件数，第三个起将最新事件存入
  原 ED 快照槽。解码器区分 ED TRB 与 type32 event，旧日志仍可读取。
  ED=0 按 Isoch DMA 地址匹配；ED=1 按原 DS ED self/tag 的虚拟地址匹配。
- **实验 completion 是受控终结，不代表原 completion 已兼容 ISO**：
  A/C 仅匹配成功 ED 事件后终结；B 匹配成功裸 Isoch 事件后终结。
  C 的第一条裸事件不释放；重复事件不二次释放。raw count 必须≤192，
  值原样送入 report，同时用 terminal 标志禁止旧路径按 count=0 重投。
  匹配的 Isoch/ED 错误锁存为 terminal 高位加 completion code，之后的 ED
  成功不再释放。超长 count 同样锁存；未知 tag 保留 DMA。错误时客户端
  状态为RETAINED，禁止重投。后续count/正常completion对照见RESULTS的A8..A12阶段，
  不把早期受控终结当作所有版本/速度通用的completion验收。
- `0x2CBE0` 的 report epilogue 在 report_count≤1 时将诊断放入七个未用槽；
  首个真实 report 与 report_count 保持原值。USB IPC 没有新增命令或参数。
- 诊断为 magic/variant/event_count/terminal、**context 首四个 dword**、
  Isoch physical/tag、发布 TRB、ED TRB（第三个事件起被最新事件替换）、
  前两个原始事件。可从 TRB 看 cycle，
  从 physical/tag 推导该 TD 的 ring 位置；doorbell index 固定7、写值 `0x700`。
  这是提交时快照，不是完整寄存器 dump，也不是错误后的 context 快照。
- HS/SS 每周期192 bytes；SS companion 的 burst/mult=0、wBytesPerInterval192。
  单接口描述符16/22 bytes，小于独立128-byte限制。已有 configuration u8
  长度/offset 修复以 u16 恢复，281-byte 组装及 GET_DESCRIPTOR 已在机器码仿真验证。

共享 wire schema 位于 `source/uvc/iso_probe_protocol.h`：
`TRIGGER=0x50` 是 interface OUT 无 data，wValue 为16-bit序号；
`STATUS=0x51` 是 interface IN 固定168 bytes、wValue0；
`CANCEL=0x52` 是 interface OUT 无 data、wValue0。wIndex2。
测试 payload 为 `ISO1`、序号低/高字节及可核对的确定性 pattern。

## 早期单TD重建与本地验证参考

```sh
python3 research/usb-ds-iso/tools/extract_usb.py \
  --firmware "$HOME/Library/Application Support/Ryujinx/bis/system/Contents/registered" \
  --keys "$HOME/Library/Application Support/Ryujinx/system/prod.keys" \
  --hactool research/usb-ds-iso/private/hactool/hactool \
  --out research/usb-ds-iso/private/module
python3 research/usb-ds-iso/tools/build_patch.py
python3 research/usb-ds-iso/tools/package_experiment.py
research/usb-ds-iso/private/venv/bin/python -m unittest discover \
  -s research/usb-ds-iso/tests -v
```

`package_experiment.py` 保持根 sysmodule.json 不变，生成兼容当前 npdmtool 的
私有配置，验证生成后的 ACI0 Program ID 和 ACID range。实验与回滚独立 build
目录并强制重新编译，避免 ISO_PROBE flags 缓存串用。Mac Intel 可给 host make
传 `LIBUSB_PREFIX=/usr/local`；Linux 使用 pkg-config 的 libusb-1.0。

重新导入/导出 Ghidra（已有工程无需再 import）：

```sh
JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home \
JAVA_TOOL_OPTIONS="-Duser.home=$PWD/research/usb-ds-iso/private/ghidra-user" \
/opt/homebrew/Cellar/ghidra/12.1.3/libexec/support/analyzeHeadless \
  "$PWD/research/usb-ds-iso/private/ghidra" usb-ds -process usb.elf \
  -scriptPath "$PWD/research/usb-ds-iso/ghidra" \
  -postScript ExportDecompiled.java "$PWD/research/usb-ds-iso/private/module/decompiled.c"
```

仿真覆盖真正的补丁指令，包括 A/B/C、两种 wrap、输入与忙状态拒绝、Bulk
原路径、双 IOC/重复事件、错误保留所有权、report ABI、Build ID/hash 不匹配，
以及 descriptor >255 的组装与读取。Unicorn 需要允许 JIT 的运行环境。
它验证软件编码与控制流，不能验证 device-mode 硬件执行、调度或总线行为。

早期实验已执行A/B/C、frame计数和lead4/8/16/32对照：B/A6确认+0x48的8kHz
时间基准，B/A7 lead4已有实机记录；后续A12仅HS单包路径通过串行/回绕等检查。
详细结果见[历史记录](RESULTS.md)，不能把这些历史结果外推到A23 burst或UAC。

## 早期macOS原生逐包诊断

macOS 接收侧另有独立诊断工具：下载官方 v1.0.30 codeload tar 到
`private/libusb-v1.0.30.tar.gz` 后运行 `tools/build_darwin_diagnostics.py`。
生成 `private/darwin-diag/iso-probe-native-diag`，静态链接单独编译的 libusb，
不替换 Homebrew 库。它保留整体错误，同时输出 IOKit 原生逐包 status/actual，
并在整体错误时复制逐包证据。运行与标准工具相同的 `--log` 参数；stderr
必须一并保存。接收缓冲另存为 `<log>.seqN.buffer.bin`；仅有 buffer 图案
不计为 packet 验证成功。此工具不修改 Switch 补丁、descriptor 或调度。
B/A7 lead4历史短窗口命令为 `iso-probe-native-diag --packets 64 --log window64.jsonl`。省略 `--packets` 保持原512窗口；原生schedule记录
输出计划起始frame，用来核对device FrameID是否位于窗口内。

## 回滚

将本实验的 `atmosphere/exefs_patches/SysDVR-ISO/` 移出SD加载目录，
恢复已校验备份的视频客户端或当前部署包配套的rollback，然后重启。
A23配套回滚在`private/packages-A23-interval1/rollback/atmosphere/`；
`private/packages/rollback/atmosphere/`仅是早期包的回滚位置。
rollback 包不包含 IPS；复制它本身不会删除已安装的实验补丁。
恢复其他旧补丁时保持原备份内容，不混装 A/B/C。
