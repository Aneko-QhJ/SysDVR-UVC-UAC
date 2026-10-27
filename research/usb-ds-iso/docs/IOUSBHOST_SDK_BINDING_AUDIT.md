# IOUSBHost SDK适配与原始STATUS绑定（2026-10-12）

继续[会话审计](IOUSBHOST_SESSION_AUDIT.md)，完成SDK适配实现的编译与模拟故障注入、原始STATUS
记录，以及传输包/会话/STATUS/设备日志的独立封装核验。本轮只运行模拟对象；没有服务枚举、
真实SDK对象创建、IORegistry查询、USB请求或SD访问，没有修改采集阶段、次数或设备版本。

## SDK实现与模拟边界

[io_usb_host_sdk_adapter.m](../host/io_usb_host_sdk_adapter.m)包含真实SDK操作实现
`A23DormantSDKOperations`，签名以本机SDK为准，链接Foundation、IOUSBHost及IOKit通过。
当前provider只接受simulation operations；实际实现返回simulation=false，provider在首次
registry查询/打开之前拒绝。没有枚举程序、trigger、配置切换、reset或新的experiment入口。
测试仅注入AdapterOperations/AdapterInterface/AdapterPipe，不创建真实实现实例。

适配流程检查借用service token、打开前后的device/interface/parent registry ID及HS速度，
重新核对SDK缓存描述符、当前alt0/interface2和pipe83的ISO/MPS256/interval1配置。完整描述符
必须与选择时提供的原始字节一致，身份数字拒绝bool/float。唯一候选仍由会话层核验；适配层
不声称已实际枚举或持有服务。真实backend将来必须明确借用service的有效期及IOObject引用所有权。

主机data分配184320bytes，transaction共享映射26880bytes，分别验证精确length且对象不相同，
显式清零后交给owner初始化960条记录。实际SDK分配使用macOS26.4+的dataWithCapacity API；
Mock分配器故意填0x5a，测试确认provider清零，不假定SDK初始内容。打开后任一预检失败，
在没有ISO提交的条件下关闭lease并destroy一次；成功请求仍遵守原有完成/保存/ack后关闭的限制。

SDK interestHandler将消息异步转到会话queue；当前没有运行真实通知路由。
deviceDescriptor读取可能产生GET_DESCRIPTOR，因此“读取描述符”也没有在本轮执行。
cached configuration的内存长度由SDK契约提供，编译及Mock字节测试不能证明实际缓存、
真实IOBuffer映射/排他打开、通知到达、取消、断开或用户回调排空行为。

## 原始STATUS与会话边界

SDK实现的readStatus仅准备interface vendor IN `c1/51/value0/index2/length168/timeout3000ms`，
记录begin/end Mach ticks、BOOL结果、原始bytesTransferred及NSError domain/code。短回复只保存
实际返回的前缀，报告长度超过capacity时保留原报告值但不越界读取，不补零冒充168bytes。
它没有被执行。其source=`sdk_control_reply`也不能混入simulation会话冒充Mock证据。

新会话初始化参数requireStatusBinding=true时，必须在Ready后记录一次fresh before，才允许
唯一ISO提交；完成快照后记录一次after，才允许保存。`recordStatusPhase`只消费已经提供的
Mock回复，不发请求。每个status_observed事件保存原始base64、SHA256、请求tuple、返回长度、
请求结果/错误及Mach区间。before begin不能早于Ready，after begin不能早于callback和snapshot。
这些都是软件观测，不建立主机与设备时钟对齐或USB总线相位证明。

before要求完整168bytes、成功且无NSError、协议magic/version/endpoint正确、fresh IDLE/seq0/
URB0及相关头字段零。短/陈旧回复原文先写入journal，然后停止并禁止提交。
after短回复/请求失败/长度溢出同样保存原文并停止，仍可保存已完成的raw/transaction失败证据。
未记录after的完成请求不能保存确认或释放原存储；重复phase和错误阶段拒绝。
旧初始化参数仍默认不要求STATUS，不给旧journal追认原始STATUS绑定。

## 独立collection封装

[analyze_io_usb_host_collection.py](../tools/analyze_io_usb_host_collection.py)提供离线freeze/audit，
输入必须是可信、已经结束且没有其他写入者的Mock进程材料。它没有USB功能。封装包括：

- transfer/内既有五文件bundle，原格式及内容不改写。
- session.jsonl、status-before.bin、status-after.bin；两个bin直接解码journal原文。
- device-log.txt（明确supplied_mock_log）、collection.json（会话ID、scenario、firstFrame及关联哈希）。
- 根SHA256SUMS和最后写入的COMMITTED，共12个文件。

输出独占创建0700目录，文件0600/O_EXCL/O_NOFOLLOW；写入处理短写/EINTR，fsync和逐字节读回，
目录同步后最后写commit并同步父目录。写失败保留部分目录、不覆写或续写；COMMITTED只表示
封装字节完整，不意味着传输成功。已存在输出即拒绝。

audit核对固定文件集/非symlink/大小、各层manifest及commit，调用原有bundle和会话分析器，
再要求STATUS bin与自己的journal原始bytes完全一致，最后核对STATUS/ISO7/完整设备日志关系。
即使重新计算外层哈希，混入别的bundle、另一个会话、修改bin但未改journal、改source或时间
仍会被内部关联检查拒绝。没有密码学签名，可信输入整体重写或日志伪造不属于已证明的能力。

短STATUS属于完整保留的失败证据：collection_integrity_verified=true，但设备协议解析失败，
simulation_collection_pass=false。正常设备STATUS和payload不能覆盖原生错误、STATUS请求失败、
长度溢出或迟到回调。simulation_byte_binding_verified只证明提供字节在封装中的关联；
capture_binding_verified、firmware_bytes_verified、callback_drain_verified、hardware_verified、
usb_strict_pass恒为false。读取完整日志仍不能证明以后不会有新的回调。

## 本轮验证与冻结

18个适配场景包括正常路径、真实operations拒绝、无/布尔token、前后身份变化、float身份、
打开失败、描述符缺失/变化、active alt变化、pipe缺失、端点错误、两类分配失败和长度错误。
10个STATUS会话包括clean、short/stale before、short/error/overflow after、native error、
late after close、missing before、missing after。ASan/UBSan全部通过；原有16个生命周期场景回归通过。

60项Python检查全部通过且无跳过：新增16项collection检查，加既有44项。覆盖重新计算哈希后的
字节/会话/时间/source/tuple/类型错配、短回复、原生错误、迟到事件、独占创建、中途写失败、
symlink及未commit目录。10份会话、6份collection的22次独立CLI均返回预期结果：clean为0，
其余完整失败证据为1。损坏或不符合格式的输入返回2。

```sh
/usr/bin/clang -std=c11 -fblocks -fobjc-arc -Wall -Wextra -Werror \
  -fsanitize=address,undefined -framework Foundation -framework IOUSBHost -framework IOKit \
  research/usb-ds-iso/host/io_usb_host_transaction_owner.m \
  research/usb-ds-iso/host/io_usb_host_evidence.m \
  research/usb-ds-iso/host/io_usb_host_runtime_guard.m \
  research/usb-ds-iso/host/io_usb_host_session.m \
  research/usb-ds-iso/host/io_usb_host_sdk_adapter.m \
  research/usb-ds-iso/tests/io_usb_host_sdk_adapter_test.m -o /tmp/a23-sdk-test
# 第一个输出目录必须不存在；输入是本轮固定Mock字节。
/tmp/a23-sdk-test /tmp/a23-new-mock-sessions \
  research/usb-ds-iso/private/analysis/A23-IOUSBHost-sdk-binding-review-20261012/sdk-fixtures/inputs
```

本轮材料冻结于private/analysis/A23-IOUSBHost-sdk-binding-review-20261012/，包含最终源码、
SDK header哈希、Mock输入及原始回复、会话/collection、独立CLI结果、回归和sanitizer记录、
provenance及根SHA256SUMS。之前session冻结包122份文件只读复核通过，旧目录没有重冻。
采集状态SHA256保持a592fc6bfe95f34c7a716f37dd0974e6481cfca04686354f1dfd6a77b8615ecd，
stage与所有入口次数0不变，历史三次native/raw分歧仍为失败，根因/修复/长期稳定性仍未知。

电脑上下一步可冻结新backend的空窗口预检、单burst条件、pending退出和失败停止方案。
后续[空窗口观察方案](IOUSBHOST_NO_TD_PLAN.md)已落实固定计划/帧号绑定、失败停止和独立分布观察，
基线接受及后续burst许可仍为false；后续[运行条件准备](IOUSBHOST_RUNTIME_READINESS.md)
已实现服务引用、采样年龄预算及pending退出的模拟条件，真实行为仍待确认。
新transaction API空槽原生状态尚未知，不能套用旧backend的Underrun白名单。实际服务唯一性、
打开/映射、真实STATUS、空槽完成语义和取消/断开/排空行为必须连接Switch取得新证据。
