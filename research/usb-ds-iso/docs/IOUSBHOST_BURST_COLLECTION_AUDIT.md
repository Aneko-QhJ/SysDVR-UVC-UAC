# IOUSBHost 单次 burst 设备关系与 collection 离线审计（2026-10-13）

后续已实现并编译[独立SDK能力适配](IOUSBHOST_BURST_SDK_ADAPTER.md)；下文为07:28模拟collection阶段及其冻结记录。

原始 STATUS、主机 journal/core、完整 A23 启动日志、ISO7 和三组控制分发形状的
模拟字节绑定已实现。165 项相关 Python 回归通过、0 跳过；22 个原生注入场景通过 ASan/UBSan。
本轮没有 USB 请求、SD 访问或新实机次数。冻结目录：
`private/analysis/A23-IOUSBHost-burst-collection-20261013-072803`。

## 完成的审计

新工具 `tools/analyze_io_usb_host_burst_collection.py` 只有离线 freeze/audit 入口。
freeze 独占创建新目录，保留原始短回复和失败记录，逐文件 fsync/读回后最后写 COMMITTED。
没有自己的核心完成证据或缺失 before/after 原文时拒绝创建，不补零、不重构缺失回复。
写盘失败保留未提交目录；再次调用不能覆盖。审计限制固定文件名、大小、目录结构及普通文件，
拒绝符号链接、额外/缺失文件、重复 JSON 字段和不一致的 manifest/commit。

| 关系 | 检查 |
| --- | --- |
| STATUS 与主机记录 | 两份原文逐字节等于 journal Base64，哈希一致；outer manifest 重算不能消除不一致 |
| 主机 core | 沿用执行器独立审计，绑定 snapshot、callback、firstFrame、960 条原生记录和 16×192 包；错误不能被正确 device 字段覆盖 |
| 设备身份与完成 | 沿用设备审计：完整 A23/HOS22.5.0/BuildID/安装成功；唯一 submit/timing/终结；seq1、相同 URB/report ID、3072 bytes、终态3 |
| ISO7 | error0、terminal1、bitmapffff、actual3072，环指针/前两项事件 tag、原始 CC/actual/flags、frame/control/context 关系 |
| 控制分发 | 恰三组 before STATUS、trigger、after STATUS；每组接口0 request/ignore、接口1 request/ignore，保留六条 vendor 记录，不去重 |
| 设备顺序 | trigger 分发后 submit/timing，随后 after 分发；唯一终结在 timing 后，可由 after 处理期间或此前轮询产生 |

控制元组固定 c1/51/0/2/168、41/54/1/2/0、c1/51/0/2/168。
组内必须连续四行；ignore 绑定紧邻的错误接口请求。
额外 vendor、取消、错接口、缺失/重复、错序、窗口内标准/类请求、连接变化、SetupPacket 失败均拒绝。
初始枚举在诊断窗口外可存在。历史旧 backend 日志有额外 STATUS，不能冒充新的三组方案。
日志标签是接口号，缺少总线请求 ID；三组只能说明软件分发形状，request_count_verified=false。

此次也修正了主机模型对 report_count 的过窄条件。
`_pollIsoProbe` 在每次 GetReportData 后更新该值：有完成报告时可为1，后续轮询可为0；
历史旧 backend 保存的两份完成 STATUS 也分别显示1/0。独立单次请求候选接受0或1，
大于1作为多报告歧义保留失败，不据此修改其他 native status 或既有冻结材料。
这个判断是候选约束，尚未成为新 backend 的实机政策。

## 模拟来源及结果

原生 BurstMock 按共享 ABI 生成合成 ISO7 原始回复，report_count=1、URB42；
`tools/io_usb_host_burst_mock_log.py` 按相同常量生成合成启动/控制/事件文本。
未把历史日志或 JSON 重构为新实机回复。每份 collection 有明确 MOCK_ONLY 标记，
固定 simulation schema、journal_raw_mock_reply 和 supplied_synthetic_A23_log 来源。

保存并审计9份模拟 collection：ISO先完成、控制先完成、控制同步完成3份通过；
控制迟到、重复ISO、重复控制、控制错误、非零控制字节、短after回复6份不通过。
短回复仍保留167字节原文，错误/超时不重试；已有失败结果可以被归档但不能判成功。
上轮原始22个模拟场景重新分类结果完全一致，旧冻结目录未改。

新增18项回归覆盖缺失/重复分发、错序、错误元组、窗口内断开、完整身份/URB/时钟字段、
ISO7 bitmap/tag/context/terminal、report_count0/1/2、STATUS/core混用、重算哈希后篡改、
原生overall错误、来源重标记、写入失败以及缺失证据不能补造。
CLI 正常模型exit0、完整失败模型exit1、格式错误exit2；hardware/capture/repeat参数拒绝。

simulation_status_byte_binding_verified 和 simulation_device_log_byte_binding_verified 仅证明
这些模拟文件之间的字节关系。device_log_bound、hardware_trigger_binding_verified、
hardware_verified、usb_strict_pass、baseline_accepted、allow_next_burst、callback_drain_verified、
firmware_bytes_verified、bus_phase_verified 和跨时钟对齐标记全部false。
ISO7样本仍不是原子快照，也不提供线缆时刻；主机mach时钟与设备19.2MHz计数分别审计，不直接相减。

## 下一步及实机缺口

电脑上仍可实现和编译审查独立 SDK single-burst transport：固定身份/配置、真实缓冲区、
异步控制回调、原始STATUS观察来源以及生命周期连接。目前执行器仍只接 Mock，不能运行实机采集。
后续适配需要保留日志模式与来源边界，不能把 simulationOnly 标记改名就获得硬件入口。

真正需要 Switch 确认的仍是新 API burst传输、控制timeout粒度与调度预算、空槽原生错误分布、
设备事件关联和callback/DMA排空。旧32轮成功与本轮模拟不能替代这些证据。
当前stage=no_td_observation_complete_policy_pending、remaining=0，未产生新的凭据、部署包或拷卡动作。
