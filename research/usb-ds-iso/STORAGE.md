# 研究目录一次性精简与留存

当前代码和文档继续在 `host/`、`device/`、`patches/`、`tools/`、`tests/`、`docs/` 中维护。
`private/runs`、`private/collections` 和 `private/card-cycles` 保存实测及读卡原件；
`private/analysis` 保存当前研究输入及实机辅助记录；`private/storage` 保存仍需留存的
证据压缩包和整理收据。已淘汰的离线结果没有恢复副本。
私有数据仍由现有 `.gitignore` 排除，Git 提交不包含设备固件或本地证据。

## 本次精简范围（2026-10-29）

按用户明确要求，工作区按后续研究需要精简，不保证恢复到任意旧实验版本。
以下策略取代旧盘点报告中“全部历史离线 ZIP 必须保留”的建议。

- 本次以整个仓库（含 `.git`、隐藏目录、`private/`）约 **1 GiB** 为整理目标，
  已完成一次性精简；后续研究不设容量上限或容量检查。
- 保留源码、工具、文档、测试、Git 历史和未提交修改；实机原始证据、当前票据、
  已消耗次数及序号记录保持原字节。
- 保留 10-27 至 10-29 的结果、short24 所需旧父树、固件、Ghidra 工程与依赖。
  已从归档恢复 Q1 时序参考输入，当前工具可直接读取。
- 旧 `analysis` 中的启动、电源、读卡、实机观察和收尾材料也保留；47 个相关证据
  ZIP 继续留存。过时的离线审计、重复测试/构建和恢复包按明确清单退役。
- `.git/experiment-artifacts` 中的唯一实机记录、原始模块、参考资料及提取工具原位保留。
  该目录已不是完整恢复包，旧默认 `restore --scope capture` 流程不再可用。

处置清单、保留文件哈希、逐批删除收据与离线验证日志均在
[private/storage/trim-20261029](private/storage/trim-20261029/)。其中 `disposition.json`
明确每个目录/归档的保留或删除原因，`preserved-files.json` 记录保留原件的哈希；
`retired.jsonl` 记录已实际删除的条目。旧文档的历史路径按该清单判断是否仍存在，
不得把已删除输入描述为“恢复后可运行”。

本轮结果：约 **4.15 GiB / 16.9 万文件 → 896 MiB / 1.93 万文件**，释放约 **3.28 GiB**。
删除 270 个历史离线目录、426 个过时 ZIP 和 74 个 Git 内构建/恢复副本；
16,678 个保留文件/链接哈希及属性未变，Git HEAD/引用未变。原盘点的另 1 项
`private/.DS_Store` 是未封存的 Finder 元数据，最终核验发现其被系统改写；该差异
单独记录，不计作原字节通过，也不改写原保留清单。
`retired-dependencies.json` 列出 181 个直接引用退役输入的历史工具/测试文件；这是静态
路径扫描，不表示这些旧流程已通过。当前工具未检出此类缺失输入，并已实际构建和运行
设备/主机、trace、short24 和 Q1 离线验证，结果见 `validation-after.json`。

额外修复：Q1 分析器原先依赖已删除的注释，现改为核对对应运行条件，未改变实测结论；
Git refs 中一份旧 Finder 元数据已按哈希另存收据，移出 refs 后 Git 连通性检查通过。

`make -C research/usb-ds-iso check` 继续只运行快速测试。
新实验常规通过用例使用临时目录并在结束时清理，长期保留必要输入、结果摘要及关键反例；
总报告引用明细，避免重复复制源码、构建和全部历史。硬件证据不自动轮换或清除。

## 仍保留的无损归档如何使用

独立工具 [research_storage.py](tools/research_storage.py) 仅使用 Python 3.9+ 标准库，
不导入冻结实验工作流、不操作 USB/SD、不修改票据或签发实验许可。
以下命令从仓库根目录执行；也可以使用脚本绝对路径。

```sh
# 打包一个明确选定的、已停止使用的 analysis 直接子目录。原目录仍保留。
python3 research/usb-ds-iso/tools/research_storage.py pack NAME

# 核验归档内容。
python3 research/usb-ds-iso/tools/research_storage.py verify NAME

# 在临时目录完整恢复并逐文件核验，再移除未变化的展开原目录。
python3 research/usb-ds-iso/tools/research_storage.py prune NAME

# 恢复到原 analysis/NAME；目标已存在时拒绝覆盖。
python3 research/usb-ds-iso/tools/research_storage.py restore NAME

# 或恢复到一个尚不存在的独立目录，便于查阅旧结果。
python3 research/usb-ds-iso/tools/research_storage.py restore NAME --destination /private/tmp/old-review
```

`NAME` 是单个目录名称，不接受通配符或跨目录路径。工具不自动判断研究依赖：
选择归档对象前检查源码、当前票据及归档引用；之后复核当前来源束和冻结构建。
只有对应 ZIP 仍存在时才可恢复；已按退役清单删除的输入不再支持恢复或旧流程重放。
当前正在使用的构建、设备包、来源文件、许可账本和实测原件保持展开。

## 归档保证与限制

- ZIP 内的清单记录每个原始路径、SHA256、长度、权限和文件修改时间，以及空目录。
  相同内容按 SHA256 只保存一次，恢复时创建独立普通文件，不使用软链接或硬链接。
- 打包前核验已有 `SHA256SUMS` 和适用的 `COMMITTED`；不重写原清单或报告。
  归档完成后回读压缩内容，并确认源目录未变化。
- 清理前完整演练恢复；归档损坏、恢复失败、源文件变化或新增文件均会拒绝目录清理。
  原目录先改名，再次核对后才移除；归档保留。
- 归档应在目录没有写入者或正在使用它的进程时执行。工具锁只排斥自身的并发操作，
  不防御外部进程持续改写目录。未保存文件系统扩展属性、ACL 或 inode 身份；
  不用于依赖这些属性的活跃资源，也不把恢复目录视为新的实测或授权。
- 归档与原件在同一磁盘，不代替异盘备份。中断留下的 `.partial`、`.pruning` 或 `.lock`
  应先检查再处理，工具不会自动重试、覆盖归档或移除旧锁。

## Finder 元数据

macOS Finder 生成的 `.DS_Store` 可能使“文件清单必须完全相同”的旧校验器拒绝目录。
工具可备份并移除未被任何祖先 `SHA256SUMS` 收录的文件；已收录的历史文件保留。

```sh
python3 research/usb-ds-iso/tools/research_storage.py pack-finder finder-backup-NAME
python3 research/usb-ds-iso/tools/research_storage.py prune finder-backup-NAME
python3 research/usb-ds-iso/tools/research_storage.py restore finder-backup-NAME --destination /private/tmp/finder-recovery
```

元数据恢复必须指定独立目录，避免把无关文件重新混入当前证据。
这项清理不修改封存文件、校验清单或验收结论。

## 2026-10-27 整理范围

以下为当时的操作记录；其中纯离线 ZIP 已按 2026-10-29 退役清单处理，
不是当前仍可恢复的目录清单。

本次归档的离线结果如下，原始内容均保留在同名 ZIP 中：

- `A23-sequence-workflow-review-20261017-r2`
- `A23-sequence-workflow-review-20261017-r3`
- `A23-sequence-workflow-review-20261017-r4`
- `A23-sequence-workflow-review-20261017-r5`
- `A23-format-loop-review-20261015`
- `A23-integrated-memory-review-20261015`
- `A23-literal-scan-review-20261015`

前四项未发现外部文字引用，保留仍被准备脚本使用的 r6。
后三项是历史离线报告：重跑 `audit_a23_memory_log_guard.py` 或
`audit_a23_integrated_memory.py` 前需先恢复 `A23-format-loop-review-20261015`。
仍作为格式审计输入的 `A23-literal-scan-review-20261015-final` 保持展开。
没有改写这些旧报告的 JSON 格式，以免破坏已封存哈希。

Finder 备份为 `private/storage/finder-metadata-20261027.zip`：移除 511 个未收录文件，
保留 39 个已收录文件。清理前序号历史校验因两个额外 `.DS_Store` 拒绝；清理后恢复通过。
本地操作收据位于 `private/storage/compaction-20261027.json` 和
`private/storage/compaction-reports-20261027.json`。

七个目录的 5751 个原文件共 1,219,255,608 字节，归档合计 33,912,363 字节
（约 32.3 MiB），减少约 1.10 GiB 逻辑数据。工作区 `du -sk` 从整理前的
8,729,720 KiB 降到 7,554,204 KiB，约释放 1.12 GiB；实际分配统计与文件长度不同。

验证：13 项工具测试通过；每个归档均完成真实恢复及逐文件校验。
679 项研究来源和当前票据字节不变，672 项 Q1 来源检查通过，Q1 r4 的 1023 项
构建清单验证通过，最新读卡快照和 Q2c 交接封存验证通过。
当前构建验证使用 Python 3.13（历史模块需要 Python 3.10+），存储工具也在系统
Python 3.9.6 上通过测试。本轮未重新编译接收器或运行任何硬件实验。
验证摘要保存在 `private/storage/current-validation-20261027.json`。

后续新增审计应在总报告中引用明细文件及摘要，避免重复嵌入完整明细；
常规通过场景优先使用临时目录，长期保存复现输入、结果及必要反例。
封存后的历史格式不就地迁移。

## 2026-10-29 /private/tmp 收拢

项目研究曾把构建、依赖和证据副本留在 `/private/tmp`。2026-10-29 按以下规则收拢：

- 唯一产物、依赖和输入共 28 项复制到
  [private/tmp-import-20261029](private/tmp-import-20261029/)，逐文件 SHA256 校验后删除源；
- 26 个构建目录的 `exefs.nsp` 与 `private/` 内归档同哈希，核对后删除 `/tmp` 副本；
- 19 个空测试目录和 2 个重复/可重建文件直接删除。

导入目录约 123 MiB，含 `MANIFEST.json`（逐文件哈希）和 `DELETED.json`。后续临时产物
应放在 `private/` 下的明确目录，不再长期堆在 `/private/tmp`。该导入不是新实测证据，
不改变票据、授权或结论。

## 2026-10-29 analysis 压缩

以下记录的是本次精简前的两批无损压缩；最终留存以本页顶部策略及退役清单为准。

对 `private/analysis` 做了体积审计和整目录归档。审计前 6.6 GiB / 800 个目录；
可读文件 5.65 GiB 中只有 1.10 GiB 唯一内容，80.6% 是跨目录重复字节。

- 第一批按“当前文档零引用、旧 `-rN` 轮次、被新轮次取代、排除 10-28 之后近期证据”
  筛出 197 个，完成 188 个；第二批按 `refs<=1` 的旧目录筛出 285 个，完成 277 个。
- 两批合计：原始 2.99 GiB，归档后 355.8 MiB，465 个归档全部重新校验 0 错误；
  源目录均在 restore rehearsal 通过后移除。
- 17 个保留展开：15 个内部 negative/tamper 用例带故意不一致的嵌套 seal，1 个含
  symlink，1 个没有顶层 seal；工具拒绝打包是正确的。
- `private/analysis` 降到 3.0 GiB，`private/storage` 增到 390 MiB（473 个 ZIP），
  按文件字节净减少约 2.64 GiB（`du` 约 3.2 GiB）。

收据与逐项日志在 `private/storage/compaction-20261029-analysis.json`、
`compaction-20261029-analysis-tier2.json` 及同名 `.jsonl`；审计与候选明细在
[private/tmp-import-20261029/analysis-size-report.md](private/tmp-import-20261029/analysis-size-report.md)。
嵌套 seal 是 negative/tamper fixture 的一部分，不应直接删除或改写；如需归档这 15 个
目录，应先设计显式的“仅校验顶层 seal”模式，而不是绕过校验。
