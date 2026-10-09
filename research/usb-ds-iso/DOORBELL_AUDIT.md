# A20：ISO5 原门铃路径前后 MFI

2026-10-07。A19设备日志确认安装和唯一提交，handler至ACK0.403333ms；16包
内容/native/public/overall状态成功，但首两包缺槽。三个MFI均13533，只覆盖
选帧至进入原tail，原tail的检查及门铃写入尚未被这组观测包围。

原`0x31C74..0x31CE0`读取x1上下文，使用x0/x8/x9/x10，未使用x5/x14、sp或callee-saved寄存器。
正常路径在`0x31CDC`以`w8=endpoint_index<<8`写MMIO+4，然后返回0；
拒绝分支在移位/写入之前返回`0x1928C`。A20在ISO producer内调用完整原tail，
保持原返回值，再读取MFI，最后恢复原调用者x29/x30及sp返回。
原tail代码、doorbell寄存器和值保持原样；Bulk入口和事件所有权规则不改。

去掉A19发布前采样，将两个采样点放到原tail调用前后，仍为三个MFI读取，
注入仍684byte，止于`0x69000`。FrameID算法、lead32、16独立TD、首cycle最后
发布、两道DSB均不变。调用/返回及采样可能影响执行时长，硬件结果尚未验证。

| 偏移 | ISO5内容 |
| --- | --- |
| 0..71 | 与ISO3/ISO4同一common header和TD0/TD1-or-error快照 |
| 72 | 直接参与选帧的MFI |
| 76 | 第二道DSB之后、调用原tail之前的MFI |
| 80 | 原tail返回之后的MFI |
| 84 | doorbell_marker：新提交清0，最后保存原tail返回时的w8；正常EP7为`0x700` |
| 88..111 | 保留，可能陈旧，禁止解释 |

诊断magic为ISO5 `0x354F5349`，report/STATUS仍112/168bytes、version1。
marker0或其他值无效，拒绝分支留下未移位的endpoint index，不能当正常门铃。
解码只在marker0x700、MFI范围和首FrameID关系一致时展示三个值；复制仍非原子，
marker不是事务ID。首个匹配错误仍优先覆盖TD1，不计算成功ED差值或释放retained DMA。

这组读数包围软件执行原tail及其MMIO store，不是MMIO写入的精确时间，也不证明
控制器接收门铃或按指定FrameID服务TD。模16384差值无法排除整周期回绕；
中断和调度也可能影响前后间隔。仍缺总线trace和两侧时钟同步。

```sh
python3 research/usb-ds-iso/tools/build_patch.py --burst --event-audit --publication-audit \
  --doorbell-audit --frame-lead 32 --explicit-all --mps 256 \
  --out research/usb-ds-iso/private/packages-A20-doorbell-audit
python3 research/usb-ds-iso/tools/package_experiment.py --burst --revision A20 \
  --packages research/usb-ds-iso/private/packages-A20-doorbell-audit
```

A20匹配模块/IPS已部署并校验、安全推出；下一次插回Switch并重启。冻结USB2/HS、视频关闭、host64/
request192/wait40ms/256slot、单次，不重投。连续16包、全部native/public0、
exact192/overall0、自身URB/status3/3072及terminal1/bitmapFFFF/actual3072仍是验收条件。
额外核对ISO5 marker0x700和三锚点，回收完整Switch安装/唯一提交/ticks日志。
已终结URB不取消；仅pending/retained时保存证据后取消。

本地35项测试通过（32项机器码/客户端/解码器，3项冻结receiver验证）。实际执行
A20机器码，覆盖247个ring起点及两cycle、读取顺序、正常及拒绝tail的返回值、
原tail字节不变、caller sp/LR及callee-saved寄存器恢复、过滤/错误保留/拒绝重投、
报告边界和真实STATUS/EP0路径。默认ISO2/3/4 inject.bin与IPS和A18/A19 receiver
均与既有包逐字节相同。runtime installer预检/幂等/部分失败回滚及A/rollback
构建/NPDM检查通过。验证日志、manifest和SHA256SUMS随包保存。

包是诊断准备，不代表缺槽根因已确定或稳定性已通过。2026-10-07 19:49已备份A19、
拷入A20并完成四文件读回校验及安全推出；A20已单次实机：连续raw正确但native/overall报错，严格验收未通过；完整日志已回收，
下一步发布前context诊断见[CONTEXT_AUDIT.md](CONTEXT_AUDIT.md)。冻结接收器的旧stderr“events”标签仍是control别名。

字段参考：[Linux Tegra XUDC驱动](https://code.googlesource.com/linux/torvalds/linux/+/9f7853d7609d59172eecfc5e7ccf503bc1b690bd/drivers/usb/gadget/udc/tegra-xudc.c)，
DB偏移4/target移位8及MFINDEX偏移0x48与本地字段复核相符；Linux行为不能替代HOS实测。
