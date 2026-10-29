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
