# 路径缓冲候选接收器、判读与部署包（2026-10-16，Asia/Shanghai）

已为[完整路径缓冲候选](A23_PATH_SPAN_DEVICE_CANDIDATE.md)构建独立的第 5 代接收器和原件收集工具，并完成对应 NSP 包转换及核验。正式设备 ELF、recipe、NPDM、配置保持上一轮身份。本轮没有访问 SD、签发一次记录、启动接收器采集或发起 USB 请求。

## 新绑定及原件判读

新绑定 schema 为 `A23-path-span-host-device-binding-1`，配置 `path-span-window-30s`。接收器 build/record/description 与 consumed receipt 均使用独立第 5 代标识，绑定同一六份设备材料，包括 NPDM、配置、ELF 中两处 recipe 常量。Python 与本地程序检查器均拒绝旧版回执、旧候选、变动源码或设备材料；文件检查发生在设备访问和实际 claim 之前。

新收集器保留 EXE3/主结果缺失、部分文件、坏 CRC、损坏尾部、多个 LCP1、不匹配 nonce/context/writer/clock 等原件，不自动选择多个候选。模拟匹配链可判内容自洽与完整；这不认证物理来源、LCP1 自身提交、join 返回或实际最后执行点。已冻结的新集合可移动并独立重核，不依赖原 live 源路径。真实旧生命周期集合在新入口被拒绝，旧集合本身保持完整。

31 个收集场景、12 个等待/交接模型通过。模型中的 consumed 记录和 claim 仅由注入式测试程序生成，没有调用真实签发入口或 `--acquire-once`。正式新记录仍不存在；新离线 record 为 `offline_build_ready / remaining=0 / acquisition_enabled=false`。

本次来源 226 项，含旧 219 项原样和 7 项新变体。来源条目上限调整为 256，当前接收器构建清单 243 条，仍受数量、大小、路径和精确摘要核验约束。不是放开来源或接受任意材料。

| 身份 | SHA256 |
| --- | --- |
| recipe | `37269528ee3baa2941e1cb9268ccd4702d9db5b0fec87e913d3111c99b6e894f` |
| 设备 ELF | `9fe1e51e0d3cd5cc557055ec85225b48967cae31f465dd1bf5bb2a5c8d1efa8b` |
| 接收器 | `afd6e0f04c7971d396511ce72d8ae96171b313a1a3d38f4276890287662b2438` |
| 接收器构建 manifest | `5221a15fc7a7a1ab07eabb7919af3d329ea7a4143defdb69f3490b987df291cb` |
| 设备绑定 | `a10e3750ed104576c05b205145e8a8efefe8811d20dec0d1e1debc8c368c61cf` |

接收器审查：`private/analysis/A23-path-span-receiver-review-20261016`，1564 条封存，manifest `b79ed9ec51cbf5aac371cdf4ef6f89decdf1655b5405dd9ca443d8604fd327ce`。其中 `receiver-build` 243 条，`offline-record.json` 为零次数，`collections`、`mock-runs`、`native-fixtures` 均是离线模型。

## 新包及备份基线

ELF 转换 NSO、NPDM 程序身份/线程请求、三段内容/BSS/hash/build ID、PFS0 仅含 main/main.npdm、原控制器 IPS 均核验通过。新 NSP **117024 字节**，SHA256 **`b54747adb8e824bb0a08709868335a06c1aca53c6b1e4e8ce6a1d2e761b8deb8`**；NSO 为 `1bdfb9bc56ea8b942b86453b8ab68d998ed01207ed3266db28b18bc4f2dea851`。

`sd-review/` 为四文件新部署树，`rollback-review/` 为最近实际部署的生命周期版本：NSP `bca717…` / 116864 字节，其余 flag、toolbox 与 IPS 保持。基线通过 `private/card-cycles/20261016-143132-lifecycle-first-live-read` 的只读快照四文件清单核验；没有把更早的 quiet 包当作当前卡上基线。新包只需要更换 NSP 数据。

部署包：`private/analysis/A23-path-span-deployment-review-20261016`，22 条封存，manifest `5ff6a33f1649e09fbf7dbc6a59c5b9b096f8e86c553970dba87c2a7a85bf900f`。该封存代表电脑上的打包核验，不是新包已写入卡或在设备运行的回执。

22 项新变体专项、路径候选/原型与旧生命周期回归共 **79 项通过，0 失败、错误或跳过**。除上述模型外，测试核对新旧 schema 拒绝、被重新封存的变动材料仍拒绝、包转换、旧包不能绑定新接收器、三文件保持及最近回收基线。相关材料和最终保护检查：`private/analysis/A23-path-span-materials-validation-20261016`。

## 后续入口

下一步建立绑定第 5 代接收器、新包、验证材料及最近卡基线的独立部署和一次诊断入口，并演练失败不重试、回执检查和安全弹出。现有 `prepare_a23_lifecycle_once.py`、卡工具和工作流仍针对旧生命周期材料；不能直接拿它们写本次新包或签发第 5 代记录。

卡上最近确认仍是 `bca717…`，latest 部署指针保持该实际版本。两份已消费现场记录仍 failed_no_retry / remaining=0，旧票据/离线记录不改。新包尚未部署，路径修正是否消除 `0xD401`、实际映射/栈预算和 ISO 全零根因仍需后续证据。
