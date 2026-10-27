# A23 quiet 候选接收器与六项材料收集（2026-10-15）

已把[隔离捕获与文本日志的设备候选](A23_QUIET_WINDOW_CANDIDATE.md)接入新独立接收器、
启动工作流与收集器。设备仍是上轮 ae65…运行 recipe / 56778…ELF，没有重建设备程序。
新链路显式关联 NPDM、配置及主线程栈请求，拒绝旧记录和旧回执。

原生接收器与注入入口各 14 个编译单元完成链接；12 组等待循环、5 次实际序列化模型、
25 组收集完成，28 项新增及此前 154 项相关回归合计 **182 项通过，0 失败、0 错误、
0 跳过**。软件材料匹配仍不认证物理同一次运行、USB 实际
完成、实际内核栈预算或原超时原因。未签发次数、有效采集、调用真实 IOKit/SDK 对象、
访问 USB/SD、执行 ARM、打包或部署；新离线记录 remaining=0、acquisition_enabled=false。

## 新关联范围

[设备身份工具](../tools/a23_quiet_device_binding.py)只接受封存 quiet 候选的六份原字节
材料：full.elf、recipe.json、symbols.txt、recipe header、sysmodule.json、main.npdm。
既核对各文件摘要，也核对 recipe/header/ELF 两份静态对象、quiet 窗口策略、recipe
中的配置摘要，以及 NPDM META 中的栈请求 8192、priority 44、CPU 3。复制后的同字节
材料可供离线验证；旧 V3 材料不接受。旧接收器也继续拒绝新 quiet 材料。

host binding schema 为 A23-quiet-host-device-binding-1，configuration 为 quiet-window-30s。
父输入 a7ae…仍是 recipe 中保留的 V3 来源字段，和 quiet 运行 ae65…分开；本轮新增
177 份 host 输入也不冒充设备 recipe 的输入集合。NPDM 与配置摘要、栈请求在下列
各层显式出现，不只依赖一个合并摘要：

| 层 | 新关联 |
| --- | --- |
| 构建 metadata、describe、零次数 record | schema 3，quiet 设备及六项材料，绑定接收器程序和 manifest |
| 消费回执 | schema 3，运行 recipe、ELF、NPDM、配置、主栈请求、device binding 摘要 |
| 进程与 SDK 独占记录 | 原记录 schema 保留，checked/claim 中完整比较上述新字段 |
| 验证材料门禁 | schema 3，必须绑定此接收器及全部新字段，不接受旧验证或错误主栈请求 |
| 收集主结果 | 新 quiet collection/analysis schema，内层 EXE3 匹配不能覆盖外层身份失败 |

## 原生检查与启动边界

[构建工具](../tools/build_a23_quiet_receiver.py)冻结 177 份输入，从原封存源派生三份 native
单元和一份常量头；没有修改旧 170 份输入或旧接收器。新[原生检查](../host/a23_quiet_device_guard.inc)
在进程开始及选定设备交接时核对当前/冻结六项材料、派生源码和完整 manifest；另读取
NPDM 的 META/主线程字段。身份字段还进入嵌入式构建描述，重写文件后重算外层摘要
不能替换程序内的预期。交接在 SDK claim 后再次检查，发现变化则保留记录且不打开 SDK。

[新工作流](../tools/workflows/capture_a23_quiet_receiver.py)没有默认票据或 issuer。
零次数记录在加锁、创建 run 和启动进程前拒绝；仅在注入测试中模拟 prepared 单次
记录，确认先持久化消费、再写回执和启动。回执写失败或启动失败不重试，130 秒进程
观察超时不 kill、不终止进程，也不封存仍变化的输出。正式 offline-record 在封存包内，
保持零次数；未来如准备测试，应另建独立可变记录，不改这份封存。

## 收集与负向检查

[收集器](../tools/collect_a23_quiet_execution.py)封存等待/SDK/EXE3 与六项设备材料及身份
记录；重分析只用包内字节，不沿记录中的设备路径读取当前文件。包可移动，保留
重复/部分回执、缺失主文件、保存失败等原始材料；不把内容可读等同于 commit 已确认。
原有大小、数量、路径、符号链接、重复 JSON、目录与 seal 检查继续生效。

25 组模型分别包括：

- matching、large-clock 两组软件整链完整。
- sequence/shape 两组执行内容不一致；primary receipt failure 与 missing primary 两组
  仍可内部比较，但保持不完整。
- 19 组外层失败：父输入冒充运行 recipe，错误 ELF、binding、NPDM、配置、主栈请求，
  bool 冒充整数，v1/v2/部分/重复回执，缺失或错误的进程及 SDK 记录。这些组的内层
  等待/EXE3 仍完整，但外层身份比较失败，主结果不能报告完整。

[28 项检查](../tests/test_a23_quiet_receiver.py)还核对：原生六项材料变化拒绝、选定设备
交接前 NPDM 变化拒绝、重算局部摘要仍有 NPDM 字段矛盾、两代候选相互拒绝、错误验证
材料不消费、文件独占记录不可重用，以及失败/超时保留。所有测试用新建临时副本与
注入启动器，没有运行有效许可的 acquire；消费状态仅是标明来源的模型。

## 封存与续接

审查：`private/analysis/A23-quiet-receiver-review-20261015`，1546 条 manifest；其中
receiver-build 单独 194 条。审查 manifest 摘要：
`1f8459313dadb1fa60ca1b0216df8f213756af390a36b5e2bd3b474a6a141faf`。
新 receiver 摘要 `0a99ee3665c8b3cfcd7af17a7904adeb8228b47bf315594ea6e2d39e35f461d6`。
新 device binding 摘要 `e56f949870b19d81a6bfff8bd6c8282beed0e8372fa850bd36ac8768a347a517`。
新 offline-record 是可核对的构建结果，不是已签发的测试许可。

验证：`private/analysis/A23-quiet-receiver-validation-20261015`，12 条另行封存，保存
182 项回归结果、收集分类、实时记录、旧封存重核和构建关联。验证本身不签发次数。

此前 21 份封存共 5523 条重核，旧 170 份输入、七份生产文件、三份实时票据及两个旧
offline-record 保持。新设备自身的栈/同步调用耗时没有因 host 关联完成而得到证明。

下一步回到这份 quiet ELF 的诊断必需路径：按新地址绑定 USB 等待对象、静默条件下
owner 的调用路径，以及双 join 后的文件名/正常与失败保存。保持不把给定参数剖面提升
为线程上界，不复用旧 ELF 的栈证书；形成诊断准备材料后再决定一次独立设备实验。
当前所有剩余次数为 0，原 16.395292ms 超时根因未知。
