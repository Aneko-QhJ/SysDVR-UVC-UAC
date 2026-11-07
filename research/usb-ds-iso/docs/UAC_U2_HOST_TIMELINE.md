# U2 宿主时间线（macOS 侧为什么拆流）

日期：2026-11-07。范围：离线回读既有 macOS 实机日志 + v42 诊断准备；
**v42 未部署、0 实机**。

## 结论（先读）

- macOS 的 `usbaudiod` 收到**一个** isoch `transaction error` 就停流：
  错误 → `requestConfigurationChange` → `performStopIO` 只隔 4 ms。
- 停流本身 **104–138 ms**（内部 `abortGated` 掉 29–30 个在飞请求），
  随后 **90–200 ms** 才 `performStartIO`。设备侧看到的 alt0→alt1
  136–221 ms 就是这段。
- 宿主队列不浅：`lockDelayMS 100`（= `numTransactions 100`，100 ms），
  初始 24，因开场 "excessive zero length packets 20 > 2" 升到 100。
- ZLP 是常态：v38 一轮 6 s 的流里 `zlpCount` 到 88，只有 1 次
  `transaction error`；62 次设备 miss 只对应 3 次 host error。
- 由此，v38 残余的 ~2.5 s 损失是**宿主固定的 stop/start 代价**，
  不是设备侧重 arm 可调的参数；这也解释了 v37/v38/v40 调 lead 无效。
- **因果方向尚未判定**：62 次 miss 只有 3 次 host error，说明
  "miss → halt → host error" 不是充分条件。v42 用共享时钟判这个。

## 证据（v38 实机窗口，`log show` 回读）

```text
18:51:48.862 kernel    AppleUSBXHCIIsochronousRequest ... endpoint 0x84:
                       status 0xe00002ed (transaction error)
18:51:48.862 usbaudiod  completeBlock ... transaction status error: 0xe00002ed
18:51:48.862 usbaudiod  requestConfigurationChange requesting, completeBlock
18:51:48.866 usbaudiod  performStopIO stopIO
18:51:48.866 kernel    abortGated ... endpoint 0x84: aborting 30 requests
18:51:48.994 usbaudiod  performStopIO done [128.7 ms]
18:51:49.089 usbaudiod  performStartIO startIO
18:51:49.189 usbaudiod  performStartIO lockDelayMS 100 ...
```

对齐验证（v38 r1）：

| 设备 `alt0_since_alt1` | 宿主 `startIO → error` |
| --- | --- |
| 6464 ms | 6.42 s |
| 1606 ms | 1.59 s |
| 2541 ms | 2.45 s |
| 9543 ms | 9.5 s（抓取结束） |

- 设备 5 条 active alt0 ↔ 宿主 5 次 `abortGated`；其中 3 次前面有
  `transaction error`，另外 2 次是开场 ZLP 调参和抓取结束。
- 回读命令（只读，不需要 root）：

```sh
log show --start "2026-11-06 18:51:25" --end "2026-11-06 18:52:10" --style compact \
  --predicate 'process == "kernel" AND eventMessage CONTAINS "endpoint 0x84"'
log show --start "2026-11-06 18:51:25" --end "2026-11-06 18:52:10" --style compact \
  --predicate 'process == "usbaudiod"'
```

## 这改写了什么

- 上一轮的读法（v39/v41）是"一串错误 URB 才触发 teardown"。宿主日志显示
  **单个** error 就停流；一串 miss 更可能是 `abortGated` 期间（~110–140 ms）
  设备侧在飞请求陆续以 status=5 回来的结果。v41 的 ring dump 在**下一次
  alt1 之后**，记录的 `ago_ms` 又相对 `last_done_tick`，所以"串"的成员
  可能混进了 re-arm 之后的记录——需要在共享时钟下重判。
- 设备侧可动的只剩"让第一个 error 不出现"；lead/恢复参数没有空间。

## v42：共享时钟诊断（离线已备，未部署）

- 设备：v38 逐字节 + `-DUAC_U2_MISS_RING -DUAC_U2_TICK_LOG`。在
  `alt diag alt0/alt1`、`miss ring` 头、`teardown cancel`、`USB host connected`
  上加 `t_ms=`（开机毫秒）。
- 宿主：`tools/uac_host_capture.py` 同时录 `log stream --style ndjson`
  与 ffmpeg WAV，并抓 ioreg/audio 快照。
- 分析：`tools/uac_host_timeline.py` 用枚举锚点 + 每对 stopIO↔alt0
  求时钟偏移，把 ring 记录换算到宿主时间，逐条 error 给出
  `first_miss_ms_before_error`。

判别：

| 读数 | 含义 |
| --- | --- |
| 每个 burst 的首条 miss 早于 error **> 20 ms** | miss 在前，设备侧是因 |
| 首条 miss 在 error 之后或 ≤ 2 ms | host stop 造出 burst，设备侧无解 |
| 混合 | 需要按 burst 分类再判 |

## 操作（下一次实机，需另行通知开机）

```sh
# 1) 设备侧：v42 已部署。开机顺序很重要：先启动采集，再给 Switch 开机，
#    否则日志里没有枚举锚点（log stream 必须早于设备出现）。
# 2) 宿主侧（Mac）：工具先开 log stream，再等 SysDVR 音频设备出现，然后
#    才启动 ffmpeg（ffmpeg 不能打开还不存在的设备）。
python3 tools/uac_host_capture.py --out private/runs/<run>/ --seconds 20 \
  --wait-audio 30
#    看到 "log stream ->" 后立刻给 Switch 开机。
# 3) 关机、读卡、归档设备日志，然后对齐：
python3 tools/uac_host_timeline.py --device-log <device-log> \
  --host-log private/runs/<run>/host-log.ndjson --out private/runs/<run>/timeline.json
```

## 不证明

- 因果顺序（v42 才判定）；
- 宿主 stop/start 能否被设备侧避免；
- 任何性能提升；本轮只回答"谁先动"。
