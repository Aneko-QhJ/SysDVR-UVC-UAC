# Device-side single Isoch TD experiment

## 当前状态（2026-10-08）

2026-10-08 02:05已回收第二轮主机诊断的完整2391byte日志，安装result0/22记录及唯一
seq1/URB387/3072正常终结与主机一致；无新增错误报告。两轮microframe-audit-1单次严格
成功均已完整日志核验。17E000环偏移按端点动态环指针/模块范围和ED标签验证，修正旧脚本
固定17D000假设；原检查中止时的日志也保留。稳定性、真实微帧相位和根因未确认。
已构建[逐次原生状态核验的串行工具](NATIVE_SERIAL_VALIDATION.md)，本地11个callback、
3个完整CLI模拟、3个分析器及3项参数拒绝验证通过；每次native/raw/ISO7完整终结
通过后才可提交下一次，最多16次，任一失败停止。本轮没有实机执行该阶段。
SD四文件保留A23，未重复拷入；02:20:17.555537+08:00正常推出disk4并确认挂载消失。
下一步重启、关闭视频、USB2/HS，执行一次最多16次串行的接收器会话以检查环回绕。

以下为此前收集及实验记录。

2026-10-08 01:59同一microframe-audit-1工具第二次fresh IDLE/HS单次采集严格通过：
16包seq1..16/exact192/raw正确且indices567..582连续，native/public0、overall0。
URB387/status3/3072与ISO7 terminal1/FFFF完整终结，无取消/重投。四查询成功且计数均为8倍数，
FrameID1295推算首槽568而实际567，参考delta全-1，仍不能解析真实微帧相位。
工具/参数哈希与前轮相同，已有两轮严格成功；前轮2631byte日志已匹配，本轮完整设备日志
待读卡，暂不继续提交。稳定性与根因仍未确认，当前下一步读卡。

以下为此前日志回收及研究记录。

2026-10-08 01:41主机microframe-audit-1单次HS采集严格通过：16包seq1..16/exact192，
indices536..551连续、有效包native/public0及overall0；URB387/status3/3072完整终结，
无取消/重投。四处只读微帧查询均成功，但读数均为8的倍数，真实微帧相位未解析。
新backend增加只读观察，不能将本轮视为原冻结backend的纯复现。稳定性和根因未确认；
本轮完整2631byte设备日志已回收核验，SD已安全推出；下一步重启后用同一工具独立复现一次。

以下保留先前失败及研究记录。

后续按用户约定执行[读卡到推出的完整流程](CARD_WORKFLOW.md)。

当前卡上为 **A23，第二次独立启动复现失败，完整4551byte日志已回收核验**。
00:39只执行一次HS采集，16包raw正确且indices522..537连续，但有效包native全
E00002ED/public1、overall E000400E，严格验收失败；URB387/status3/3072完整终结，
未取消/重投。ISO7 interval1配置匹配、首两ED软件MFI差1tick，不能据首次成功宣称修复。
已停止复现阶段；已准备只增加主机只读微帧观察的下一次单次诊断，卡上保留A23。
构建和4项接收器测试通过，详见[HOST_MICROFRAME_AUDIT.md](HOST_MICROFRAME_AUDIT.md)。
A22完整4948byte日志已回收，安装及唯一提交/终结与主机证据匹配，无新增错误报告；
raw连续但native状态失败的结论不变。A23改HS bInterval4→1（125µs），沿用首包显式/
后15TD SIA，使用ISO7；采集窗口同步改为960槽/120ms，不能作为严格单变量因果对照。
47项本地测试、旧版逐字节重建、安装回滚和交付校验通过。00:01首次HS单次16包
seq1..16、exact192 raw正确，indices456..471连续，全部有效包native/public0、overall0；
自身URB387/status3/3072完整终结，ISO7配置匹配，首两成功ED的MFI差1tick。
完成URB未取消/重投，原始证据已保存；单次通过不等于稳定性通过，根因未确认。
5228byte完整设备日志已回收，确认A23启动标记、runtime result0/22记录、唯一提交及
正常终结；四文件仍匹配，15份既有错误报告无新增/变更，handler至ACK0.321094ms。
此前保留A23并安全推出，随后执行的独立复现已失败；两轮证据和验证阶段见
[INTERVAL_EXPERIMENT.md](INTERVAL_EXPERIMENT.md)和[REPRODUCIBILITY.md](REPRODUCIBILITY.md)。

A12 **实机已验证**：HS 单192byte ISO、正常completion、100次串行、ring回绕、
物理重连和用户观察的视频共存。A12修复实验接口误stall共享EP0的问题，
最后共存测试段无EP0错误/视频超时；早期日志仍有视频超时，不标为整段零错误。
最终包为 `private/deliveries/A12-HS-experiment-final.zip`，详细证据见 RESULTS。
SS协议错误、endpoint reset恢复、持续30分钟、UAC及总线波形尚未验收。

A13 **实机已收到全部16包，但重复时出现接收槽空档，稳定性未通过**：HS-only/MPS256/lead32，一个3072byte
URB预排16个连续1ms的独立TD，每个为Isoch Chain + ED IOC，FrameID逐次+1。
每个ED必须匹配自己的ring tag且count192；16-bit bitmap防止重复累计。
全部16个ED到齐才以3072bytes终结原URB；任一匹配事件错误/长度异常保留DMA，
不得重投。只允许一个URB在途，buffer保持4096对齐且全长3072，避免跨页。
首次及两次重复均在连续槽内收到16包，第三次重复第1/2包间空一槽；
全部内容及URB完成仍正确，已停止继续提交。尚未到ring wrap，不标为稳定通过。
这是有界连续帧实验，不是持续队列或音频。

A14在 `private/packages-A14-frame-snapshot/`，已通过本地测试，
2026-10-02 14:32备份A13并部署，四文件读回校验、安全推出完成；实机单次已取得FrameID快照：
保持调度参数，ISO2 +48新增首TRB快照，用于比对FrameID与host schedule。
A13的ISO2缺少该字段，解码器以TRB type5确认快照存在。
A14首包index比声明FrameID对应槽早1，后15包对齐，仍有一槽空档且native
payload错误；raw内容与URB完成均正确，不标为data成功。无新TD空窗口全零/
overall0，未复现payload错误，尚不足以确认根因。Switch日志已回收，确认A14安装result0/一次正常完成、无新增错误报告。
A14 host提前量比较使用独立host32工具，
`--burst --packets 128 --trigger-delay-ms 40`，单次测试已通过，但256slot重复第三轮只收到14包并锁存设备code23；
已显式取消至URB status4，无重投，稳定性仍未通过。
A15仅增加错误raw event/MFI/TD位置诊断，位于
`private/packages-A15-error-snapshot/`，2026-10-02 21:02已回收A14日志：
三个成功URB完整终结，URB435取消至status4，无重投，无新增错误报告。
A14已备份；A15四文件读回校验并安全推出，尚未实机。
A15首次HS单次已完成：16包内容/native状态正确、URB完整终结，但第1/2包间
仍有一槽空档，连续帧验收失败；没有设备错误，未生成错误快照。已停止重投，
SD日志已回收，确认A15安装及唯一URB完整终结，无新增错误报告。
卡保持A15并安全推出。下一轮仅host提前32改64，等待仍40ms/256slot/单次；
工具位于`private/darwin-diag-host64/`。host64单次实机收到连续16包、FrameID
全部对齐，但native payload全为E00002ED/overall E000400E，验收仍失败。
设备URB完整终结，无需取消；日志已回收确认安装及完成，无新增错误报告。
SD保持A15并安全推出；下一轮host64/256slot/fresh boot的--receive-only空闲
接收对照已完成：无TD窗口raw全零、overall0、设备空闲不变。
同boot配对burst原生16包及overall成功，但仍有一槽空档，稳定性未通过；
设备完整终结，无需取消，两轮设备日志已回收确认唯一提交和安装成功，无新增
错误报告。SD保持A15并已安全推出。下一轮同参数单次只增加主机提交/实际等待/
触发请求/callback耗时日志已实机：submit0.503ms、实际等待45.057ms、trigger
62.198ms。16包raw正确/URB完整终结，但native全部报错并仍有一槽空档。
日志已回收确认安装及唯一URB完整终结，无新增错误报告。
A16新增设备trigger/PostBufferAsync/ACK前后tick日志，USB控制器补丁及调度参数
与A15相同；A15已备份，A16四文件校验并安全推出，尚未实机。
A16首次HS单次已测试：实际等待43.738ms、trigger67.118ms，16包raw正确，
但native全部报错且仍有一槽空档；设备URB完整终结，无需取消，已停止重投。
设备日志已回收：post约0.199ms，post到ACK前约11.015ms（含同步日志及调度），
ACK约0.172ms。A17仅把提交日志移到ACK后，controller及host与A16字节一致；
已备份A16、部署A17。实机单次16包严格通过，随后计划16次重复在第1次
即一槽空档失败停止；设备两URB均完整终结，无需取消，稳定性未通过。
两run设备日志已回收：post-to-ACK降至约0.000365ms，handler总耗时不足0.3ms，
但空档仍出现，日志后移未解决稳定性。无新增错误报告，SD保持A17并安全推出。
下一轮仅主机每槽请求192改256，数据actual仍严格要求192；host64-slot256工具
已通过两种stride的接收负例检查。slot256单次仍有一槽空档；16包actual192/
requested256、raw内容正确，native状态E00002E7/overall0，未通过严格验收。
URB完整终结，无需取消；设备日志已回收确认唯一提交及安装，未新增错误报告。
SD保持A17并安全推出。主机常数对照暂告一段落，下一步本地审计控制器未匹配/
终结后事件的诊断缺口，再设计有界事件/MFI采样。
2026-10-06 已完成 A18 ISO3 有界诊断和本地验证，包位于
`private/packages-A18-event-audit/`，已部署并完成单次采集：16包内容及native状态正确，
首两包仍空一槽，严格验收失败；首两成功ED的MFI差16。设备日志已回收，确认唯一提交、
安装result0，无新增错误报告，handler至ACK共0.428ms；SD保持A18且已安全推出。首两成功 ED、首个过滤/
终结后事件及优先错误快照的布局、有效性规则和单次实验步骤见
[EVENT_AUDIT.md](EVENT_AUDIT.md)。主机仍冻结 host64/request192/40ms/256slot；
不把软件 MFI 快照当成总线时序或根因修复。
后续原模块审计未发现首两TD的FrameID递增/ring回绕错误。A19 ISO4现已完成
本地验证，新增选帧、发布前、进入原doorbell tail前三个MFI锚点，保留首两ED
和优先错误快照；调度常数、DMA所有权及严格验收不变。29项A19测试和9项A18
回归通过，包位于`private/packages-A19-publication-audit/`，布局及下一次单次采集
步骤见[PUBLICATION_AUDIT.md](PUBLICATION_AUDIT.md)。2026-10-07已备份A18及旧日志、
拷入A19，四文件读回SHA256一致且SD安全推出。首次HS单次已采集：16包内容及
native/public/overall状态正确，但首两包缺槽73，严格连续性失败。ISO4三个阶段MFI
均13533，phase_valid/FrameID关系一致，首两成功ED的MFI差16；URB完整终结，
无取消、无重投。完整设备日志已回收，确认A19安装result0/唯一提交/正常终结，
handler至ACK0.403333ms，无新增错误报告；SD保持A19并安全推出。
A20 ISO5原门铃tail前后MFI采样已完成35项本地验证，包在
`private/packages-A20-doorbell-audit/`，操作见[DOORBELL_AUDIT.md](DOORBELL_AUDIT.md)。
A20于2026-10-07 19:49完成A19备份、四文件拷入/读回校验及安全推出。
A20首次HS单次已采集：连续16包/FrameID全对齐、raw逐字节正确，但native全为
E00002ED/overall E000400E，严格验收失败；自身URB完整终结，无取消或重投。
ISO5 marker700有效，原tail前后MFI相同；5408byte完整日志已回收，确认安装及唯一
提交/终结，无新增错误报告，handler至ACK0.36625ms。
A21新增ISO6发布前硬件EP7上下文只读快照，680bytes/report112/STATUS168，
39项本地验证及旧版本逐字节回归通过。已备份A20、部署A21并完成四文件读回核验，
安全推出。A21首次HS单次16包raw/native/public/overall正确，但缺槽81，严格连续性
失败；端点context配置匹配，自身URB完整终结，无取消/重投。5654byte完整安装/唯一
提交/ticks日志已回收核验，无新增错误报告。见[CONTEXT_AUDIT.md](CONTEXT_AUDIT.md)。
A22仅切换后15个TD为SIA1/FrameID0，首包显式lead32及ISO6诊断沿用A21；43项
测试、runtime安装回滚、A/rollback构建和旧版逐字节回归通过。已备份A21、部署A22，
四文件读回及正常安全推出完成。A22接收器与A21完全相同；21:44首次HS单次已采集，
16包连续indices66..81、exact192 raw正确，但全16包native E00002ED/public1、
overall E000400E/transfer1，严格验收失败。首FrameID推导首槽67，全包相对1ms参考
槽delta-1；ISO6配置匹配、URB387/status3/3072完整终结，无取消/重投。完整A22启动
标记/runtime安装/ticks日志已于22:18回收核验；ISO6不能单独辨别A21/A22，需配套日志。
handler至ACK0.421823ms，四文件匹配，15份既有错误报告无新增/变更。已完成研究、
A23验证及配套部署/推出；下一步重启后单次测试A23。
见[FOLLOWUP_SIA.md](FOLLOWUP_SIA.md)。软件锚点不能
证明控制器的总线服务时刻，缺槽根因仍未确认。
旧FRAMES采样请求不兼容burst诊断布局，
本轮没有获得有效独立帧采样；详情及原始证据见 RESULTS。

A13使用独立request `0x54`，旧单包request `0x50` 不会触发它；旧包也不会接受
新触发请求。STATUS仍168bytes，诊断magic改为`ISO2`：context四字改为
完成bitmap、累计actual以及首TRB虚拟地址（64-bit）。受684byte RX注入空间
限制，本版不抓取raw Transfer Event/context快照，不能沿用ISO1解释这些字段。
`terminal`保留错误code；code14/SS问题未修复或宣称解决。

包在 `private/packages-A13-burst/`，一次只部署A，与A12同样需要同时替换
客户端及IPS并重启。2026-10-02 14:25已备份A12、部署A13并安全推出SD，
四文件读回SHA-256一致；尚未实机提交TD。先经USB2连接、不打开视频，
只测一次：

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

## 先运行 A 组

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

成功后用 `--repeat 100` 串行验证；再用 `--repeat 150` 覆盖真实 ring wrap。
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

## 实现与诊断约定

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
  状态为 RETAINED，禁止重投。remaining/actual 语义仍待实测。
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

## 重建与验证

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

若 A/B/C 都不能收到数据，先对照 context/TRB 与事件。此时才继续调查 device
MMIO frame counter，确认单位，再测试 explicit FrameID 与 lead4/8/16/32；
实机 B/A6 已确认 +0x48 的8kHz时间基准，详见 RESULTS；B/A7 lead4待实测。
UAC 和连续 streaming 等待这一关通过。

## macOS 原生逐包诊断

macOS 接收侧另有独立诊断工具：下载官方 v1.0.30 codeload tar 到
`private/libusb-v1.0.30.tar.gz` 后运行 `tools/build_darwin_diagnostics.py`。
生成 `private/darwin-diag/iso-probe-native-diag`，静态链接单独编译的 libusb，
不替换 Homebrew 库。它保留整体错误，同时输出 IOKit 原生逐包 status/actual，
并在整体错误时复制逐包证据。运行与标准工具相同的 `--log` 参数；stderr
必须一并保存。接收缓冲另存为 `<log>.seqN.buffer.bin`；仅有 buffer 图案
不计为 packet 验证成功。此工具不修改 Switch 补丁、descriptor 或调度。
下一轮命令为 `iso-probe-native-diag --packets 64 --log window64.jsonl`，
仍使用 B/A7 lead4。省略 `--packets` 保持原512窗口；原生schedule记录
输出计划起始frame，用来核对device FrameID是否位于窗口内。

## 回滚

将本实验的 `atmosphere/exefs_patches/SysDVR-ISO/` 移出 SD 加载目录，
恢复备份的视频客户端，或部署 `private/packages/rollback/atmosphere/`，然后重启。
rollback 包不包含 IPS；复制它本身不会删除已安装的实验补丁。
恢复其他旧补丁时保持原备份内容，不混装 A/B/C。
