# A23父输入、运行recipe与ELF的独立绑定候选（2026-10-15）

已在新的隔离候选中补齐上轮发现的摘要层次缺口。新接收器描述、构建清单、零次数记录、
消费回执、进程/SDK核销及EXE3收集统一使用设备实际运行recipe，并分别保留父输入和
最终ELF摘要。旧122份源、旧接收器/记录、七生产源、三票据及原封存没有改动。

新候选完整编译链接，12组循环注入、5次V3序列化模型、16组收集及22项新增检查完成；
与此前106项相关回归合计128项，0失败、0错误、0跳过。新记录仍为offline_build_ready、
remaining=0、acquisition_enabled=false。没有签发次数、有效采集、真实IOKit/SDK对象、
USB/SD访问、设备执行或部署；原16ms超时根因仍未知。

## 身份的具体含义

| 标识 | 当前值 | 用途 |
| --- | --- | --- |
| parent_input_digest | `a7aed8c72e3334c083963fb734e2e62fc3d6ca5f612a4914365fd6a2388ca850` | V3父输入身份 |
| runtime_recipe_sha256 | `04e91db655a03fb1a61f1a92d9a1758928a868a5222ee2e9b641b82e2bddd2d7` | 30秒窗口程序写入材料的recipe；新记录recipe_sha256采用此值 |
| device_elf_sha256 | `dfa6414af2e3ce0b3d6950103aba0126a50b22dfd09d2aba6609252939a57813` | 最终设备ELF字节摘要 |
| device_binding_sha256 | 当前device-binding.json规范JSON的摘要 | 关联配置、上述身份、源目录及四项设备文件 |

[身份模块](../tools/a23_device_binding.py)检查封存window-30s配置、recipe.json、生成header
和ELF中两份32字节ep0CandidateRecipe一致，并核对最终ELF摘要。四项设备文件分别为
full.elf、recipe.json、symbols.txt和source/uvc/ep0_candidate_recipe.h。绑定源目录也是
标识的一部分，因此测试副本与正式候选的binding摘要可以不同；运行recipe和ELF相同。

这些标识只绑定电脑上的构建材料，不认证Switch正在运行该程序，也不提供跨时钟关联。

## 新构建和本机门禁

[新builder](../tools/build_a23_bound_receiver.py)从此前122份冻结输入及7份新增文件创建
129份源副本，在生成目录中派生三个原生单元及常量header，不修改原文件。新接收器仍
使用原有等待/SDK/线程退出策略；改变的是身份核对和说明字段，未构建新的设备ELF。

生成描述schema为2，`--describe`明确显示父输入、运行recipe、ELF与binding摘要。
manifest.json、device-binding.json和生成常量均绑定这些值。实际主程序与ASan/UBSan
注入程序分别从14个单元完整编译链接。新构建144条manifest，完整审查987条。

[原生核对片段](../host/a23_device_binding_guard.inc)在原文件门禁内核对：

- 构建中的设备描述及生成源/常量与嵌入的清单一致。
- 四项设备原文件和冻结副本都与嵌入摘要匹配。
- recipe_sha256必须是runtime_recipe_sha256；父输入和ELF分开比较。
- 启动前、等待交接时以及SDK文件核销之后均经过同一套文件检查。

构建目录新增`device-binding.json`与`device/…`。新封存按完整相对路径字符串排序，
原生端使用对应UTF-8比较，避免目录前缀与连字符文件名导致顺序不一致；旧封存不重写。
文件两次读取不能证明外部文件树在整个时段原子不变。

## 消费与核销

[新消费工作流](../tools/workflows/capture_a23_bound_receiver.py)要求schema 2记录及绑定
本次接收器、device binding和运行recipe的独立验证材料。没有签发器或默认票据路径。
零次数记录在创建锁、run目录或启动进程前拒绝。测试中的prepared/consumed记录全部
位于临时模型目录，不改实时票据。

schema 2消费回执保留receiver/build摘要、计划及preparation_id，新增父输入、设备ELF
和binding摘要，recipe_sha256改为运行值。消费先持久写remaining=0，再保存回执和启动；
回执写失败或启动失败也不返还次数。进程及SDK仍分别使用独占文件核销，不能重复。

进程核销保存已检查的完整身份，SDK核销将其与原回执及选定接口身份再次比较。旧schema
回执、父摘要冒充运行摘要、错ELF/binding、当前/冻结材料变化、重复或截断JSON等均拒绝。
注入程序只运行文件核对分支；没有调用接收器的有效许可acquire入口。

超时/未完成I/O仍保留进程与资源，不kill、不自动重试。原等待120秒、设备窗口30秒及
SDK控制阶段策略保持；新身份绑定不扩大这些时间预算。

## 收集主结果的关联

[新收集封装](../tools/collect_a23_bound_execution.py)保留原等待/SDK/EXE3收集包，另冻结
记录、构建元数据/manifest、接收器字节、设备四项文件，以及消费、进程和SDK核销原文件。
它从新记录的运行recipe取得EXE3解码预期，不再由父摘要替代。

比较依次要求设备文件/header/ELF内部一致，记录/构建/回执身份一致，进程核销绑定同一
回执，SDK核销绑定同一选定接口，再结合既有等待顺序、SDK快照、目标SETUP及STATUS
state/sequence比较。内层匹配不能掩盖外层身份失败。

收集前执行本地构建核验，重放时仅使用包内冻结字节，不追随device_source_root，也不
执行接收器。包可移动重放。包内并未复制全部129份构建源，重放不能独立认证二进制的
源码来源；build_source_closure_verified等来源/物理同run/跨时钟/USB权限字段仍为false。

外层限制512文件、32MiB及8层路径，拒绝符号链接、额外绑定文件和输入/输出重叠。
记录/回执变化留下未提交包。回执缺失、截断、重复字段或核销错误原字节保留为失败
比较，不能报告完整链。篡改分析后重算外层摘要仍会在重新分析原字节时被拒绝。

## 模型结果与边界

五次新序列化模型使用封存V3的13个header，唯一注入变化是把模型recipe设为实际窗口值。
请求、报告、STATUS和文件回执仍为注入，不执行真实请求处理器，也不修复历史捕获。

| 材料情况 | 主结果 |
| --- | --- |
| 匹配、极大独立设备时钟 | 给定材料一致且完整；所有物理来源/USB权限仍false |
| 缺外部主文件、设备主文件commit失败 | 身份与给定请求比较一致，但材料不完整 |
| SETUP形状或sequence错误 | 身份有效，内层请求/状态比较失败 |
| 父摘要作运行值、错ELF/binding、旧回执、部分/重复JSON | 内层仍可匹配，外层身份失败 |
| 缺进程/SDK核销、进程摘要或选定接口不符 | 内层仍可匹配，外层核销失败 |

16组收集、12组循环注入和[22项新增检查](../tests/test_a23_bound_receiver.py)还验证设备/
源码在交接前变化、重新封存的生成文件变化、只读模式、核销不可重复、验证材料绑定、
消费后失败不重试、未完成进程保留，以及注入工作流结果接入新收集的完整软件比较。

## 封存与后续

审查：`private/analysis/A23-bound-receiver-review-20261015`，987条manifest，SHA256SUMS摘要
`ebbaa6c22350dc55ac6732ab8908b4c886e6655cd7a8394970167d7832172552`。
构建：该目录的`receiver-build`，144条manifest；新offline-record为0，未签发。
验证：`private/analysis/A23-bound-receiver-validation-20261015`，保存128项回归结果及本次
构建/接收器/binding/运行recipe对应关系。旧接收器记录和三份实时票据保持0。

下一项回到同一份设备ELF的诊断运行成本：[上轮线程审查](A23_V3_RUNTIME.md)的TLS/
reent布局仍适用。视频/音频用户入口剩19792/11600字节，完整调用链尚无上界。只核
诊断必需格式、实际logger/vsnprintf外层及具体等待对象，计入包装帧并单列异常/回调。
同步文件日志耗时和实机并发影响仍未知，身份关联修复不构成设备测试放行。
