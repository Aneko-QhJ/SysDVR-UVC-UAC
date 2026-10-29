# 测试分层

| 目标 | 命令 | 规模 | 当前状态 |
| --- | --- | --- | --- |
| 快速 | `make check` | 10 个文件 | 绿，约 2 秒；每轮门禁 |
| 单文件隔离 | `make check-file` | 183 个文件 | 用于定位崩溃/导入错误，较慢 |
| 全量 | `make check-all` | 183 个文件 / 1074+ tests | 约 8 分钟；**当前不是绿的** |

## 2026-10-27 全量基线

- Python 3.13.16，`Ran 1074 tests in 499.135s`，`errors=95`，`skipped=22`。
- 已知类别：
  - 缺少可选依赖 `unicorn`（如 `test_publication_audit.py`）。
  - 私有 fixture 过期或字段缺失（如 `KeyError: 'revision'`）。
  - 历史模块要求 Python 3.10+；系统 `python3` 3.9 会额外失败。
- 因此 `check-all` 目前是**历史审计**，不是每轮门禁。修复前，非零结果不能直接当作
  当前改动的回归。
- 全量失败时，runner 会把完整输出写到 `/tmp/dsh-research-tests-<pid>.log`。

## 修复顺序（下一步）

1. 可选依赖：测试文件在 import 失败时 `skipTest`，而不是 error。
2. 私有 fixture：缺目录/缺字段时显式 skip，并给出恢复命令（见 [../STORAGE.md](../STORAGE.md)）。
3. Python 版本：统一用 3.13；Makefile 已优先选择 `python3.13`/`python3.12`。
4. 清零后，把 `check-all` 升级为门禁；在此之前只用 `make check` 和按主题 `--filter`。

## Unicorn mailbox replay

`test_mailbox_multiplex.py`（3 个 in-flight URB 的 mailbox 重放）需要 Unicorn 2.1.4
和 A23 burst 包：

```sh
cd tests
ISO_PATCH_PACKAGES=/tmp/a23-burst /tmp/dsh-unicorn/bin/python   -m unittest test_mailbox_multiplex -v
```

它不在 quick 套件；没有 unicorn/包时 skip。当前默认 `python3.13` 没有 unicorn，
全量里会 skip（不再 error）。

## 规则

- 当前改动至少要过 `make check`。
- 触碰历史工具时跑相关子集，例如
  `python3 tests/run_all.py --filter a23_ep0`；不默认全量。
- 新增测试放 `tests/test_*.py`，并与被测工具同名，便于 `--filter`。

- `test_urb_accounting.py` — URB 表/5 页 IOVA 记账模型；不访问硬件。

- `test_a23_urb_trace_decode.py` — 解码 A23 trace report：v3 的
  endpoint/producer/consumer/count，v4 的 consumer/最后 URB IOVA/size
  与 `unmap_gate` 判定，以及 v5 的 8 组条目统计。
