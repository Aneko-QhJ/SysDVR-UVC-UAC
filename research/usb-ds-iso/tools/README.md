# 工具索引与约定

`tools/` 有 400+ 个一次性/专题脚本。不要求全部读完；先看
[INDEX.md](INDEX.md)（自动生成）和 [../WORKFLOW.md](../WORKFLOW.md)。

## 当前使用

| 工具 | 用途 |
| --- | --- |
| [build_a23_short24_path_span_candidate.py](build_a23_short24_path_span_candidate.py) | 从路径修正版父树生成短包候选 |
| [audit_a23_short24_path_span.py](audit_a23_short24_path_span.py) | 路径修正版候选的离线审计 |
| [build_a23_short24_candidate.py](build_a23_short24_candidate.py) | 短包候选（旧路径版本，已实测失败） |
| [audit_a23_short24_entry.py](audit_a23_short24_entry.py) | 驻留入口的授权/写盘审计 |
| [build_a23_short24_entry.py](build_a23_short24_entry.py) | 生成一次性主机入口 |
| [package_a23_short24.py](package_a23_short24.py) | NSP/IPS 打包 |
| [analyze_a23_short24_session.py](analyze_a23_short24_session.py) | 短包会话/原生记录分析 |
| [audit_a23_short24_sdk.py](audit_a23_short24_sdk.py) | SDK 组件与设备关系检查 |
| [analyze_a23_audio_cadence.py](analyze_a23_audio_cadence.py) | PCM 速率/调度算术 |

## 分类

| 前缀 | 用途 |
| --- | --- |
| `build_*` | 生成候选、ELF、入口、包 |
| `audit_*` | 静态/离线验收、来源核对 |
| `analyze_*` | 日志、证据、时序分析 |
| `collect_*` | 主机采集 |
| `prepare_*` | 一次性准备/签发 |
| `package_*` | 打包与部署材料 |
| `model_*` | 模型/模拟 |
| `a23_*`、`io_usb_host_*` | 专题辅助 |

## 约定

- 完整测试建议 Python 3.10+（`make` 优先用 `python3.13`/`python3.12`）；系统 3.9 可跑
  `make check` 的快速集，但历史模块可能因语法版本失败。
- 新工具放本目录，带 `--help` 和至少一个 `tests/test_*.py`。
- 同类逻辑优先复用已有函数；不要复制 manifest/hash/verify。
- 一次性脚本用完移到 `tools/archive/`；迁移前先跑 `make -C research/usb-ds-iso links`。
- 不要手改 [INDEX.md](INDEX.md)；用 `python3 tools/index_tools.py` 重生成。
- 工具不应写 `private/` 之外的绝对路径；输出目录由参数传入。
