# 研究目录存储与恢复

当前代码和文档继续在 `host/`、`device/`、`patches/`、`tools/`、`tests/`、`docs/` 中维护。
`private/runs`、`private/collections` 和 `private/card-cycles` 保存实测及读卡原件；
`private/analysis` 保存展开的离线结果；`private/storage` 保存可恢复的历史离线归档。
私有数据仍由现有 `.gitignore` 排除，Git 提交不包含设备固件或本地证据。

## 使用方式

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
读取已归档结果的旧 Markdown 链接或历史审计脚本，需要先恢复相应目录。
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
