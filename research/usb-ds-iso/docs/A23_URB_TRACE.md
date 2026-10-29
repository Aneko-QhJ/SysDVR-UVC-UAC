# A23 endpoint 记账 trace（2026-10-29）

## 目标

在不改变 A23 producer 行为的前提下，从设备侧读出 **endpoint URB 表** 的真实状态：

- endpoint 对象指针；
- `+0` producer、`+4` consumer、`+8` in-flight count。

这些值能区分：

- count 仍为 5、consumer 未前进 → complete 没按 URB 递减；
- count 为 0、consumer 前进 → complete 调用了，但 IOVA unmap 没释放；
- count 异常大/小 → 下标漂移或重复完成。

## trace 报告

[patches/iso_burst_trace.S](../patches/iso_burst_trace.S) 在 A23 `iso_report` 的位置写入：

| diagnostics 偏移 | 内容 |
| --- | --- |
| `+0` | `ISO_PROBE_DIAG_MAGIC`（0x314f5349） |
| `+8` | endpoint 对象指针（u64） |
| `+16` | producer（u32） |
| `+20` | consumer（u32） |
| `+24` | in-flight count（u32） |

`_pollIsoProbe` 只在 diagnostics magic 匹配时复制；没有 magic 时 trace 会被丢弃（第一版
trace3 就是这样读到全 0）。

- 汇编 **680B / 684B**，余 4B；`iso_report` 仍在 `0x68fb4`；
- 不包含 per-URB selector，也不包含两阶段 START delta；
- 只替换 report 的诊断 copy；生产路径不变；
- endpoint 对象地址：`[x19+0x60] + 0x22000 + 0x1000 + 0xcf8`。

## 构建

trace NSP 用 **safe 77e7480 的 stream 源码** + trace payload + NOP：

```
git show 77e7480:source/uvc/uvc_device.c > source/uvc/uvc_device.c
# 生成 source/uvc/iso_runtime_payload.h：trace 22 edits + 8 NOP
make OUTPUT_DIR=... DEFINES="-DISO_PROBE -DISO_RUNTIME_PATCH ... -DFILE_LOGGING"
```

- `iso-stream-trace3-v3.nsp`
  SHA256 `6fe2ec156ef01033ff217a2d18cd54f82c3050760a2881531b4f485f1dcd3b88`；
- v1 `9e8fc035…` 没有 diagnostics magic，status 全 0；
- v2 `c237f250…` 用 manager+0x14c8+0x830 查 endpoint，但 x19 本身就是 endpoint
  对象；查错后 magic 也没写，status 仍全 0；
- v3 直接读 `x19`：endpoint=x19，`+0/+4/+8` 为 producer/consumer/count；668/684B；
- 已归档 `private/deployments/20261027-alt1-probe/builds/`；
- **未部署**。

## 读取

1. `iso-stream --transfers 1 --packets 256`（3 URB，48 包）；
2. `iso-probe --status`，取 `diagnostics_hex`；
3. 解码：

```
tools/decode_a23_trace.py <iso-probe.log>
```

输出 endpoint/producer/consumer/count。

## 预期

- 3 URB 后：endpoint 非 0；producer=3；consumer 应为 3，count 应为 0（若完成记账正常）；
- 若 count=3/consumer=0，说明 3 个 URB 的 complete 都没作用；
- 之后做 serial640 trace：host 只跑 **5 个 URB（160 包）** 就停，避免第 6 次 map 崩，再发 status 读 trace；
  - count=5/consumer=5 → complete 没递减；
  - count=0/consumer=5 → complete 正常但 IOVA 没释放。

## 风险

- 覆盖 report diagnostics 后，`iso-probe` 的原有诊断字段不再可用；只用于 trace build；
- `iso_report` 只在 host 发 status/report 时执行，因此必须在 stream 停止/alt0 之后读取；
- 3 URB trace 只验证读取链路；5 的结论要等 serial trace；
- 仍需要新的实机授权。

## 下一步

1. 用 trace3 验证报告/解码链路；
2. 构建 serial640 trace，host 在 5 个 URB 后停，读 trace；
3. 根据 count/consumer 选择修 complete 下标、修 unmap/free，或写新 producer。

## 第一次有效 trace：3 URB（2026-10-29 08:38）

- host：48 valid / 208 zero；
- status diagnostics 非零：

```
49534f31 00000000 6095f77201000000 03000000 03000000 00000000 ...
```

- magic `0x314f5349`；endpoint `0x172f79560`；
- **producer=3，consumer=3，count=0**。

说明 3 个 URB 的 complete 路径、consumer 前进、count 递减都正常；3 URB 不是
“完成没发生”。5 的问题要等 serial one-in-flight trace。

## 下一步：serial one-in-flight 5 URB

- `ISO_STREAM_BUFFERS=640`，只在 `posts == completes` 时发下一个；
- host 只跑 **160 包（5 URB）** 就 alt0，避免第 6 次 map；
- 读 status：
  - count=0/consumer=5 → 表释放了，IOVA/free-list 没复用；
  - count=5/consumer=5 → count 没递减；
  - producer/consumer 异常 → 下标漂移。

## serial5 trace NSP（2026-10-29）

- `iso-stream-trace-serial5.nsp`
  SHA256 `ef40adb93b4c282036958546787b00bc2b22a373ae969931ede774e83d6b9f58`；
- safe 77e7480 源码 + `ISO_STREAM_BUFFERS=640` + one-in-flight guard
  （`posts != completes` 时不下发）；
- 归档 `private/deployments/20261027-alt1-probe/builds/`，未部署；
- host：`iso-stream --transfers 1 --packets 160`（5 URB）；然后
  `iso-probe --status --log serial5.jsonl`，`tools/decode_a23_trace.py`。

预期与分支：

| 结果 | 含义 | 处理 |
| --- | --- | --- |
| producer=5, consumer=5, count=0 | 表释放，IOVA 没复用 | 查 `FUN_00004c70`/domain free-list/`[URB+0x10]` |
| producer=5, consumer=5, count=5 | count 没递减 | 修 A23 complete/URB 表 |
| producer/consumer 漂移 | 下标/事件错位 | 回 completion/URB ID |

注意：one-in-flight 下第 6 个应晚于第 5 个完成，host 160 包后立刻 alt0；若实测已
崩，说明 6th 仍被下发，需要先停线程再读。

## serial5 实机结果（2026-10-29）

- host：48 valid / 112 zero（160 包窗口）；
- 设备 stop 日志：`posts=5 completes=4 errors=0 attempts=5`；
- stop 后 status trace：endpoint `0x3e6f5b1e0`，**producer=5，consumer=5，count=0**；
- 无新 crash report（最新仍为 08:10 的 serial640）。

结论：**5 个 URB 后 URB 表干净**；第 6 次 map 失败不是表/count 问题，而是 5 页
IOVA 在 unmap 后没有复用。one-in-flight 下只有 3 个 URB 的数据到了 host，这是
另一个 timing/data 问题，与 IOVA 结论分开。

## 审计后（2026-10-29）

静态审计确认：`+0/+4/+8` 归零不能证明 unmap 成功。`FUN_0002c690` 在
`[URB+0x20]==0` 时跳过 unmap，且不检查 `FUN_00004c70` 的 `0x19a8c` miss；
两种情况都只泄漏、不崩溃。下一次 trace 必须读 `[URB+0x10]/[+0x20]` 或记录
`4c70` miss 计数。见 [A23_URB_UNMAP_AUDIT.md](A23_URB_UNMAP_AUDIT.md)。

## v4 URB 字段 trace（2026-10-29，离线构建）

v3 的 `+0/+4/+8` 只能证明表归零，不能证明 unmap 发生。v4 直接把
**最后一个完成 URB** 的两个字段写进 diagnostics：

| 相对 diagnostics | 内容 |
| --- | --- |
| `+0` | magic `0x384f5349`（`ISO8`） |
| `+8` | consumer（u32） |
| `+12` | `[URB+0x10]`：最后一次完成登记的 IOVA（低 32 位） |
| `+16` | `[URB+0x20]`：该 URB 的 requested size |

URB 条目 = `endpoint + 0x78 + ((consumer - 1) & 7) * 0x30`。v4 不再写
endpoint/producer/count；consumer 与 status 的 sequence/state 足以定位轮次。

- 汇编：[patches/iso_burst_urb_trace.S](../patches/iso_burst_urb_trace.S)；
  注入 **680/684B**，余 4B；`iso_report` 仍在 `0x68fb4`。
- 构建工具：[tools/build_a23_urb_trace.py](../tools/build_a23_urb_trace.py)：
  用 safe `77e7480` 的 stream 源码、`ISO_STREAM_BUFFERS=640`、
  `posts == completes` 单飞门，以及同一 manifest 生成的
  `iso_runtime_payload.h`；START delta 用 before==after 的空操作，避免两阶段变量。
- 离线产物（未部署）：
  - NSP SHA256 `a3eb8aa9f73c40270bf01d270bb67964756eae58eb28370acd45d18911665da0`；
  - IPS SHA256 `dc72fd8f…`；payload SHA256 `51c79a8f…`；
  - 目录 `private/analysis/A23-urb-trace-v4-20261029-r3/`。
  - r2（`f6b3e2fb…`）的 `_pollIsoProbe` 条件未包含新 magic，status 会丢弃 v4
    diagnostics；r3 已补 gate，只把 r3 作为候选。构建器会同时把 magic 条件写进
    safe 源码副本，避免再次出现“payload 对、读取端丢”的情况。

### 读取与判定

1. `iso-stream --transfers 1 --packets 160`（5 URB，serial 单飞）；
2. 停流/alt0 后 `iso-probe --status`；
3. `tools/decode_a23_trace.py <log>`：

| `last_size` | `last_iova` | 解释 |
| --- | --- | --- |
| 0 | 任意 | `2c690` 在 `[URB+0x20]==0` 时跳过 unmap；`4c70` 没被调用 |
| 非 0 | 0 | unmap 分支被调用，但地址为 0；`4c70` 应 miss 并返回 `0x19a8c` |
| 非 0 | 非 0 | 最后一条 URB 字段正常；若 IOVA 仍不复用，问题在更早条目或 free tree |

### 限制

- 只读**最后一条**完成的 URB；若泄漏发生在更早条目，v4 会显示正常。下一步可做
  “8 条目 size 非零计数 + IOVA 低位和”的 v5，代价是更大的循环代码。
- 不记录 `4c70` 的返回值；要证明 miss，需要在 `2c690` 的调用点加只读计数，属于
  另一轮 runtime patch。
- 未部署；实机需要新的明确授权，且不应与 A23 长流或 per-URB 两阶段混在同一轮。
