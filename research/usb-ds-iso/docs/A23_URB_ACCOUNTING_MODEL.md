# A23 URB/IOVA 记账模型（2026-10-29）

## 目的

serial640 在 host 收到 5 个 URB（80 包）后仍走 busy-map leak 崩溃。这个模型只回答
三个问题：

1. 5 是 8 项 URB 表的边界，还是 DMA/IOVA 资源的边界？
2. host 已经收到 5 个完成，说明 `complete_original` 被调用了；那 unmap 为什么没
   释放？
3. 哪种最小修正能让第 6 个 URB 通过？

模型在 [tests/test_urb_accounting.py](../tests/test_urb_accounting.py)，纯 Python，
不访问 USB/SD/硬件。

## 模型

- endpoint：`+0` producer、`+4` consumer、`+8` count、8 个 URB 条目；
- 每次 submit 按 `FUN_0002c520` 的顺序：**先** map 一个 4 KiB IOVA，**再**检查 8 项表；
- 每次 complete 按 `FUN_0002c690` 的顺序：取 consumer 条目，unmap `[URB+0x10]`，
  `+4=(+4+1)&7`，count--；
- IOVA 域默认 5 页；busy 分支保留已 map 的页（泄漏）；
- serial one-in-flight：一个 submit 后一个 complete，host 报告驱动下一轮。

## 结果

| 场景 | 第 6 次 submit | host 完成数 | 结论 |
| --- | --- | ---: | --- |
| unmap 正常 | 成功 | 6 | 5 页可以复用，不会卡在 5 |
| unmap 缺失 | map 失败 | 5 | 精确复现观察到的 5 |
| unmap 地址错误 | map 失败 | 5 | 同样精确复现 |
| 8 页/unmap 缺失 | 成功 | 6 | **8 项 URB 表解释不了 5** |
| 表满后继续 submit | busy | — | 每次泄漏一页，和 busy-map leak 一致 |

因此：

- **5 更符合 5 页 IOVA 域，而不是 8 项 URB 表**；
- host 已经收到 5 个完成，说明 A23 的 `complete_original` 至少被调用了 5 次；
- 真正的问题在 **unmap 没有释放**：可能是 consumer 指向了错误 URB 条目、
  `[URB+0x10]`/`[URB+0x20]` 不是 map 时的值、domain 指针不对，或
  `FUN_00004c70` 返回失败；
- 8 项表满后的 busy-map 泄漏是**另一个**防御性问题，不是 5 的主因。

## 限制

- “5 页”是从观察到的 5 反推的假设；endpoint 的 IOVA 域实际大小还需要 trace 确认。
- 模型没有覆盖 `FUN_00004c70` 内部的 free-list 合并/查找；地址正确但 free 失败也会
  得到同样的 5。
- 模型不能证明 A23 事件的具体调用序列；它只证明“完成被调用但 unmap 无效”与观察
  一致，而“完成缺失”与 host 的 5 个报告不一致。

## 下一步：记账 trace

在 usb:ds 侧做一次**只读 trace**，不改变 producer 行为：

- `FUN_0002c520`：endpoint `+0/+4/+8`、producer 条目地址、`[URB+0x10]`、
  `[URB+0x20]`、domain 指针、map 返回值；
- `FUN_0002c690`：consumer 条目地址、`[URB+0x10]`、`[URB+0x20]`、unmap 返回值、
  `+4/+8` 变化；
- 输出到 A23 mailbox/status 可读字段，NSP 在一次 3-URB/serial 运行后读取。

只有 trace 才能区分：

1. consumer 条目不是 map 的那一条 → 修 A23 完成与 URB 表的下标；
2. `[URB+0x10]` 正确但 `FUN_00004c70` 失败 → 修 domain/free；
3. `[URB+0x20]` 为 0 导致 unmap 被跳过 → 修 URB 条目字段。

## 修复候选（trace 之后）

- **局部记账修正**：让 complete 的 consumer 条目与 map 条目一一对应，并确认
  `[URB+0x10]/[+0x20]` 未被覆盖；
- **防御性 busy-map guard**：把 8 项表检查移到 map 之前，busy 分支不 map；这只能
  防止泄漏崩溃，不能解决 5 的停滞；
- **新 producer**：每 URB 明确 ID、完成、unmap，不依赖 A23 单 mailbox。

在 trace 出来之前，不再部署 A23 长流。
