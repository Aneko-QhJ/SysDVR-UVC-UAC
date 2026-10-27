# IOUSBHost离线描述符与证据链（2026-10-12）

接续[接口与所有权审计](IOUSBHOST_TRANSACTION_AUDIT.md)，已完成描述符预检、模拟证据写盘、
独立分析器及集成验证。所有运行均使用提供的字节或MockTransport；USB0、SD0。
新格式只接受simulation，不能作为实机成功、设备日志验证或新采集权限。
历史三次native/raw分歧、32轮serial-clock成功、当前阶段和剩余次数保持不变；根因仍未知。

## 描述符匹配边界

[io_usb_host_evidence.m](../host/io_usb_host_evidence.m)中的SDK matching dictionary函数锁定
1209:ca57、interface2/classFF/subclass49/protocol1及HS，未调用该函数或枚举注册表。
纯字节预检验证设备身份、配置totalLength、TLV边界、接口/端点数量、重复alternate及唯一目标，
要求alt0/endpoint83/ISO/interval1/MPS256，拒绝SS及旧interval4。
允许无关UVC接口存在，但只返回实验接口信息。配置字节来自调用者，不能据此证明当前设备配置。

SDK matching dictionary签名和常量已编译核验；尚无设备打开/claim或自动选择服务代码。
多个服务候选必须拒绝，不能将描述符内部唯一误当作注册表服务唯一。
后续还需关联设备与接口服务、固定registry身份、处理detach和真实缓冲区映射。
描述符getter及打开可能触发USB请求，不能包装成无副作用的只读实机预检。

## 写盘与释放

`A23SaveSimulationEvidence`在owner的串行队列上工作，限Completed或Rejected且存储仍保留。
父目录由调用方提供且须可信、无其他写入者；目标子目录通过mkdirat独占创建，拒绝重用或symlink。
各文件通过openat/O_EXCL/O_NOFOLLOW创建，0600权限，处理短写/EINTR，fsync后完整逐字节读回。
它保存以下内容，不转换overall或只挑出成功包：

| 文件 | 内容 |
| --- | --- |
| raw.bin | 全部184320bytes，包括空槽和错误槽 |
| transactions.bin | 原始960×28byte SDK交易结构；status/request/offset/complete/time/options |
| metadata.json | 原owner字段、scenario、simulation标记、保存时state/callback数量、abort error |
| SHA256SUMS | 上述三文件的完整哈希 |
| COMMITTED | SHA256SUMS的哈希，在其余文件校验及目录fsync之后写入 |

最后再次fsync子目录和父目录，函数成功后才调用owner的保存确认释放原存储。
失败保留部分目录及原存储，不能在该目录重试覆盖；后续保存须另建目录。
COMMITTED和哈希用于完整性检查，不证明作者、来源、USB真实性或磁盘断电行为。
分析器不把文件存在当作函数成功或DMA所有权确认。
现有owner的Retained/陌生回调指针状态不允许通过这个写盘入口解除隔离。

保存的是首份完成快照和保存时计数；之后的重复回调不会覆盖证据。
未来实机收集器还需在整个会话维护迟到回调/关闭事件记录与停止机制，不能把保存时计数1
当作已经排空framework的用户回调。当前没有下一请求或实机执行入口。

## 独立分析

[analyze_io_usb_host_evidence.py](../tools/analyze_io_usb_host_evidence.py)不依赖owner或写盘实现，
先核验精确文件集合、尺寸、非symlink、commit及SHA，再解码全部960条packed little-endian记录。
它检查每条request192/offset=i×192/options0/actual≤request及元数据类型、backend、时间和状态。
允许即时回调先于submit返回，不错误要求arrival≥return。

single_burst内容验收要求16个连续槽、actual192、sequence递增（包括65535→0）及全192byte模式；
空槽raw必须全零，首包位置按实际值而非固定522。no_td只检查没有actual和raw全零。
native验收独立检查整体0、有效槽status0、没有Invalid、未超时/取消错误、单次正确回调。
空槽状态完整统计保留，不预设新API必须报Underrun，也不将某种空槽状态加入实机许可名单。
no_td的模拟logic pass只证明这些软件条件，不代表新backend空窗口已完成实机验收。

输出分别给出payload_matches、active_native_clean、callback_clean、transactions_finalized和
simulation_logic_pass；hardware_verified、device_evidence_verified、usb_strict_pass恒为false。
该版本拒绝hardware模式或hardware_verified=true；没有设备STATUS/ISO7、安装及完整日志解析。
有效模拟包且logic pass返回0，有效证据但logic fail返回1，损坏/未知格式返回2。

## 验证与冻结

Objective-C集成测试覆盖提供字节的描述符拒绝/唯一性、无关UVC接口、pending禁止保存、路径逃逸/
已有目录/symlink拒绝、RLIMIT_FSIZE模拟raw中途写失败后保持存储，以及六个新目录的保存释放。
AddressSanitizer/UndefinedBehaviorSanitizer通过，SDK matching函数只编译未运行。

独立15项Python检查全部通过，包括Objective-C输出六包的交叉核验：clean/no_td为模拟条件通过，
native-error/timeout/rejected/duplicate为失败。原始NoResources E00002BE和有效槽NotResponding
E00002ED仍按原值保存；不改成NotSent或忽略错误。
另覆盖未重新封装的字节损坏、重新封装后的语义损坏、commit/文件缺失、重复JSON/manifest、
symlink、未完成Invalid、sequence及杂散raw损坏、时间顺序和伪造模式/字段类型。

```sh
/usr/bin/clang -std=c11 -fblocks -fobjc-arc -Wall -Wextra -Werror \
  -fsanitize=address,undefined -framework Foundation -framework IOUSBHost \
  research/usb-ds-iso/host/io_usb_host_transaction_owner.m \
  research/usb-ds-iso/host/io_usb_host_evidence.m \
  research/usb-ds-iso/tests/io_usb_host_evidence_test.m -o /tmp/a23-evidence-test
/tmp/a23-evidence-test /tmp/a23-simulation-new-directory
PYTHONDONTWRITEBYTECODE=1 A23_SIMULATION_BUNDLES=/tmp/a23-simulation-new-directory \
  /opt/homebrew/bin/python3.12 -m unittest discover \
  -s research/usb-ds-iso/tests -p test_io_usb_host_evidence.py -v
```

冻结产物：private/analysis/A23-IOUSBHost-evidence-review-20261012/，包括源码、六个模拟包、
独立结果、故障残留字节、验证记录及SHA256SUMS。故障模拟symlink只在临时测试目录中创建，
冻结包不复制该symlink。包内实际文件以根SHA256SUMS为准。
当前采集状态SHA256仍为a592fc6bfe95f34c7a716f37dd0974e6481cfca04686354f1dfd6a77b8615ecd。

## 电脑与实机的剩余工作

后续[离线会话与设备关联](IOUSBHOST_SESSION_AUDIT.md)已实现下面的生命周期模拟、detach/迟到
事件记录与独立STATUS/ISO7/日志解析；真实SDK资源和新采集绑定仍未完成。

电脑上可继续实现并模拟设备/接口/pipe生命周期、detach、迟到事件日志、设备STATUS/ISO7及
完整启动日志关联，定义新backend空窗口和单burst的独立停止条件与冻结入口。
真正的服务唯一性/打开权限、映射、HS端点当前配置、接收/取消/断开时序和新API空槽返回值
需要实机确认。尚未准备这些步骤，不修改A23设备补丁或experiment.py阶段。
