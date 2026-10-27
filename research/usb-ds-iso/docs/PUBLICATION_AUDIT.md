# A19：ISO4 发布阶段 MFI 锚点

A19已单次实机，原生状态正确但缺一槽，严格失败；完整设备日志已核验。
本页的构建、部署及采集步骤是该版本的历史说明，卡上后续版本为A23。
最新阶段见[当前状态](STATUS.md)，后续条件见[测试计划](TEST_PLAN.md)，不按旧步骤直接重测。

## 历史设计与验证

2026-10-06。A18 首次实机有 16 个正确 payload，native/public/overall 状态成功，
但首两包之间缺一槽。设备安装和唯一提交已确认；URB 完整终结，未重投。
首两成功 ED 的软件处理入口 MFI 为 2628、2644，差16。
此差值不能替代总线 trace，也不能把 handler 执行时刻当作事件产生时刻。

复核原模块 `0x30700` 事件循环：先检查事件 cycle，再在 `0x30898` 调用 hook，
循环继续处理可用事件，最后更新 dequeue。原 `0x31C74` tail 保留 endpoint 检查，
在 `0x31CDC` 写 doorbell。A19 producer 全部建好16个独立TD，经DSB后才发布
首TRB cycle，第二次DSB后转入原tail；测试未发现FrameID递增或ring回绕计算错误。
诊断应补充同一设备计数域里的发布阶段，尚不应补偿FrameID或更换调度常数。

## 布局

112byte diagnostics / 168byte STATUS / version1；ISO4 magic `0x344F5349`。
0..71 与 ISO3 相同，保留 terminal/bitmap/actual/首TRB/control 和前两成功ED。
首个匹配错误仍优先替换 TD1 槽，不允许后续成功清除错误或释放 retained DMA。

| 偏移 | 内容 |
| --- | --- |
| 0 / 4 / 8 / 12 | magic / 错误相对offset / 首TRB发布control / terminal |
| 16 / 20 / 24 | completed bitmap / actual sum / 首TRB虚拟地址64bit |
| 32 / 52 | TD0成功ED、TD1成功ED或首个匹配错误，各 raw event16bytes + MFI4bytes |
| 72 | 选帧时读到的原始MFI，直接用于 `(MFI >> 3) + 32` |
| 76 | 已建好所有TD，第一道DSB和首cycle发布之前读取MFI |
| 80 | 首cycle发布及第二道DSB之后，转入原doorbell tail之前读取MFI |
| 84 | phase_valid：0=未完成或陈旧；1=三个MFI锚点已写入 |
| 88..111 | 保留；可能陈旧，不能解释为事件、MMIO或有效数据 |

ISO4 不采样首过滤/终结后事件；保留原过滤和错误判定结果。每次接受新提交清除
两个event control sentinel及phase_valid。无效记录、phase_valid0及保留字节均忽略。
三个锚点写完后才设phase_valid1。报告复制不是原子事务；标志不是事务ID，
解码还核对MFI范围和首FrameID与选帧MFI的关系，但这些检查不证明快照原子性。

锚点只观测软件读取计数的阶段。偏移80不记录 `0x31CDC` MMIO写入的实际时刻；
中间仍执行原tail检查，也可能被调度中断。模16384差值无法排除整周期回绕。
即使未来观测到选帧至发布只有几个tick，也不能证明控制器在指定总线帧服务了TD。
诊断新增两次MMIO读取及记录写入，可能影响执行时长；调度常数冻结不代表执行耗时
与A18完全相同。锚点用于缩小发布阶段的不确定性，不单凭其数值确认缺槽原因。

## 冻结条件与验收

保持 HS / MPS256 / interval4 / device lead32 / 每TD192bytes / 16TD / 原doorbell。
主机从冻结的A17 host64-timing源码生成，只扩展magic兼容、使用本地协议头，
继续同一静态backend、request192/lead64/wait40ms/256slot、单次、fresh boot、视频关闭。
不得用退出0或public success替代 native status0，16包连续性条件不放宽。
另核对ISO4 phase_valid1及首FrameID关系；错误覆盖TD1时不计算两个成功ED的差值。

```sh
python3 research/usb-ds-iso/tools/build_patch.py --burst --event-audit --publication-audit \
  --frame-lead 32 --explicit-all --mps 256 \
  --out research/usb-ds-iso/private/packages-A19-publication-audit
python3 research/usb-ds-iso/tools/package_experiment.py --burst --revision A19 \
  --packages research/usb-ds-iso/private/packages-A19-publication-audit
```

备份并同时替换模块/IPS，重启。每个run目录只执行一次；失败即停，不重投。
仅pending/retained状态需要在保存证据后 `--cancel`，不能对已终结URB额外取消。
保存native/JSONL/raw/STATUS，回收完整Switch日志及设备ticks，确认A19安装和唯一提交。
在SD确认且实验包完成验证时，延续既有授权完成拷贝、读回校验和安全推出。

## A19本地验证、部署与实机结果

A19的29项测试通过，覆盖实际684byte机器码、247个ring起点/两种cycle、
FrameID及MFI回绕、三处真实读取顺序、首cycle最后发布、重复/foreign过滤、
匹配错误的DMA保留、取消后新提交清除sentinel、报告边界及原寄存器恢复；
同时验证真实客户端STATUS/EP0、解码器的陈旧/过渡状态和冻结接收器的负例。
原A18的9项机器码回归通过；默认ISO2和ISO3的inject.bin/IPS重建均与旧包
逐字节一致。runtime installer的22条记录预检、幂等和部分失败回滚通过。
A19/rollback构建及NPDM检查通过，报告/STATUS保持112/168bytes。

包位于 `private/packages-A19-publication-audit/`，含A/rollback、配套接收器、
解码器、manifest及SHA256SUMS。本地构建完成时未部署或实机，SD上仍为A18。
部署A19后执行冻结条件下的一次采集，核对三锚点及首两ED；
首两包空槽、原生状态和连续性仍按原验收标准判断。
旧stderr标签`events`仍打印首TRB control，不能当事件数；使用配套解码器。

2026-10-07 16:44已按用户拷卡指令完成A19部署：同一SD UUID、当时A18四文件
及A19包27文件校验通过，备份A18模块/IPS目录及3292byte旧日志，四文件拷入、
fsync/sync及读回SHA256一致，无新增或变更错误报告。SD已安全推出，此时尚未实机。
部署及A18回滚副本见`private/deployments/20261007-164456-A-A19-publication-audit/`，
指针为`private/deployments/latest-A19.txt`。当时安排插卡重启、HS/视频关闭，
使用本包冻结接收器按host64/request192/40ms/256slot单次采集。

2026-10-07首次A19实机：预检HS/fresh IDLE/seq0/URB0后，仅一次提交。16包内容
及native/public/overall状态成功，但indices72、74..88，首两包缺槽73，严格失败。
自身URB387/status3/3072、ISO4 terminal1/bitmapFFFF/actual3072，完整终结，未取消或重投。
三个MFI锚点均13533、phase_valid1/首FrameID1723关系一致；首两成功ED软件MFI
13778→13794，差16。锚点没有显示可分辨的计数变化，但不能证明零耗时，
也不包含原tail和实际doorbell写入的时间，尚不能定位缺槽原因。
证据见`private/runs/A-A19-HS-publication-audit-20261007-165130/`；
完整2766byte Switch日志已回收，A19启动/runtime result0/唯一seq1提交和
URB387/status3/3072终结确认；handler至ACK0.403333ms，无新增错误报告。
当时保留A19并安全推出。后续A20原tail前后采样见[DOORBELL_AUDIT.md](DOORBELL_AUDIT.md)。

字段参考：[Linux Tegra XUDC驱动](https://code.googlesource.com/linux/torvalds/linux/+/9f7853d7609d59172eecfc5e7ccf503bc1b690bd/drivers/usb/gadget/udc/tegra-xudc.c)。
其中 `MFINDEX`、FrameID/SIA字段和device context布局支持本次字段复核；
Linux的SIA提交不能证明本实验explicit FrameID的服务语义，也不能直接替换HOS行为。
