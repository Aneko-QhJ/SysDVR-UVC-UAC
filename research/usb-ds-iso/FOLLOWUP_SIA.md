# A22：首包显式 FrameID，后续 TD 使用 SIA

2026-10-07，A21 完整 5654-byte 设备日志已回收：HOS22.5.0、目标 BuildID、
runtime result0/22条记录、唯一seq1/URB387和status3/3072终结均匹配主机证据。
四个部署文件一致，15份既有错误报告无新增或变更。handler至ACK为0.468125ms。
16包raw/native/public/overall成功，但indices80、82..96，缺槽81；首包对齐，
后15包偏移+1。发布前context配置匹配，TD0/TD1成功ED软件MFI相隔16tick。
配置快照未显示已解析字段异常，仍不能确定缺槽原因。

A22只改变后续15个TD的排队方式：TD0仍用`(MFI>>3)+32`的显式11-bit FrameID、
SIA0；TD1..15使用SIA1、FrameID0。ISO6快照、16个独立TD和ED、MPS256、
每包192bytes、首次cycle最后发布、两个DSB、原门铃尾部、完成/错误DMA所有权、
report112/STATUS168均沿用A21。循环内两条AArch64指令被等长替换，代码仍680bytes，
结束68FFC、RX上限69000。默认不启用新开关，重建A21应逐字节一致。

这是检验“为每个TD指定下一FrameID是否与首两包空槽有关”的单变量实验。
[Linux Tegra XUDC设备驱动](https://code.googlesource.com/linux/torvalds/linux/+/9f7853d7609d59172eecfc5e7ccf503bc1b690bd/drivers/usb/gadget/udc/tegra-xudc.c)
的`tegra_xudc_queue_one_trb`对Isoch设置SIA1、FrameID0和TLBPC0，提供设备侧参考。
该驱动并未证明HOS支持本实验的首包显式/后续SIA组合，也不能保证无缺槽。
[Intel xHCI 1.2b规范](https://cdrdv2-public.intel.com/625472/625472_xHCI_Rev1_2b.pdf)
解释主机侧SIA/FrameID语义；它不构成Tegra设备控制器的行为契约。
本轮选择由A21观察和设备驱动参考推导，须实机验证，未确认根因。

接收器应与A21二进制完全相同，仅manifest的目标revision改为A22；冻结A17
host64/request192静态后端、trigger delay40ms、256slot、single burst和错误判断。
ISO6仅记录首控制字，不能单独鉴别A21/A22或证明后15包的实机执行方式。
须核验配套NSP/IPS哈希及Switch启动标记
`ISO diagnostic revision A22 HS ISO6 first-explicit followup-SIA experiment`。
DMA上下文和多字段report非原子，软件MFI不是总线时间戳，未验证DATA PID。

```sh
python3 research/usb-ds-iso/tools/build_patch.py --burst --event-audit --context-audit \
  --followup-sia --frame-lead 32 --explicit-all --mps 256 \
  --out research/usb-ds-iso/private/packages-A22-followup-sia
python3 research/usb-ds-iso/tools/package_experiment.py --burst --revision A22 \
  --packages research/usb-ds-iso/private/packages-A22-followup-sia
```

本地43项测试通过（40核心/3接收器），覆盖全部247ring起点/两cycle、8种选帧
microframe相位/11-bit回绕、首包显式及后15包SIA、原ABI和DMA所有权、两指令差异
及revision错配拒绝。ISO2..6的inject/IPS及A18..21接收器重建逐字节一致，A22
接收器与A21完全相同。A/rollback构建和NPDM通过；runtime安装回滚和包交付核验
在部署前执行并保留证据。28个A包文件、6个rollback文件及两ZIP内容/哈希均通过。
本地包manifest保存构建时状态；部署后单次采集结果记录在下文。

2026-10-07T20:33:32.986192+08:00已完成A21模块/补丁目录及5654byte日志备份、
A22四文件配套拷入和SHA256读回；20:33:33.827541正常推出disk4并确认挂载消失。
实际部署记录见`private/deployments/latest-A22.txt`。NSP SHA256
`8b1e6f5006b3d505a9449f142488e7c6c25397a2dd281a584fa403cd02866f70`，IPS SHA256
`baa69cabe05d2ac1fbcf05aa47fbac810cbb6892056fb225ecff0c9c7eb15904`。

部署后插回Switch并重启；USB2/HS、视频关闭，在冻结条件下一次采集。
严格验收16包连续有序、逐包native/public0、exact192、overall0，自身URB
status3/3072、terminal1/bitmapFFFF/actual3072；另记ISO6有效性和context配置。
完成URB不取消、不重投；pending/retained先保留证据再取消。随后读卡回收完整日志。

2026-10-07 21:44首次HS单次已采集：只读fresh IDLE/seq0/URB0预检通过，
host64/request192/40ms/256slot均冻结，仅一次提交。16包seq1..16、exact192
raw逐字节正确，indices66..81连续；全部native E00002ED/public1，overall
E000400E/transfer1，严格验收失败/exit1。首FrameID955/control3BB01411推导首槽67，
全部相对首FrameID加ordinal的1ms参考槽delta-1。后续SIA TD没有显式FrameID，
该比较不证明实际总线服务时间。自身URB387/report387/status3/3072、terminal1/
bitmapFFFF/actual3072完整终结，无取消和重投。

ISO6 context_valid1/首FrameID关系一致，配置匹配，原始words与A21相同；MFI7387，
首编码边界7640，领先253tick（模16384）。TD0/TD1成功ED软件MFI7632/7640，
差8tick，相对首FrameID和下一1ms参考边界均-8。DMA及report非原子、时钟未同步，
不据此确认DATA PID或根因。submit0.888ms/实际等待45.024ms/trigger52.773ms、rc0。
视频关闭为约定条件，STATUS未独立验证；采集时A22启动标记/runtime安装和设备ticks待读卡。
原始证据/独立逐包核验保存于`private/runs/latest-A22-run.txt`。

22:18完整4948byte设备日志已回收并SHA256核验，指针`private/collections/latest-A22.txt`。
A22/HOS22.5.0/目标BuildID、runtime result0/record21（共22条）、唯一seq1/URB387/
status3/3072及首控制字均与主机证据匹配，运行revision身份已确认。设备prepare0.056146/
post0.191615/post-to-ACK0.000365/ACK0.173698/handler-to-ACK0.421823ms。
四文件匹配A22，15份既有错误报告无新增/变更；run20文件SHA256已更新。
连续raw但原生状态失败的结论不变，根因未确认。后续已完成
[A23 interval1实验](INTERVAL_EXPERIMENT.md)的研究、47项本地验证和配套部署/推出，
下一步重启后仅一次HS采集；A22包保留其构建时状态。
