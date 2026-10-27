# A21：ISO6 发布前硬件端点上下文

A21已单次实机，context配置匹配但缺一槽，严格失败；完整设备日志已核验。
本页的构建、部署及采集步骤是该版本的历史说明，卡上后续版本为A23。
最新阶段见[当前状态](STATUS.md)，后续条件见[测试计划](TEST_PLAN.md)，不按旧步骤直接重测。

## 历史设计与验证

2026-10-07，A20完整设备日志已回收，安装result0/22条runtime edit、唯一seq1/URB387
及status3/3072终结均确认，四部署文件匹配，无新增错误报告。prepare0.052188ms、
post0.221146ms、post-to-ACK0.000417ms、ACK0.0925ms，handler至ACK0.36625ms。
原生16包E00002ED/overall E000400E；raw精确192且连续indices68..83/全部delta0。
ISO5选帧/原tail前/后MFI均12290，TD0/TD1成功ED软件MFI12546/12554，相隔8tick。
这些证据仍不能确定设备调度、原生主机状态或总线数据PID哪一层是根因。

A21的设计目标是补足硬件端点上下文证据。HOS原`0x30B50`安装函数从controller+0x22050
取已分配context表，按endpoint index*64取条目；EP83为index7/offset0x1C0。
原函数`0x30C1C..0x30CEC`写原bInterval、类型、CERR3、MPS及maxburst，
`0x30D40..0x30D74`写平均TRB长度/MaxESIT及cerr_count。配置规则与
[Linux Tegra XUDC驱动](https://code.googlesource.com/linux/torvalds/linux/+/9f7853d7609d59172eecfc5e7ccf503bc1b690bd/drivers/usb/gadget/udc/tegra-xudc.c)
的context字段/初始化相符：device原bInterval应为4，不能套用host的interval-1编码。
该参考只能辅助字段命名；不替代本机HOS实测，也不把sequence_byte当已验证DATA PID。

A21在16TD组装完成之后、第一cycle发布之前，读取EP7 context的前32bytes，
保存到私有112byte mailbox。只读该context，不修改配置，不重新加载端点或改变MMIO。
ISO6 magic364F5349；0..71 common header及首两成功ED/首匹配错误保持原样。
72为参与选帧的MFI，76为context_valid（提交前清0，32bytes保存后置1），80..111
为原context dword0..7：info0/info1/dequeue low/high/tx_info/sequence/errors/progress。
有效标记1、MFI<16384及首FrameID与选帧关系一致才解码；无效记录可含陈旧数据。
配置不匹配时保留原始words并报告差异，不把它们从证据中排除。

重点核对state1/type5/interval4/MPS256/maxburst0/mult0/MaxESIT256；同时保留
DCS/64bit dequeue、avgTRB、edtla、sequence_byte/partial_td、cerr_count、data_offset/
num_trbs。DMA可能同时更新context，两个向量load也不是原子快照；context_valid
不是事务ID，也不证明硬件服务时间或DATA PID。读数在发布前，不能当完成时状态。

A20的原tail前后MFI诊断本轮移出，保留选帧MFI；恢复原tail的尾跳转方式，保留
原调用者stack/LR/返回值及原tail字节。FrameID计算、lead32/MPS256、16独立TD、
首cycle最后发布、两DSB及错误保留DMA/禁止重投不变。680bytes位于684bytes RX
padding内，report/STATUS为112/168bytes。诊断路径时长可能变化；单次实机及完整日志结果见下文。

```sh
python3 research/usb-ds-iso/tools/build_patch.py --burst --event-audit --context-audit \
  --frame-lead 32 --explicit-all --mps 256 \
  --out research/usb-ds-iso/private/packages-A21-context-audit
python3 research/usb-ds-iso/tools/package_experiment.py --burst --revision A21 \
  --packages research/usb-ds-iso/private/packages-A21-context-audit
```

A21历史单次采集步骤为匹配模块/IPS部署后重启；USB2/HS、视频关闭、host64/request192/wait40ms/
256slot、单次。验收仍为16连续有序包/native及public全0/exact192/overall0，自身URB
status3/3072与terminal1/bitmapFFFF/actual3072。context配置观察单独记录；匹配不
代表传输成功。完成URB不取消；保留DMA时先保存证据再取消，无重投。回收完整
安装/唯一提交/ticks日志。下一版应由实机context结果决定，不据本地仿真宣称根因。

A21本地验证/部署：39项测试通过（36指令/客户端/decoder，3冻结receiver）；
247 ring起点/两cycle、context读取在gate前且不写原context、stale有效性、错误保留、
原tail/stack/LR/callee-saved、STATUS/共享EP0、receiver错误负例均通过。
ISO2/3/4/5补丁及A18/A19/A20 receiver重建逐字节一致；runtime安装22记录
预检/幂等/部分写入/读回失败回滚、A/rollback构建和NPDM通过。
2026-10-07T20:09:09.706612+08:00已备份A20、匹配部署A21，四文件读回核验及正常安全推出完成。
本地验证包manifest保留构建时状态；实际部署见`private/deployments/latest-A21.txt`。
以下为部署后实机及读卡结果。

2026-10-07 20:13首次单次实机已完成：16包raw/native/public/overall成功，
indices80、82..96，缺槽81；首FrameID1853声明首槽80，首包delta0、其余+1。
context配置匹配，state1/type5/MPS256/interval4/MaxESIT256/burst0/mult0，
sequence/edtla/partialTD/progress均0。自身URB387/status3/3072完整终结，无取消和重投。
严格连续性未通过；2026-10-07 20:21完整5654byte日志已读卡核验：HOS22.5.0、
目标BuildID、runtime result0/22条记录、唯一seq1/URB387及status3/3072均匹配。
四文件仍匹配，15份既有错误报告无新增或变更。prepare0.052865/post0.236927/
post-to-ACK0.000365/ACK0.177969/handler-to-ACK0.468125ms。
collection指针`private/collections/latest-A21.txt`，run指针`private/runs/latest-A21-run.txt`。
后续A22保持ISO6及首包显式lead32，仅后15TD改用SIA1/FrameID0；见[FOLLOWUP_SIA.md](FOLLOWUP_SIA.md)。
