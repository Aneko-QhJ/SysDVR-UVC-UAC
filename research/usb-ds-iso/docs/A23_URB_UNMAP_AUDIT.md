# A23 完成路径的 unmap 静态审计（2026-10-29）

## 问题

serial5 实机在 5 个 URB 后读到 endpoint `producer=5`、`consumer=5`、`count=0`，
URB 表干净；serial640 仍在第 6 次 DMA map 处 `svcBreak`。本轮离线只回答：
**从 `FUN_0002c690` 到 `FUN_00004c70`/`FUN_000040e0` 的完成路径，哪一步可能
“表已清、页没释放”且不崩溃？**

输入是用户固件提取的 usb 模块（BuildID `AD8D36F2…`，
`private/module/usb.elf`，SHA256 `10b280d4…`）。使用 Ghidra 12.1.4 headless
反编译指定地址；产物与命令见 `private/analysis/A23-iova-free-list-audit-20261029-r1/`。

## 结论

1. **正常完成确实会 unmap**：`2c690` 在 `[URB+0x20] != 0` 时调用
   `4c70(domain, [URB+0x10])`，然后推进 consumer、递减 count。
2. **`2c690` 不检查 `4c70` 的返回值**。`4c70` 在地址不属于已分配块时返回
   `0x19a8c`，不释放任何东西；这个返回值被直接丢弃。
3. 因此有两条**静默泄漏**分支，都会让 `+0/+4/+8` 看起来正常：
   - `[URB+0x20] == 0`：整个 unmap 分支被跳过；
   - `[URB+0x10]` 不是 map 时登记的对齐地址：`4c70` 查不到，返回
     `0x19a8c`，`2c690` 忽略。
4. `4c70` 只有在 `40e0` 返回非 0 时才会 assert；`40e0` 找不到块时也返回
   `0x19a8c`，但此时 `4c70` 已经在 `40e0` 的返回值上 assert。**查不到地址
   本身不会 assert**，这解释了“没有新 crash report、但页可能没释放”。
5. `40e0` 把释放块按**基址**（`+0x20`）插回 free tree，而 `3d40` 分配时用
   `ceil(size/align)*align` 作为搜索阈值。这个不对称暂标为可疑；在 IOVA 地址
   位于高位时，搜索仍会选中最小的可用块，不能单独解释 5。它需要单独的
   trace 才能排除。

## 调用链与字段

### 提交（`FUN_0002c520`）

```
2c520(endpoint, &urb, handle, buffer_va, size)
  -> 3c50(domain, &iova, handle, buffer_va, round4k(size), 0x10000, 0, 3)
       -> 3d40(allocator, size, align=0x10000, 0, buffer_va, handle, 0)
       -> 9040(domain mutex lock)
  -> URB = endpoint + 0x78 + producer*0x30
       +0x08 = buffer_va
       +0x10 = iova
       +0x18 = iova
       +0x20 = size
       +0x28 = 1 (status)
       +0x2c = 0 (transferred)
  -> count++, producer=(producer+1)&7
```

### 完成（`FUN_0002c690`）

```
2c690(endpoint, result, terminal, requested, lock)
  URB = endpoint + 0x78 + consumer*0x30
  if URB->status == 2: done
  ...
  if URB->size (+0x20) != 0:
      domain = 30c0(endpoint->manager)
      4c70(domain, URB->iova (+0x10))       // 返回值不检查
  consumer=(consumer+1)&7
  count--
```

### `FUN_00004c70`（释放入口）

- 以 `domain+0x50` 的树按地址查找已分配块；用
  `aligned = node[+0x38] + (u32)node[+0x30]` 还原对齐地址，并检查
  `[aligned, aligned + node[+0x28])` 是否包含参数。
- 找到：解锁 `domain+0x24`，调用 `40e0(allocator, aligned)`；`40e0` 返回非 0
  则 `FUN_00009540()`（assert / `svcBreak`）。
- 找不到：返回 `0x19a8c`，不释放、不 assert。

### `FUN_000040e0`（free tree 插入）

- 在 `allocator+0x20` 的已分配树里按参数查找块，校验
  `[node[+0x38] + u32 node[+0x30], + node[+0x28])`。
- 移除节点、`allocated_count--`，新建 free 节点：
  - `+0x20` = 块基址（tree key）
  - `+0x28` = 块大小
  - `+0x30` = 块基址
- 插到 `allocator+0x08` 的 free tree；**不做相邻块合并**。
- 当 `allocated_count` 归零时，用 `allocator[10]/[0xb]` 的原始区间重置 free tree。
- 找不到返回 `0x19a8c`（会被 `4c70` 转成 assert）。

## 为什么现有 trace 不够

serial5 的 `diagnostics_hex` 只有 magic、endpoint、producer、consumer、count。
两条静默泄漏分支都发生在 `2c690` 内部，完成后 `+0/+4/+8` 仍然归零，所以
“表干净”不能推出“页已释放”。

要区分它们，下一次 trace 至少需要：

| 字段 | 来源 | 用途 |
| --- | --- | --- |
| `[URB+0x10]` | endpoint 表 | 是否等于 map 时登记的 IOVA |
| `[URB+0x20]` | endpoint 表 | 是否为 0（unmap 被跳过） |
| `4c70` 返回值 / miss 计数 | 需要在 usb:ds 侧 hook | 区分“找到了但 40e0 失败”与“没找到” |
| domain 指针 | `endpoint->manager` | 确认 free 的是同一个 domain |

最小可行版本可以只读 status 时刻 8 个 URB 条目的 `+0x10/+0x20`，或记录
`consumer-1` 条目的这两个字段；这能先分辨“size 为 0”与“IOVA 不匹配”。
该最小版本已实现为 v4 trace 并实机一次：
[A23_URB_TRACE.md](A23_URB_TRACE.md)（680/684B，r5 `b0cbe1ed…`）。
结果：consumer=5、最后完成 URB 的 size=3072、IOVA=0x80030000，
`last_entry_present`；最后一条没有走 size=0 分支。本轮只到 5 URB，
没有尝试第 6 次 map，因此仍不能判定更早条目/free tree 是否泄漏。
v5 全条目版本随后又做了 320 包 + `caffeinate`：host 96/320、bad=0，
设备 `posts=8 completes=7 errors=0`、**无 usb fatal**；8 个条目仍只在
`0x80030000`/`0x80040000` 两页间交替。第 6/7/8 次 map 都成功，说明
one-in-flight 下 unmap/复用连续成立；本 build 没有“5 页墙”，
serial640 的崩溃需要按当时的 in-flight/主机状态重新解释，不能再归因于
`4c70` 永久 miss 或 free tree 必然泄漏。
若要统计每次完成的返回值，需要在 `2c690` 的 `4c70` 调用点加只读记录，属于
runtime patch 的下一步，不应和现有 A23 注入混在同一轮变量里。

## 与 5 的关系

- 5 个 URB 后表干净、host 只收到 3 个 URB 的数据，说明 completion 事件数
  与实际交付数不一致；A23 的单 mailbox 没有 URB ID/代际，本来就可能把事件
  归属到错误的 URB。
- 如果错误归属让某个完成读到 `[URB+0x20]==0`，或读到不是本次 map 的
  `[URB+0x10]`，页就会静默泄漏；5 次后第 6 次 map 失败/assert。
- 这只是与现有观察一致的**候选解释**，不是已证明的根因；“5 页”本身仍是从
  观察反推的容量假设，domain 的实际大小和 64K/4K 对齐语义还要 trace 确认。

## 未证明

- `4c70` 是否真的被调用、每次的返回值；
- `[URB+0x10]/[+0x20]` 在完成时的实际值；
- free tree 的地址 key 与 size 阈值是否会导致第 6 次分配选不中；
- domain 的实际区间大小（5 页还是 5 个对齐槽）。

在拿到上述字段前，不再部署 A23 长流，也不把 serial5 的“表干净”改判成
“unmap 正常”。

## 证据

- `private/analysis/A23-iova-free-list-audit-20261029-r1/usbds-iova-decomp-r2.txt`
  （SHA256 `493d5832…`，43 个函数，含反汇编与 decompiled C）；
- `private/analysis/A23-iova-free-list-audit-20261029-r1/README.md`（命令与哈希）；
- `private/module/usb.elf`（SHA256 `10b280d4…`，BuildID `AD8D36F2…`）；
- 现有实机：`private/runs/A-alt1-trace-serial5-20261029/`；
- 相关专题：[A23_URB_TRACE.md](A23_URB_TRACE.md)、
  [A23_URB_ACCOUNTING_MODEL.md](A23_URB_ACCOUNTING_MODEL.md)、
  [A23_BUSY_MAP_LEAK.md](A23_BUSY_MAP_LEAK.md)。

## 10s 复测补充（2026-10-29 18:01）

同 v5 build、640 缓冲、单飞、`caffeinate` 下跑满 10000 包：host 3392 有效包、
bad=0；设备 `posts=214 completes=213 errors=0`，无 usb fatal；8 条目仍只在
两页间交替。unmap/复用连续 214 轮成立，原始 serial640 的 5 URB 崩溃未复现。
本轮不再支持“`4c70` 永久 miss/ free tree 必然泄漏”作为旧崩溃解释；优先查
当时的 host 休眠/USB 调度或运行状态。
