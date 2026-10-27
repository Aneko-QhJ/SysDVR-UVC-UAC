# 实验分支目录与本地产物

`research/usb-ds-iso/README.md`是唯一研究入口。短期状态写入`docs/STATUS.md`；详细证据按实验
写入`docs/`，历史结果保留在`docs/RESULTS.md`，后续条件集中于[TEST_PLAN.md](TEST_PLAN.md)。
补丁汇编集中到`patches/`，主机源码在`host/`，
构建与离线分析在`tools/`，可持续使用的采集流程在`tools/workflows/`，测试在`tests/`。

冻结部署包、厂商模块、第三方构建及实机raw/native/log证据放在忽略提交的`private/`。
保留已有目录和文件哈希，避免重写冻结manifest中的路径与历史命令。新的设备构建输出统一
放在`private/builds/sysmodules/`；旧仓库根目录的25个实验构建文件/目录移至
`private/legacy-builds/root/`，保留其字节内容。常规视频构建仍沿用Makefile默认输出。

## 统一入口

以下命令可从仓库根目录执行，也可用脚本绝对路径从其他目录执行：

```sh
python3 research/usb-ds-iso/tools/experiment.py status
python3 research/usb-ds-iso/tools/experiment.py verify
python3 research/usb-ds-iso/tools/experiment.py restore --dry-run
python3 research/usb-ds-iso/tools/experiment.py restore --scope capture
python3 research/usb-ds-iso/tools/experiment.py restore --scope patch
```

`status`读取本地状态，不访问USB。`verify`核验当前包、冻结主机工具、最新run/collection/
deployment的SHA256SUMS；缺失或不一致会报错。

`restore`默认从Git公共目录中的`experiment-artifacts/<实验分支名>/research/usb-ds-iso/private`
选择性恢复输入。这是只读历史快照：只补齐缺失文件/目录，已有计划、当前证据和库均保留，
不执行归档脚本、不写归档。可用`--archive /绝对路径/private`明确选择另一份归档。
`capture`恢复有界测试所需冻结包/库/基线及已有状态，`patch`只恢复原始HOS模块输入。
恢复后应运行`verify`；当前较新的本地日志与阶段优先于旧快照。

准备完成后可用`experiment.py test`调用受版本控制的`tools/workflows/capture_native_serial.py`。
该入口以及采集脚本自身均检查`native_guard_serial_prepared`和最多16次；失败阶段会在USB
操作前停止。现有停止机制、raw保存、native逐包校验、完成URB不取消和禁止失败重投规则保留。
当前最新计划指向该受版本控制的入口，旧private脚本作为冻结历史文件保留。

## 构建与测试

Makefile增加可选`OUTPUT_DIR`，并支持嵌套`BUILD`目录。实验打包器自动把设备对象与输出
放在`private/builds/sysmodules/`，不再向仓库根目录生成exefs-iso-*。例如：

```sh
make -j4 TARGET=exefs-check \
  BUILD=research/usb-ds-iso/private/builds/check/objects \
  OUTPUT_DIR=research/usb-ds-iso/private/builds/check/outputs
python3 -m unittest discover -s research/usb-ds-iso/tests -p test_workflow_paths.py -v
```

补丁构建读取`patches/`，打包器从`docs/`复制配套说明；交付包内原有说明文件名不变。
先前目录整理验证：4项流程测试、全库Markdown本地链接校验、实际嵌套目录设备构建，以及
A23的680字节注入和IPS重建逐字节匹配冻结包。未改写卡文件或执行额外USB实验。

## 文档与冻结证据的关系

[STATUS.md](STATUS.md)维护最新已核验事实，[TEST_PLAN.md](TEST_PLAN.md)维护推进条件。
专题说明维护对应版本的技术设计和最终结果；[RESULTS.md](RESULTS.md)保留按日期的原始观察，
其中旧“待读卡”由后续核验记录解除，旧采集计划不自动成为当前操作指令。
截至2026-10-09，原串行失败3365byte日志保留；最新单次burst2630byte完整日志核验通过。
新同backend串行22:34执行4轮、第4轮失败后停止，待读卡，见[MATCHED_SERIAL_VALIDATION.md](MATCHED_SERIAL_VALIDATION.md)。

本次文档整理仅修改可维护的Markdown；不更新冻结包中的INSTALL/README、manifest、
SHA256SUMS、原始日志或历史脚本。包中“未实机”记录构建时状态，后续run/collection决定实际结果。
`analyze_native_serial_run.py`的CLI会覆盖run中的`serial-evidence.json`；冻结证据的只读复核
应调用其`analyze()`并单独输出结果，不改写已校验文件。
