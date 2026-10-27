# 首次 SDK burst 读卡复核（2026-10-13 17:43，Asia/Shanghai）

完整设备日志已只读回收，6041 bytes，SHA256 `81337a5f62f4357f2045a48a1e0640953cb9bbf940c6c036882b968645a1e7de`。
4个部署文件逐字节读回核验，与上次一致；21份错误报告无新增、删除或内容变化。
UUID匹配的SD卡disk4于17:43:49安全推出，挂载点消失。本轮未写卡，USB测试调用0。

## 设备与主机观察

启动日志记录A23、HOS 22.5.0、预期Build-ID、runtime patch result=0/record=21。
同一连接片段内出现STATUS→BURST→STATUS三组广播日志，分别为
`c1/51/0/2/168`、`41/54/1/2/0`、`c1/51/0/2/168`。
每组在接口0、1各记录一次并紧跟wIndex mismatch/ignoring；这是接口分发标签，不能当成两次总线请求。
完整日志还有其他连接/断开片段，不把整份日志视为单一连接，也不独立认证主机与设备采集来源。

BURST setup确实到达Switch的接口0/1分发记录。未出现ISO submit、ISO timing或ISO终结记录。
主机原始前后STATUS仍完全相同、IDLE/seq0；控制16.395ms返回Timeout，随后ISO停止并返回Aborted、有效包0。
不能再把这次失败解释为“请求从未到达设备”；接口2是否执行及准确停止分支仍未确认。

## 电脑上可以继续检查的路径

`source/uvc/uvc_device.c`中，ISO接口在通用EP0日志之前进入专用handler；匹配接口2的请求没有该通用日志。
BURST分支的PENDING/RETAINED、usbDsGetSpeed错误或非HS检查会直接stall并返回，没有专门分支日志。
提交记录在PostBufferAsync及_ctrlAck之后输出，因此缺少提交日志本身不能证明没有调用PostBufferAsync。
_ctrlAck执行零长度IN状态阶段，_ctrlInXfer等待上限为1秒，失败后stall；SDK控制请求timeout为16ms。
这些源码位置提供下一步离线研究方向，尚未证明时间上限差异或某个早退分支就是根因。

## 保存与结论边界

只保存失败collection，严格验收仍失败（缺ISO7、完成状态及提交/终结关系）。
主机journal/core/final字节绑定成立；设备日志字节绑定成立，来源及完整主机设备关系未认证。
不修改审计规则；hardware_verified、usb_strict_pass、baseline、callback_drain与allow_next_burst均false。
独立burst凭据保持failed_no_retry/remaining0，仅将device_log_pending更新为false。
旧no-TD和serial凭据哈希保持。原始实机run与finished数值1保持原样；无重试、无新部署。

本地证据目录：
- `private/card-cycles/20261013-174348-A23-IOUSBHost-burst-read`：原始日志、部署文件、报告、读回/推出结果、独立观察及前后凭据。
- `private/collections/A23-IOUSBHost-burst-failed-20261013-174348`：冻结主机与设备失败collection。

下一步在电脑审查ISO handler早退、SetupEvent分发和EP0状态阶段；本次读卡不追加实机测试。
