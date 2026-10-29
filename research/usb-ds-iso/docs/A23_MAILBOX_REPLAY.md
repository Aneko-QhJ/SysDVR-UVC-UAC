# A23 三 URB in-flight mailbox replay（2026-10-28）

## 复现

`test_mailbox_multiplex.py` 用 `test_patch.Machine` 执行真实 A23 补丁：

```sh
cd research/usb-ds-iso/tests
ISO_PATCH_PACKAGES=../private/tmp-import-20261029/builds/a23-burst \
  ../private/tmp-import-20261029/deps/dsh-unicorn/bin/python \
  -m unittest test_mailbox_multiplex -v
```

为了模拟真实 request 的 idle gate，测试在每次 `submit(3072)` 前把
`ENTRY+0x20` 设为 `ENTRY+0x18`；A23 的 mailbox/事件代码保持原样。

## 结果

```
submit 0  rc=0  enqueue=RING+0x200
submit 32 rc=0  enqueue=RING+0x400
submit 64 rc=0  enqueue=RING+0x600

slot 0 的 16 个 ED 事件  ->  []
slot 32 的 16 个 ED 事件 ->  []
slot 64 的 16 个 ED 事件 ->  [(0x2a980, [MANAGER, 0x83, 0, 1, 3072, 1])]
```

也就是说：**3 个 in-flight URB 只有最后一个会调用 `complete_original`；前两个的
16 个 ED 事件全部丢失**，因为 `iso_enter` 每次重置同一个 mailbox，`first` 指向最新
URB。

## 后果

- 每个 3-URB 窗口：`entry+8` 增加 3，完成只减少 1；净增 2。
- 到 `entry+8 == 8` 后，`FUN_0002c520` 仍然先 DMA map 再返回 busy；busy 分支不
  unmap，于是每次重试泄漏一个 IOVA。
- 几次之后 `FUN_00003d40`/`FUN_00003c50` 分配失败并 assert；这就是 5/640 池和
  复用崩溃的共同 DMA map 崩溃。
- 3 URB 的 48 包数据能到 host，是因为 TRB 数据路径本身正确；完成记账从第一个
  窗口起就是错的。

## 结论

- 单 mailbox 不是“可能”，而是已被离线复现：多 URB in-flight 无法正确完成。
- 连续 PCM 必须：
  1. 每 URB 独立 mailbox/ID/代际；或
  2. one-in-flight，接受 16ms 数据 / 48ms 周期（33%，32ms 空档）。
- 当前 A23 诊断 producer 不应再用于多 URB/长流。

## 设计续接

per-URB mailbox 的最小布局和 cave 预算见
[A23_PER_URB_MAILBOX_DESIGN.md](A23_PER_URB_MAILBOX_DESIGN.md)。

## 测试位置

- `tests/test_mailbox_multiplex.py`；需要 Unicorn 和 A23 包，不在 quick 套件里。
- 包可用 `tools/build_patch.py --burst --frame-lead 32 --explicit-all --mps 256`
  重建；测试通过 `ISO_PATCH_PACKAGES` 指向其目录。
