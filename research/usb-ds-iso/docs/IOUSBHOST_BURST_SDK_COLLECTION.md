# 单次 burst SDK collection 与设备关系（2026-10-13）

后续13:38阶段已完成[单次SDK入口与零次数准备](IOUSBHOST_BURST_ENTRY.md)，221项Python
检查通过、0跳过；本文以下保存13:11 collection阶段的结果和当时待办。

电脑实现已完成：独立 SDK collection 冻结器及主机 journal/core/checkpoint、原始 STATUS、
完整 A23 启动日志、ISO7 和三组控制分发关系审计。204 项 Python 检查通过、0 跳过，其中
20 项为新增 collection 检查；34 个原生 SDK 协调器注入场景通过 ASan/UBSan。
生产 SDK transport、协调器和证据保存代码本轮没有改变；只给测试 STATUS 增加合成 ISO7。
真实 SDK 设备对象、registry、USB、SD 访问均为 0，没有新实机样本或部署。

冻结目录：`private/analysis/A23-IOUSBHost-burst-sdk-collection-20261013-131129`。
构建及原生结果见 `build.log`、`native.log`、`native-fixtures/`；完整 Python 结果及环境见
`python-full.log`、`python-environment.json`。`collections/` 和 `collection-audits/` 保留每个
可冻结场景及独立结果，`collection-outcomes.json` 同时记录拒绝的场景。

## 独立格式和来源声明

`tools/analyze_io_usb_host_burst_sdk_collection.py` 只读取已提供的文件，提供 `freeze` 和
`audit`，不枚举设备、不打开 SDK lease、不采集或创建凭据。独立格式为
`A23-burst-sdk-collection-1` / `iousbhost-single-burst-1`，与模拟 collection、旧 no-TD
collection 分开检查。`execution_mode=hardware` 只表示 SDK 观察格式，不能认证文件来源。

冻结必须显式指定 `--origin`：

| origin | 保存和审计要求 |
| --- | --- |
| injected_sdk_fixture | 原样保存 MOCK_ONLY、fixture-calls 和 result；SDK、registry、USB、SD 调用计数严格为整数0，主机结果须与 checkpoint 一致 |
| supplied_sdk_artifacts_unverified | 已提供但未认证的 SDK 文件与设备日志；不允许直接把带 fixture 声明的目录重新标记，剥除声明也只得到未认证材料 |

两种来源都保持 host/device origin、hardware、capture、空槽政策、callback drain 和下一次
burst 放行标记为 false。合成 ISO7 使用协议字段生成，没有借用实机完成数据。

固定目录包含 `host/`、两份原始 STATUS、`device-log.txt`、`collection.json`、`ORIGIN.txt`、
`SHA256SUMS`、`COMMITTED`。host 保存完整 journal、原始 transfer core、final checkpoint，
存在 retained checkpoint 时必须原样保留。文件集合、长度、身份、hash、布尔/整数类型、
重复 JSON 键及 symlink 均检查；不覆盖已存在目录，fsync/读回后最后写 COMMITTED。
输入冻结期间发生变化或复制后的字节不符时不提交。

## 设备与主机关系

STATUS 必须逐字节等于 SDK journal 中两份原始控制回复；core/final/retained 与 journal 的
UUID、服务身份、描述符 hash、frame、固定 seq1 计划和原生时刻必须一致。
超时后恢复的 retained 记录必须仍存在，其失败数组是 final 的有序前缀，开始及退出时刻
不能被改写；迟到完成继续保留失败。只有已结束、关闭且有自己 core 和两份回复的目录可冻结。
可完整保存失败观察，完整性通过不会消除控制错误、超时或短回复等失败。

设备审计要求完整 A23 启动、HOS22.5.0 和指定 Build-ID、安装记录21、一次提交/终结及
seq/URB/时钟关系；ISO7 检查 terminal、bitmap、actual、context、首控制字、环地址和
两条 ED 事件标签。完成 report_count 为0或1候选，超过1保留歧义失败。
有效16槽须逐包匹配 payload、actual192、native0，overall 成功；944空槽须保持当前
保存观察所对应的 status0/actual0。此候选检查不接受实机空槽政策。

控制 trace 原样保留 STATUS → 41/54/1/2/0 → STATUS 三组分发，每组接口0/1与 ignore
相邻匹配。六条 vendor 记录的标签表示接口，不当作六次总线请求；重复、缺失、错 tuple、
断开或冲突流量拒绝。字节和日志的关系匹配不认证同一次启动/采集，也不证明总线时序。

## 验证结果与下一步

34 个注入场景中，18 个保存为 collection：5 条正常路径完整匹配，13 条保存失败结论。
5 条正常路径为 ISO先完成、控制先完成、inline控制完成、控制队列延迟、ISO队列延迟。
其余16个不完整场景在创建输出前拒绝。短 after STATUS 仍保留控制 trace；正确设备内容
不能覆盖原生 overall 错误或错误空槽。旧184项检查全部通过，既有格式继续拒绝新 collection。
前一阶段只有 header 的旧 SDK fixture 可保存，但缺少 ISO7，设备关系审计保持失败；旧冻结包
没有修改。CLI 正常审计返回0，完整失败材料返回1，缺少来源/capture/repeat 请求拒绝。

新增检查覆盖设备字段/启动记录/日志截断、控制广播、STATUS替换、重算hash后重标政策、
retained历史抹除、fixture调用计数与结果矛盾、冻结期间输入变化、复制/写盘故障和目录损坏。
4 项工作流路径检查及 diff 空白检查通过。源码、文档、凭据前后快照和历史包校验结果另存。

下一步仍可在电脑审查和准备单次 SDK burst 入口及凭据工作流；本轮不创建可用采集次数。
真实 SDK timeout 粒度、调度余量、有效包/空槽状态政策、同次采集来源、总线相位和 DMA/
callback 排空仍需实机证据。stage 保持 `no_td_observation_complete_policy_pending`、
remaining=0，baseline_accepted、allow_next_burst 和 burst_capture_entry_enabled 保持 false。
没有新 NSP/IPS，不需要拷文件或连接 Switch。
