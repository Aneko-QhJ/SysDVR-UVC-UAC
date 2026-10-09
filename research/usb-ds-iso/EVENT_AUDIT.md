# A18：有界 ISO3 事件 / MFI 诊断

2026-10-06。本版已完成本地实现、机器码验证和实验包构建，并已部署、进行一次实机测试。
16 包内容和原生状态正确，但首两包之间仍空一槽，**严格验收未通过**；
ISO3 已抓到首两成功 ED 的 MFI 差16。设备日志已回收，确认安装成功、唯一提交、
handler至ACK共0.428ms，无新增错误报告；SD保持A18且已安全推出，详见 `RESULTS.md`。
目标是补上 A17 的事件观测缺口；没有修复或确认空槽、原生 payload 错误的根因。

## 冻结条件

设备仍为 USB2/HS、endpoint 0x83、MPS256、interval4、lead32，单个 3072byte
URB 内含 16 个独立 Isoch+ED TD，每个 payload192，FrameID 每 TD +1。
主机使用 A17 host64-timing 的冻结源码和同一份静态 libusb backend，
request192、lead64、等待40ms、256槽、单次、fresh boot、视频关闭。
冻结接收器仅增加 ISO3 magic 兼容及本地头文件引用，接收、原生错误、overall、
取消、耗时记录和调度逻辑不变。原源码和静态库先验 SHA-256 不符时拒绝构建。

## 112byte 布局与采样边界

STATUS 仍为 version1 / 168bytes。ISO3 (`0x334f5349`) 与 ISO2 区分布局，
terminal、bitmap、actual 和首 TRB 地址仍位于相同偏移。

| 偏移 | 内容 |
| --- | --- |
| 0 | ISO3 magic |
| 4 | 首个匹配错误相对首 TRB 的 byte offset |
| 8 | 发布后的首 Isoch TRB control，含 FrameID/cycle |
| 12 | terminal：0=未完成，1=16 个不同 ED 成功，高位=匹配错误且保留 DMA |
| 16 / 20 | 完成 bitmap / 累计 actual |
| 24 | 首 TRB 虚拟地址，64bit |
| 32 | TD0 首个成功 ED：raw event 16bytes + MFI 4bytes |
| 52 | TD1 首个成功 ED；匹配错误时优先替换为首个错误的完整 raw event + MFI |
| 72 | terminal0 时首个被过滤事件：raw event + MFI |
| 92 | terminal 非零后的首个事件：raw event + MFI |

过滤槽可记录 null/foreign、非本次 TD、parity/对齐不符、plain Isoch success、
重复 ED 中最先出现的一项；本版不记录具体过滤分支或全量分类计数。
这些事件沿用 A17 的过滤结果，不能仅因其出现就认定控制器故障。
TD0/TD1 成功样本只在匹配 ED、CC1、actual192 且未重复时写入。
匹配错误总是替换偏移52的槽，偏移4说明错误属于哪个 TD；此时 TD1 原样本丢失，
解码器不再计算首两成功 ED 的 MFI 差。TD0 错误也保存在该错误槽。
后续过滤和终结后事件不覆盖已有快照，且不改变 bitmap、actual、terminal 或 dequeue。

每次被接受的新提交会清除四个记录的 event control，作为有效性标记。
**control0 的槽无效，其他字节可能陈旧，必须忽略。** 解码器不会输出无效槽的
raw/MFI。各字段的写入和报告复制不是一次原子事务；错误槽还要求 CC/长度与
terminal 一致，不能把暂时仍保留的 TD1 成功样本解释为错误快照。保留末次 STATUS
以及完整 JSONL。MFI 在软件事件 handler 入口读取，模 16384 的差值只表示
处理事件时的计数差，不是总线服务间隔。host/device 时钟仍未同步。

## 空间和所有权

注入代码为 **684bytes**，仅占 `[0x68D54,0x69000)`；不跨入 rodata。
Link 仍在 ring+0xF70，诊断页尾从 +0xF80 开始，事件快照写入最远到 +0xFEF。
指针筛选先验证原 ring 范围，再按 0xF70 回绕计算本次 512byte/32TRB 的相对位置，
并验证 Isoch/ED parity。只有 16 个不同、CC1、actual192 的 ED 才完整释放该 URB。
匹配错误和未完成状态仍阻止重投；无匹配、重复或终结后事件不会释放 DMA。

为腾出诊断空间， producer 合并无副作用的校验、保持 FrameID 的 11bit 截断、
以 byte 倒数结束 16 次循环，并对同地址 Link 使用等价拷贝。report hook 复用
目标 Build ID 的原始 `0x60E50` copy 函数，由原 report epilogue 恢复保存的 LR。
机器码测试覆盖全部 247 个 ring 起点、两种 cycle、wrap、FrameID 边界、首 TRB
最后发布、错误保留和重投保护、诊断写入边界、Bulk 路由及原报告寄存器恢复。
仿真验证指令路径，不能替代实际控制器和 DMA 时序验收。

## 重建与本地验证

```sh
python3 research/usb-ds-iso/tools/build_patch.py --burst --event-audit \
  --frame-lead 32 --explicit-all --mps 256 \
  --out research/usb-ds-iso/private/packages-A18-event-audit
python3 research/usb-ds-iso/tools/package_experiment.py --burst --revision A18 \
  --packages research/usb-ds-iso/private/packages-A18-event-audit

PYTHONPATH=research/usb-ds-iso/tests \
ISO_PATCH_PACKAGES="$PWD/research/usb-ds-iso/private/packages-A18-event-audit" \
research/usb-ds-iso/private/venv/bin/python -m unittest \
  test_burst test_event_audit test_summary test_ep0_ownership test_iso3_status test_audit_receiver -v
```

Unicorn 需允许 JIT。客户端/rollback 构建检查 NPDM；runtime installer 的真实 C
测试检查预检、幂等、混合输入拒绝、部分写入失败和回滚。接收器测试直接运行冻结
源码的 callback，拒绝丢包、重复、空槽、public/overall 错误、损坏及 actual256。
普通 `--burst` 构建仍使用原 ISO2 补丁，不自动启用本诊断。

## 下一次实机实验

包目录 `private/packages-A18-event-audit/A/`，配套 `rollback/`。
先备份现有 content 和同 Build ID 的 IPS，按包内 INSTALL 同时替换客户端/IPS、
移走重叠旧补丁并重启。保持 USB2/HS 和视频关闭。初始 STATUS 应为 IDLE/seq0/URB0。

从仓库根目录为本次单独创建空 run 目录，例如：

```sh
mkdir research/usb-ds-iso/private/runs/A-A18-HS-event-audit-001 && (
set -C
research/usb-ds-iso/private/packages-A18-event-audit/A/iso-probe-native-diag \
  --burst --packets 256 --trigger-delay-ms 40 \
  --log research/usb-ds-iso/private/runs/A-A18-HS-event-audit-001/run.jsonl \
  2>research/usb-ds-iso/private/runs/A-A18-HS-event-audit-001/native.log
python3 research/usb-ds-iso/tools/summarize_run.py \
  research/usb-ds-iso/private/runs/A-A18-HS-event-audit-001/run.jsonl \
  --out research/usb-ds-iso/private/runs/A-A18-HS-event-audit-001/summary.json
)
```

一个 run 目录只运行一次；接收器拒绝覆盖 JSONL/raw。即使 raw 内容正确，也需
16 包连续有序、native/public status0、actual192、overall0，以及本次 URB
status3/requested=transferred3072、bitmapFFFF/actual3072/terminal1 才算通过。
退出0只代表接收器的 public payload/URB 检查通过，必须额外核对 native.log
中16个有数据槽的 native status0；Darwin 某些状态会映射为 public success。
summary 解码 JSONL，不自动检查 native.log，不能将其 payload_passes 当成原生验收。
失败即停，保留 native/JSONL/raw/STATUS；仅 pending/retained 时使用配套接收器
`--cancel`（不加 `--burst`），不重投。随后回收完整 Switch logfile.txt，核对 A18
标记、runtime 安装、URB 和设备 ticks，再分析首两个 ED 处理时的 MFI 差及
过滤/终结后 raw 事件。单次成功仍不能宣称稳定、确认根因或进入 UAC/PCM 持续串流。
