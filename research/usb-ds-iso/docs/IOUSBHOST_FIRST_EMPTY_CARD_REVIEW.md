# 第一次 IOUSBHost 空窗口读卡核验（2026-10-12 19:54）

后续：控制广播审计已修正，同一原始证据重审完整性通过；原拒绝记录保留，政策仍未接受。见[重审说明](IOUSBHOST_CONTROL_TRACE_REVIEW.md)。
已回收本次完整启动日志4411bytes；A23/HOS22.5.0/目标BuildID一致，runtime安装result0、record21。
设备STATUS头保持fresh/idle，前后原始168bytes与主机journal绑定；完整日志中提交、timing和终结记录均0，
未见burst/cancel/frames控制。主机一次提交、一次callback，960槽status0且completeCount0的结果保持不变。
这支持本次无设备TD观察，不能据此接受原生空槽政策或证明USB总线行为。

## 控制记录的差异

当前分析器保守返回 observation_complete=false，唯一原因control_trace_does_not_match_plan。
原始日志含4条vendor记录，接口顺序0、1、0、1，均为c1/51/0/2/168。
每条后紧跟对应接口的“wIndex mismatch, ignoring”；两个有效STATUS回复来自主机原始journal。
当前control_trace把EP0方括号字段按单调序号处理，要求两条记录，因此拒绝实际设备日志。

source/uvc/uvc_device.c的_handleSetupPacket先分流g_isoInterface到_handleIsoSetup，不输出通用EP0行；
其余接口先输出EP0[interface_index]，再检查wIndex并忽略不属于自己的请求。
UvC服务循环按control、streaming、iso接口依次处理SetupEvent，源码也明确记录广播行为。
因而四行与两次请求分别广播到接口0/1的解释一致，不是四次STATUS回复的证据。
日志没有请求唯一ID或总线捕获，不能从重复文本无条件去重；旧两行Mock验收也不能直接套到实机。

原控制检查失败报告原样封存，另存来源源码和广播形状核验，没有修改分析器、重试实机或接受基线。
下一步可在电脑上设计明确区分接口标签与请求序号的控制日志审计，验证重复、缺失、交错及额外控制的拒绝条件，
然后重新离线审计同一份证据；不需要重跑空窗口或部署设备新版本。
空槽原生政策、callback排空、总线相位、根因和长期稳定性仍未确认，burst入口保持关闭、次数0。

## 卡与冻结证据

四个部署文件SHA256与上次A23一致；21份错误报告无新增、变化或移除。
只读取日志/文件/报告，未写卡、未发起USB测试，没有可部署的新设备版本，因此未重复拷入文件。
19:54:59+08正常推出disk4并确认挂载消失。

- collection：/Users/livcm/Documents/Developer/Git/SysDVR-UVC-Capture/research/usb-ds-iso/private/collections/A23-IOUSBHost-no-td-20261012-195405
- 读卡周期（含原始日志、四文件备份、报告、源码、原检查结果、磁盘身份和推出记录）：/Users/livcm/Documents/Developer/Git/SysDVR-UVC-Capture/research/usb-ds-iso/private/card-cycles/20261012-195405-A23-IOUSBHost-read
- 日志SHA256：5f905d947fc62ca6cf677e2ebba1aaa3a04bfcf76e34a481a97d7243e4b25c6d

本次冻结证据不改写；后续工具修正应将重审结果另存新目录。
