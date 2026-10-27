# lead32 判读、收集与一次入口（2026-10-17，Asia/Shanghai）

后续实测已完成：[lead32首次有效实测及回收](A23_LEAD32_FIRST_LIVE.md)。16包准确载荷及所供设备链完整；新增未归因ERPT仍待查。两条记录均0次、有效记录已回收并弹出。下文“未签发/未启动”等仅指本页离线封存时的状态，当前以实测页及pending为准。

lead32 的独立静态判读器、证据收集器和一次执行入口已完成离线验证。**80项检查全部通过，正式 lead32 记录仍不存在，次数0，接收器未启动。** 窗口错位仍是假设，没有新实机结论。

接收器沿用[上一轮候选](A23_LEAD32_RECEIVER.md)，没有重新构建设备固件或部署文件。新流程显式复用同一个path-span包，同时要求匹配的部署回执、只读回收和安全弹出回执；现有记录支持下一轮使用相同设备材料，不需要为这次主机改动重写卡。

## 新判读与收集

新增独立模块，保留全部原始字节，不把lead32记录改写成lead64。新SDK判读器只接受第2版计划及4/2/2ms预算，检查current+32、帧号范围、精确整数时间换算、入队/触发/回调次序、自己的回调指针和保存收尾。旧64计划被拒绝，旧判读器也保持不接受新计划。

在已经封存的34份协调器模型和12份等待模型上重新判读：32份协调器记录有效，2份故意保存失败的checkpoint保持不完整；11份等待记录有效，启动前中断模型保持缺少begin的前缀结论。这是静态复核，不是再次执行真实SDK或USB。

EXE3、primary、LCP1与第6代build/record/receipt/claim的比较分层保留。28组收集场景覆盖完整链、缺件、截断、坏CRC、上下文前缀、错误recipe/writer/频率/nonce、多个LCP1、主记录不一致、旧回执、混入lead64、NPDM和SDK身份不匹配、缺少进程claim及重复JSON键。多份LCP1不自动挑选；不完整文件不补齐、不删除。

完整注入模型可得到 supplied_chain_complete=true，表示所供字节和顺序自洽；source/physical/hardware/root_cause/usb_strict_pass/cleanup/allow_next_burst 等认证仍为false。静态收集包可搬移后复核，无需重新读取live build；新增文件或改动原字节会被拒绝。原有“三次首TD CC23/零载荷”的实测结论没有被覆盖。

## 一次入口与材料范围

`tools/prepare_a23_lead32_once.py` 默认只预览，不写正式记录；`--issue` 仅供下一次人明确要求开始诊断后使用，必须同时提供 `--deployment` 与 `--recovery`。范围绑定：

- 第6代lead32接收器的完整构建、原有59项接收器验证及同一六设备材料。
- 本次工作流审查摘要及10项新来源的实时哈希；旧241项源码保持，新闭包251项。
- 已核验的path-span包、四部署文件、部署读回/弹出记录，以及匹配的只读回收/弹出记录。

部署包封存的旧接收器manifest只证明该设备包的来历；新范围明确标识 device_package_reused，并独立绑定lead32主机材料，不把旧主机manifest冒充新构建。

只有新记录才能消费一次：验证通过后先持久化remaining0并禁用采集，再写回执和启动接收器。启动或回执保存失败均不补次；进程超时保留未决进程和可变输出，不强杀、不封存仍在写的输出。退出码0但缺少有效主机材料也不能通过。默认离线记录、已消费记录或旧记录在建锁/启动前即被拒绝。

80项回归由21项新工作流检查和59项已有检查组成，无失败、错误或跳过。签发/消耗/启动失败测试只在`/private/tmp`的一次模型记录中执行，进程启动被替换为模拟对象；没有对项目的正式记录或硬件执行这些操作。

## 当前封存与现场续接

| 材料 | 条目 | SHA256SUMS摘要 |
| --- | ---: | --- |
| `private/analysis/A23-lead32-workflow-review-20261017` | 1346 | `50868a70d91b9632256d5ef1dd0f08cc5ce428f3a4b175ba4da2ee9de1f7b223` |
| `private/analysis/A23-lead32-workflow-validation-20261017` | 2 | `5cd6c9efa3efffa33ee5f94d6d772ca09cac281431eb696bdd334d9cf19b511e` |
| `private/analysis/A23-lead32-ready-preview-20261017` | 3 | `a0737663053c36afb970a9e7e1751a1d529139183709d9b8f85d75b2dac622b7` |

预览目标为 `private/analysis/A23-lead32-once-20261017-interface2.json`，**文件没有创建**。dry-run只核验离线构建，返回remaining0/acquisition_enabled=false。三份既有现场记录仍failed_no_retry/remaining0，7生产源、3旧票据、3离线记录保持。SD上次于00:21:19+08安全弹出，本轮无读卡、写卡、USB请求或开机操作。

续接读取 `private/analysis/A23-lead32-pending.json`。下一项是一次新的lead32实测：收到明确开始指令后才签发；先让主机进入WAITING，再提示用户装回SD、连接Switch并fresh启动CFW，不等SysDVR初始化结束。执行后再按既有流程关机、只读回收和弹出。

验收仍要求16包逐字节正确、连续有效槽、原始状态和自己的完整URB/ISO7完成关系；只有回调0或进程退出0不够。若首TD仍CC23且零载荷，保留原件后再研究设备发布/doorbell和事件来源，不自动重试。当前软件帧比较没有独立对齐两端帧域，设备CC23语义和根因仍未确认。
