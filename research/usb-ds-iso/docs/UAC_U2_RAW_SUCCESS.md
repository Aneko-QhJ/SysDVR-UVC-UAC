# U2 raw ISO success（2026-11-01 00:25）

## 结果

第一次在 Linux raw host 上收到完整 UAC ISO 数据：

```text
uac-raw-probe --trigger-first --delay-ms 30 --transfers 8 --timeout-ms 500
```

| 项 | 值 |
| --- | --- |
| host | transfer[1] 1344B（7 包）+ transfer[2] 1728B（9 包）= **3072B** |
| host 总计 | `valid=49 bad=79 bytes=3072` |
| device | `report req=3072 xfer=3072 status=3`；`complete rc=0 requested=3072 transferred=3072` |
| ring | `trb0 ctl=0x69e01411`（frame 1694）、`trb1 0x1c21`；完成后 box 清空 |
| crash | **无新 crash/fatal/erpt 报告** |
| 卡 | 恢复 `52069a44…`、删日志、安全弹出 |

## 关键

- **trigger-first + 30 ms**：先 SET_CUR，等 30 ms，再并发提交 8 个独立
  16×192 URB；第 1/2 个 URB 正好覆盖 cave 的 +32 frame TD。
- 之前 submit-first 只在最后一个 URB 收到 2 包；trigger-first 把窗口放到
  TD 附近，两个 URB 合计收满 16 包。
- cave 的 `iso_event` 累计 `actual=3072` 后调用 `complete_original`，
  device report 正常 `3072/status3`，host/设备两边一致。
- v14 的 one-shot+cancel 保证完成后没有 pending request，因此无崩溃。

## 证据

- `private/runs/UAC-u2-v14-trigger-success-20261031`（`run.json`、
  `device-log-trigger.txt`）
- `private/card-cycles/20261031-u2-v14-trigger-concurrent`

## 下一步

1. 同一命令再跑一次确认可重复性（需新授权）；
2. 之后设计连续/多 burst producer，把 16 ms 成功扩展为持续音频；
3. 8 个 descriptor-parser NOP 的全局风险仍需后续隔离。
