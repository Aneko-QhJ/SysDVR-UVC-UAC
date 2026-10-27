# 固定 16TD×24 字节短包候选（2026-10-27）

后续[SDK组件与设备关系核验](A23_SHORT24_SDK_AND_RELATION.md)已完成：21个原生注入场景
及7项关系检查通过。下文的SDK“下一项”保留本阶段历史顺序，仍无真实SDK采集或部署。

[上一轮速率分析](A23_AUDIO_CADENCE_GAP.md)选定的最小短包候选已完成离线实现：
独立控制器、完整设备 ELF、设备协议头及文件消费者已建立。最终15项针对性检查通过，
包括实际 ARM 控制器指令执行和完整 ELF 内的新控制器/recipe 绑定。

这回答了“固定16个TD的producer能否在CPU执行中处理24字节载荷”，尚未回答真实USB
是否收到16个短包。没有新 SDK 接收器、NSP 部署包或实机许可，没有 USB/SD 操作。

## 候选范围与输入隔离

| 项目 | 本候选 |
| --- | --- |
| 提交形状 | 固定16个TD，每TD24字节，总384字节 |
| 保持条件 | HS、endpoint0x83、MPS256、bInterval1、首TD显式lead32、后15TD用SIA |
| 主机文件形状 | 固定128个transaction，每项请求24字节；raw3072字节、transaction表3584字节 |
| 新诊断标记 | `IS24`，整数0x34325349；诊断结构仍112字节、STATUS仍168字节 |
| 测试载荷 | 前四字节`IS24`、16位序号和确定性body；仍是测试图样，不是PCM |
| 存储 | 独立一次性候选目录；设备g_isoBuffer仍4096字节，没有增加TD数或实现复用 |

24字节对应目标48kHz/双声道/16bit的6个样本帧，名义每125µs一次时速率匹配。
本候选的16个服务槽仅覆盖名义2ms；没有把它作为持续音频、标准UAC或校准总线时钟。
MPS256是端点上限，24是本次载荷长度，两者不混写。SS路径在producer检查中拒绝，
本轮不提供SS能力结论。

基线控制器为`private/packages-A23-interval1/A`。设备来源为已封存的
`private/analysis/A23-lifecycle-device-review-20261016/candidate`，先验证整个父目录的
manifest与COMMITTED，再复制source到新目录。新runtime payload和recipe只写候选副本。

构建工具只重放父记录中的ARM编译/链接命令，并将全部输入/输出路径映射到候选目录；
不继承读卡、部署、签发器、采集工作流或旧native场景。新增文件不改写旧生产源码、
冻结包或票据。完整设备构建仍沿用30秒窗口及既有所有权/停止保护。

## 控制器与完整设备的实际变化

控制器仍为680字节，RX cave共684字节；符号地址及除cave外的旧hook编辑逐项相同。
与旧A23恰好有8条指令不同：

| 地址 | 变化 |
| --- | --- |
| 0x68d58 | 入口总长3072→384 |
| 0x68dac | ISO7→IS24诊断标记高16位 |
| 0x68dfc | TD载荷长度192→24 |
| 0x68e20 | DMA数据地址步进192→24 |
| 0x68e2c | 剩余长度递减192→24 |
| 0x68f24 | 单ED完成长度校验192→24 |
| 0x68f48 | 完成累计步进192→24 |
| 0x68f6c | 完整终态累计3072→384 |

TD数、TRB步进、环链接、16位完成bitmap、首cycle发布和错误retained路径均未改写。
新旧producer互相拒绝对方总长度；不能将旧192字节样本截短后作为短包通过。

完整设备 ELF 由14个C对象及一次链接产生。独立ELF检查确认：机器类型为AArch64，
`isoRuntime_0_after`的680字节与新控制器逐字节相同，两个`ep0CandidateRecipe`常量
均为新recipe，`g_isoBuffer`大小仍4096。没有执行这个设备ELF或生成可部署NSP。

## 针对性离线结果

最终审计采用Unicorn2.1.4执行实际补丁指令；C fixture直接包含生成后的设备协议头，
生成384字节测试载荷，再由独立Python消费者核对。ASan/UBSan用于该本机C fixture。

检查覆盖：

- 环起点0/230/246以及帧号回绕附近的TD地址、24字节步进、lead32和后续SIA。
- 首cycle在构造期间不发布，context只读快照先于最终发布，仍只有原doorbell写入。
- 16个唯一ED完成才调用原complete入口，累计384字节；重复ED不重复累计，终态后事件不改变结果。
- 缺失第16个ED保持360字节/bitmap0x7fff且不交还dequeue；再次提交拒绝。
- ED长度23/25/192或错误CC进入retained；后续正确事件不能将其改判成功或授予重投。
- 错误总长、MPS、interval、速度及不匹配事件拒绝或过滤；原report复制保留新诊断。
- 消费者检查所有空槽原生状态与overall；错误包数、body、序号回绕、旧ISO7标记、旧尺寸
  和旧3072字节终态均拒绝。独立文件CLI也通过同一正向模型材料检查。

主机transaction与STATUS外壳是**合成模型输入**，嵌入的诊断来自ARM执行，载荷来自C协议头。
这些不是真实IOUSBHost回调、usb:ds报告或设备trace。消费者明确保持hardware_verified、
device_log_relation_verified、control_path_verified、callback_drain_verified、
buffer_reuse_verified和continuous_audio_verified为false，不输出严格USB通过结论。

## 复现、产物与开发中停止

- 构建工具：[build_a23_short24_candidate.py](../tools/build_a23_short24_candidate.py)。
- 文件消费者：[analyze_a23_short24.py](../tools/analyze_a23_short24.py)。
- 审计工具：[audit_a23_short24_candidate.py](../tools/audit_a23_short24_candidate.py)。
- 最终build：`private/analysis/A23-short24-candidate-20261027-r2`。
- 最终audit：`private/analysis/A23-short24-audit-20261027-r4`，15项检查通过。

构建只需现有devkitA64及Python；审计额外需要Unicorn2.1.4。此次将依赖装入临时目录，
没有修改系统Python；该目录可能在后续清理中消失。Unicorn在默认沙箱内连mem_map都触发
Illegal instruction，尚未执行候选；沙箱外最小NOP通过后，最终审计在同一沙箱外上下文运行。

```sh
python3 research/usb-ds-iso/tools/build_a23_short24_candidate.py \
  --output /private/tmp/a23-short24-build

PYTHONPATH=/private/tmp/a23-short24-python /opt/homebrew/bin/python3.13 \
  research/usb-ds-iso/tools/audit_a23_short24_candidate.py \
  --build /private/tmp/a23-short24-build --output /private/tmp/a23-short24-audit
```

输出目录须不存在。临时依赖及沙箱条件按上文准备；不能把沙箱内SIGILL归因于producer。
r1构建已完成链接，但工具误要求13个对象而停止；核对封存父记录实际为14后修正r2。
audit r1因沙箱限制停止，r2的14项通过；新增ELF绑定检查时r3因readelf大对象大小显示为
十六进制而停止，修正读取后r4的15项通过。各输出保留，不改原件或用模型补真实记录。

## 下一项软件准备与实机边界

下一项离线接入**单次短包SDK主机入口和设备证据消费者**，保持一次调用/一个burst：

1. owner/lease/driver固定128×24字节存储，提交及回调长度一致；MPS256/interval1保持，
   六个字节的图样标签不作为PCM样本解释。
2. 控制请求、STATUS、原生包状态、真实device execution/trace与新IS24/recipe绑定；
   本轮文件消费者只覆盖其中载荷和STATUS子集，不能代替完整关系核验。
3. 新设备ELF需要独立打包审查和部署；现有卡上仍为旧192字节设备，不能直接启动新host。
   当前138件基线、旧actual465与所有已耗尽范围保持，未分配新范围或写卡。
4. 完成相应native无设备fixture和失败收尾准备后，才提出一次有界硬件问题与具体操作。
   控制/ISO期限不冒充硬中断；未交还存储不释放、不复用；失败不自行增加重试。

继续工作按[当前规则](RESEARCH_RULES.md)选择最小必要接线；不要求先补齐通用全局租约，
也不在本候选中直接增加128个TD、长期滚动或标准UAC生命周期。
