# 从这里开始

## 60 秒

1. 读 [docs/CURRENT.md](docs/CURRENT.md)（事实与下一步）。
2. 读 [WORKFLOW.md](WORKFLOW.md)（一轮怎么走）。
3. 从 CURRENT 的“开放问题”里选一个，写 5 行问题卡。
4. 离线准备，跑 `make -C research/usb-ds-iso check`。
5. 实机按“当前边界”里的授权执行；插卡/开机前通知用户，失败即停。

## 不要做

- 不要把 [docs/STATUS.md](docs/STATUS.md) / [docs/PROGRESS_HANDOFF.md](docs/PROGRESS_HANDOFF.md)
  里的旧“下一项仅……”当成当前指令。
- 不要覆盖、移动或清理 `private/` 里的原始证据。
- 不要用模型通过、保存成功、超时或安静采样推断 I/O 已交还。
- 不要越过“当前边界”的授权范围部署、写卡、启动接收器或开机测试。
- 用户说“部署”只等于把文件拷贝到卡上；插卡与开机由用户执行，代理只提前通知，不自行开机。
- 不要把“主机 raw 正确”单独当成严格传输通过，也不要把它改判成失败。

## 存储与继续研究

2026-10-29 已完成一次性精简；后续研究不设容量门禁。
当前源码、输入、原始实机证据与票据均保留。过时离线审计和恢复包已按用户要求精简，
不保证复现任意旧版本。旧路径缺失时先查 [STORAGE.md](STORAGE.md) 的处置清单，
不要为重放历史流程补回整套旧树。常规测试产物使用临时目录，结束后清理。

## 当前边界（2026-11-07 00:2x）

- 实机授权：2026-11-01 16:19 起常设授权“部署测试不再需要授权；通知插卡/
  开机即可”（一次 boot、失败即停、不重试）。
- **当前最佳配置**：
  - 设备镜像 **v30e `1737eb35…`**（93050 B，= v29v payload 逐字节相同）：
    cave `pipe_quad_log.S` 548/684 B、`ISO_ENTRY=0x300`、3 在飞、miss 立即
    cancel + 重投、`STREAM_POSTS=512`、`MAX_RECOVERIES=128`、quiet + evlog。
  - host：`uac-raw-probe4 --trigger-first --delay-ms 30 --packets 16
    --transfers 32 --rearm --max-urbs 2048 --timeout-ms 10000 --keep-alt`
    （probe4 = probe3 把 `MAX_URBS_TOTAL` 1024→4096；每套约消耗 2 个 URB）。
- **长跑（v30e 两轮，8.9 s）**：r1 498 段 / 1529856 B / 89.7% / 5 事件 /
  `max_gap 92`；r2 **494 段 / 1517568 B / 88.0% / 7 事件 / 87 ms**（host
  88.9%）。两轮合计 **0.67 事件/s**、交付 96.5–97.3% → 稳态成立。r1 的
  五次事件间隔恰好 ~1.85 s，**r2 变成 2096/463/480/689/463/2337 ms，
  周期不重现，判为巧合**。
- **macOS 裸机（v30e→v30h）**：v30e 没出流（宿主不发 SET_CUR）；v30f 在
  EP0 里 inline 跑训练堵住 status stage（`bytes=0`）；v30g 改 worker 线程 →
  出数据但宿主切了 440 次 alt；**v30h 连续 producer（alt1 开、alt0 停、可重
  新 arm）把 alt 切换压到 15 次**，15 段训练共投 1014 套 = 16.22 s，宿主录到
  **14.21 s（69% 墙钟）**、46 miss（~1.15 事件/s）、每段 `max_gap 28–67 ms`、
  无 crash。**形态对了，剩下的是 miss 率 + 宿主样本差；VM 的 88–90% 不是
  虚拟 EHCI 伪影。** 两个参数实验都是负结果：v30i（arm 40 ms）18 段 / 895 套 /
  宿主 54%，v30j（in-flight 4）12 段 / 800 套 / 59 miss / `max_gap` 68–115 ms
  ——都回退到 v30h 配置。
- **短跑最好一轮（v30a，32 在飞）**：253 段 / 777216 B / 94.1% / 1 次 /
  `max_gap 78`；同配置复跑 v30d 247 段 / 3 次 / 89.4% → 单轮不能排序
  16/32/64，**8 深明显更差**站得住。
- **已定论**：
  - miss = 控制器的 **code 23（Missed Service）**；驱动 `0x31274` 对 23
    只置 halt、**不复位 ring**，所以 cave 无法 rearm，只能靠 app 收到
    `status=5` 立刻 cancel + 重投 → ~80–92 ms 内恢复、丢 1 套。
  - 设备侧其它假设全部否掉：lead 16/24/40、在飞 4、空 ring 门、memset
    长度、host 预排 8/16。
- **宿主侧事实**：设备在 **Bus 001 / `ehci-pci`**（不是 xHCI），内核没有
  ehci tracepoint；可用 **usbmon bus 1** 或 probe 的 per-packet detail
  （`urb[N] detail p<idx>=<status>/<len>`）。
- **v31 已判负（macOS 一次 boot）**：驱动侧 code-23 快速恢复 NSP `997de2f7…`
  （47 edits）把 `0x31274` 的 halt-only 分支换成 `bl 0x2feb0` + `b 0x31118`。
  实机 13 段 / 1011 套 = 16.18 s（v30h 1014 / 16.22 s）、**status=5 仍 30 条**、
  每段 `max_gap 30–83 ms`（v30h 28–67，均值 43 vs 38）、宿主 14.184 s
  （v30h 14.21）；无新 crash/fatal/erpt。→ **halt 握手不是空洞来源**，app 的
  cancel 往返 + cave 的 32 ms lead 才是。已恢复 v30h；下一杠杆是 app/cave 的
  恢复路径（不 cancel、不整环重放），另需一轮分辨抓取后 106 次重连是否与 v31
  有关（本轮空闲窗口长 30 倍，无 crash 报告）。
- **v32 keep-ring 已判负（macOS 一次 boot）**：NSP `4146dba7…`（46 edits，
  cave 680/684 B，app +`KEEP_RING`）。机制跑通（18 条 keep-ring 标记、
  `recoveries=1`），但交付 926 套 / 14.82 s（v30h 1014 / 16.22）、宿主
  11.499 s（v30h 14.21）、`max_gap` 均值 48.6 / 最长 154 ms（v30h 37.8 / 67）、
  status=5 38 条（v30h 30）、2 段 bytes=0。原因：halt 期间排队的 TD 套帧号
  已过期，resume 后被控制器当成新的 missed service；训练开头还会静默到
  macOS 切走 alt1。→ **回退 v30h**；32 ms lead 是必需品，下一杠杆是缩短
  re-arm 代价（新鲜帧号 + 更短 lead），不是保留旧套。
- **v33 lead-16 已判负（macOS 一次 boot）**：NSP `17118535…`（46 edits，只改
  re-arm 首套 lead 32→16 ms）。957 套 / 15.31 s（v30h 1014 / 16.22）、
  status=5 **40**（v30h 30）、`max_gap` 均值 47.4 / 最长 **126** ms
  （v30h 37.8 / 67）；宿主 12.872 s，但流内只有 3 段静音（v30h 105）——
  抓到的时长短 1.3 s，属混淆。→ **16 ms 太紧，回退 lead 32**；lead 不是
  免费杠杆。下一步转 **alt 抖动**（20 s 里 18 段训练）或 miss 率本身。
- **v34 诊断成功（macOS 一次 boot）**：NSP `71af3d22…`（与 v30h 行为相同，
  只加 alt 日志）。**每次 alt0 都在一次 status=5 miss 之后，流已静默
  42–75 ms**；宿主随后 122–191 ms 重新 arm alt1；没有一次 alt0 发生在健康
  流上。→ **alt 抖动是 miss 恢复太慢的后果**，宿主容忍 <~40 ms。下一轮目标：
  把 miss 恢复压进 40 ms（驱动侧即时 re-arm + app 不 cancel，或 post-miss
  专用短 lead）；先修 logger 竞态。
- **v35 短 lead 已判负（macOS 一次 boot）**：NSP `a6ed6f15…`（cave 600 B）。
  843 套 / 13.49 s（v30h 1014 / 16.22）、status=5 **56**（v30h 30）、
  `max_gap` 均值 70.2 / 最长 87、18 次重连。16 ms 不够取首套。**但诊断命中**：
  `cancel_ms≈0`、**`react_ms≈53 ms`**——成本在 app 的 miss 路径（每次 miss 的
  evlog dmnt dump + SD 日志），不在 cancel 也不在 lead。回退 lead 32；下一步
  去掉 per-miss evlog dump（app-only）。
- **v36 end-only evlog 小胜（macOS 一次 boot）**：NSP `79ce6baf…`（cave 仍
  v30h）。`react_ms` **53→22.5**、`cancel_ms 0`；交付 **1019 套 / 16.30 s**
  （最好）、宿主 14.238 s、**静音 0.208 s（v30h 0.42，减半）**、98.4% 方波；
  `max_gap` 均值 45.9 / 最长 60（v30h 37.8 / 67）。→ 保留。空洞现在由
  `react 22 + lead 32` 主导；下一步 lead 24 和/或再去两行 miss 日志。
- **v37 成立，新最佳（macOS 一次 boot）**：NSP `3a330aa3…`（94481 B，cave
  `pipe_quad_lead24.S` 548/684 B，lead 24；两行 miss SD 日志编译掉）。
  `react_ms` **22.5→0**、`cancel_ms 0`；**每段 `max_gap` 均值 35.3 / 最长 40**
  （首次全部 ≤ 宿主 ~40 ms 容忍）；交付 **1133 套 / 18.13 s**（最好）、宿主
  **15.575 s**、**方波 100% / 静音 0 段**（v36 87 段 / 0.208 s）。代价：misses
  67（v36 40）、alt1 8 / alt0 9。→ **保留**。下一步 = alt0 次数与 miss 率。
- **v37/v38 同档（各两轮 boot）**：v37 `3a330aa3…`（lead 24）15.575 / **16.503** s；
  v38 `1b6a6014…`（lead 20）**16.469 / 16.839** s，交付 19.1–19.4 s、`react 0`、
  `max_gap` 均值 32–36。v38 两个样本都略好，但 **n=2、delta < spread，
  “lead 24→20 更好”不成立**；v38 保留为载体，lead 这条线关闭。**真正成立的是
  v36→v37**（去两行 miss SD 写：`react 22.5→0`，宿主 14.24 → 15.6–16.8 s）。
  剩余损失 = 每轮 4–8 次 alt0 + 每次 136–221 ms 重 arm；这些 alt0 都紧跟一次
  status=5（`dt_done 0–17`），但 47–67 次 miss 只有 4–8 次触发，**条件未知**。
- **v39 诊断命中（macOS 一次 boot）**：NSP `7d30fbe7…`。**alt0 跟在 miss 串的
  最后一个之后 1–16 ms**；串 = 2–10 个 miss、间隔 20–25 ms（常见同 tick 成对），
  **孤立 miss 不触发**；触发点无单条属性（infl 2–4、slot/urb 随机、段龄
  171 ms–7.8 s）。扰动：训练结束的 dump 让下次 alt1 晚 60–100 ms，本轮宿主
  15.058 s 不与 v38 可比 → 以后 dump 放下一次 alt1 之后。下一步：打断 miss 串
  （halt 门控 32 ms 首套 / 首次 miss 不 cancel）。
- **v40 判负（macOS 一次 boot）**：halt 门控 32 ms 首套把 `max_gap` 推到
  47–54 ms（均值 44.8），**但 alt0 仍 6 次、miss 率 2.9/s**——串不是 lead 造的。
  宿主 16.346 s / 交付 19.07 s 仍在 v38 带内。→ **回退 v38（lead 20）**；
  若继续，只剩“首次 miss 不 cancel”这一条路。
- **v41 否掉 cancel 假设（macOS 一次 boot）**：NSP `dc9151b1…`。串内每条 miss
  的 `since_cancel_ms` 都是 **19–26 ms（= 一个 lead）**，自发 miss 是
  268–2387 ms → cancel 不是源头，串是“cancel → 20 ms lead → ~21 ms 后再 miss”
  的**自持环**，根因是宿主那一帧没有排队 URB。**设备侧 lead/恢复路线到此为止**；
  v38 仍是载体（两轮 16.5–16.8 s）。dump 改到下次 alt1 后已不再扰动
  （`since_alt0` 133–224 ms）。
- **v42 宿主时间线（离线回读，0 实机）**：macOS 的 `usbaudiod` 收到**单个**
  isoch `transaction error` 就停流（错误→`performStopIO` 4 ms；停流 104–138 ms，
  再 90–200 ms 才 `performStartIO`）；设备侧 alt0→alt1 的 136–221 ms 就是这段，
  5 次 alt0 ↔ 5 次 abort，`6464/1606/2541/9543 ms` 与宿主逐段吻合。宿主队列
  `lockDelayMS 100` 不浅，ZLP 常态不致命。→ v38 的 ~2.5 s 是宿主固定
  stop/start 代价；因果（miss 先还是 error 先）仍未判。v42 诊断
  `0e3da14f…`（95227 B，v38 + `-DUAC_U2_TICK_LOG`）**已构建、未部署**；
  宿主工具 `uac_host_capture.py` / `uac_host_timeline.py` 已备。
  见 [docs/UAC_U2_HOST_TIMELINE.md](docs/UAC_U2_HOST_TIMELINE.md)。
- **参数调优到头**：arm 延迟（v30i）、在飞 4（v30j）、驱动 halt 快速恢复（v31）、
  keep-ring 恢复（v32）都是负结果。VM 数字（~90% 占空、0.67 次/s）只描述 probe 路径，不是真实宿主
  上限。
- **已知小缺口**：USB 字符串描述符未实现（宿主只显示 VID/PID）；
  8 个 descriptor-parser NOP 仍未隔离。
- 卡：**v42 `0e3da14f…` 已部署、已弹出、未开机**（11-07 21:5x；
  备份 `52069a44…` 在 `private/card-cycles/20261107-u2-v42-host-clock/backup/`）；
  VM 挂起；v30e 两轮 + macOS v30e…v30j + v31…v41 证据已归档。

## 文件角色

| 文件 | 角色 |
| --- | --- |
| [docs/CURRENT.md](docs/CURRENT.md) | 唯一当前状态；每轮更新 |
| [WORKFLOW.md](WORKFLOW.md) | 最小流程；怎么开一轮 |
| [docs/RESEARCH_RULES.md](docs/RESEARCH_RULES.md) | 安全边界与验收定义 |
| `docs/A23_*.md` | 专题细节；完成后只读 |
| [README_HISTORY.md](README_HISTORY.md) | 时间线；只追加 |
| `private/` | 原始字节；只读 |
