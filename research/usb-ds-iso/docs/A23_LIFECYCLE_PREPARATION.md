# A23 生命周期候选部署包与一次执行入口（2026-10-16）

已完成[第 4 代接收器](A23_LIFECYCLE_RECEIVER.md)对应的离线部署包、一次记录预览/签发入口及执行流程。277 项相关回归通过，失败、错误、跳过均为 0；最后补充目标磁盘一致性检查后，18 项本轮测试再次通过。正式记录尚未创建，本轮没有读写 SD 卡、启动接收器采集或执行设备程序。

## 部署材料

直接将已封存的 737ad5… ELF 转换成 NSO，再与原 NPDM 打成 PFS0/exefs.nsp；未重新编译设备程序。逐段核对压缩/解压内容、三个程序段、BSS、build ID、段摘要和容器边界；NPDM 的程序 ID/权限范围、main 栈请求 8192、优先级 44、CPU 3 保持。控制器 22 处修改及 IPS 与旧包一致。

部署树为 `private/analysis/A23-lifecycle-deployment-review-20261016/sd-review/`，包含四个文件。相对最近回收的 quiet 版本，只有 `atmosphere/contents/00FF0000A53BB666/exefs.nsp` 变化；boot2.flag、toolbox.json 和 IPS 保持。`rollback-review/` 保存同一四文件的 quiet 版本，并绑定 10-16 02:23:43 只读回收及旧 quiet 部署包，不能直接替代以后对实际卡的再次核验。

| 材料 | SHA256 / 值 |
| --- | --- |
| 新 exefs.nsp | `bca717b0db12c0287c5859afc58235d19b83622a6e08a4fc679caf6aaef6d2a5`，116864 字节 |
| 新 main NSO | `d72d83c6b36738f6ca3bae1ac28306917bc13b5364fe08e8c11b9d8591e354e9` |
| 设备 ELF，保持 | `737ad5c1df026d7ea94ac898de0ff69ed4fef8c369f400d1dce72b377d58eb38` |
| runtime recipe，保持 | `39b10989773f3d216138de2ea3c8027ae1f42c6dbafbd84f454fb4cc9acfc549` |
| 接收器，保持 | `f4a23c2391279b872ceb84c89293ce43d8614dff2bd66c24a453e4dfac51aac6` |
| 主机设备绑定，保持 | `e73fa51d55efbbb15ccc83c4f20352a5d4cec5d12d424b7ec490f93e46e8d3ac` |
| quiet 回退 exefs.nsp | `81314284637a81fd5a6f9564383533b14168a62cababb51b9a6d156c643080f3` |
| 新部署包 SHA256SUMS，22 条 | `f1b8c4ca055963a5412fbf259d59de879766e56c3955085dcb9a55bb9f046ef5` |
| 最终准备审查 SHA256SUMS，10 条 | `33284726bcbb4155f34995aa58696b2eeaf557d32eff755eed06b73a2c038a9c` |

## 一次记录和执行约束

`tools/prepare_a23_lifecycle_once.py` 默认只预览，实际签发必须显式选择 `--issue`，并由调用者先取得本次实测授权。目标必须是 analysis 直属的新 `A23-lifecycle-once-*.json`，或临时模型目录中的同类新文件。排他创建；现有、部分、已消费或失败的记录均不覆盖、不补次。签发绑定新包、接收器、六材料、验证包、计划以及三个新工作流文件的摘要，材料变化则拒绝。

签发还须提供已封存的新部署回执目录。预期 schema 为 `A23-lifecycle-card-deployment-1`，核对目标 SD UUID、新包及绑定摘要、四文件读回清单、未签发/零次调用状态，以及对应目标磁盘已弹出且挂载消失的记录。弹出记录必须与部署记录的 whole_disk 一致；旧 quiet 部署回执不能通过。本轮没有这种真实的新部署回执，测试只使用临时目录中明确标注的注入模型。回执核对是保存内容的一致性，不是独立的物理来源认证。

`tools/workflows/capture_a23_lifecycle_receiver.py` 只接受新一代 prepared/remaining1 记录；离线零次记录、旧记录、变动部署回执、变动工作流和错误 scope 在创建锁、run 或进程前拒绝。取得锁后再次核对，先将该记录消费为 remaining0，再写第 4 代回执和启动命令。回执写失败或进程启动失败不退回次数。等待超时留下 unresolved_no_retry 与进程信息，不主动 kill、不封存仍可能变动的输出、不允许重试。进程退出 0 但没有可核对的主机证据仍判失败。

接收器及设备 ELF 保持上一轮身份；新入口复用已封存的第 4 代主机验证包。原生接收器仍核对其自身 202 项来源，新准备审查则在其上增加 5 项工作流/测试来源，共 207 项。三个新入口文件的变动会使已签发记录失效；这不构成源码或硬件来源的外部认证。

## 文件服务与栈复核

对同一 ELF 的 17 组函数重新核对实际机器码、调用边及持栈，并保存 FILE_LOGGING 等实际编译定义。`__appInit` 调用 CoreInit，CoreInit 尝试 fsInitialize；main 随后才准备 LCP1 文件和初始化 USB。CoreInit 可能在 fsInitialize 失败后继续，并在 LCP1 准备之前已经尝试 CaptureInitialize。因此“准备失败不启动 USB”不表示之前没有初始化其他资源。

LCP1 只管理自己的额外文件系统对象：每次写后关闭文件再 commit，结束时关闭该对象，不调用共享 fsExit；共享服务仍由原 CoreExit 管理。记录器自身失败、文件服务阻塞及文件系统 commit 的实际语义尚未在 Switch 上验证。准备失败可能只留下零文件/部分头或日志，也可能完全没有 LCP1；没有枚举不能单凭主机结果定位原因。

main、Prepare、Note、Context、Finish 等函数的持栈与上一轮 ELF 一致；Prepare/Context/note 变体仍存在未闭合的间接调用。main 请求 8192 不等于实际内核预算，函数帧也不是整条调用链上界。无实际服务执行、耗时上界或设备栈峰值证明。main return 标记同样不认证原 `__appExit` 完成或进程已经退出。

## 验证、现场顺序与下一步

18 项本轮测试覆盖真实打包工具及容器检查、quiet 回退身份、默认预览、拒绝旧部署回执、临时模型签发、不覆盖/补次、材料变化、目标磁盘/读回/弹出错配、消费后写回执失败、启动失败、等待超时及缺失主机证据。所有进程启动分支均替换为测试对象，没有调用真实采集入口。277 项回归及后续 18 项复核日志均保留。

准备最终审查位于 `private/analysis/A23-lifecycle-preparation-final-20261016`，验证包位于 `private/analysis/A23-lifecycle-preparation-validation-20261016`。旧 202 项来源、七生产文件、三票据、三离线记录及已消费现场记录保持；旧封存与本轮新包分别核验。卡上最后确认的仍为旧 quiet，当前现场记录仍 `failed_no_retry / remaining=0`，ISO actual 全 0 的失败和原根因未知结论保持。

后续现场顺序为：系统菜单完全关机并确认断电 → 插卡核验/回收原件及备份 → 部署新包、四文件读回、安全弹出并封存回执 → 获得本次实测授权后签发新一次记录 → 主机 WAITING → 装卡并按现有方法启动 CFW → 仅该一次等待/请求链 → 按保留状态处理后，通过系统菜单完全关机、确认断电再只读回收。不能用接收器退出码、固定倒数或 LCP1 最后有效槽宣称设备保存完成，也不能在 unresolved 时自动重连或强制结束进程。

下一项先把新包的部署与原件回收步骤落实为可离线演练的文件操作工具，覆盖错卡/旧基线、备份、仅替换 NSP、读回失败、部分写入及回执生成；随后再进入需要现场配合的实际部署。当前只有电脑端准备，不签发、不取卡、不启动新测试。
