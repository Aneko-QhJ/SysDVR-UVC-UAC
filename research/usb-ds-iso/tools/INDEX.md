# 工具索引

> 自动生成，勿手改。重生成：`python3 research/usb-ds-iso/tools/index_tools.py`。
> 使用约定见 [../WORKFLOW.md](../WORKFLOW.md)；分类说明见 [README.md](README.md)。

共 427 个 Python 工具。

## 当前使用

| 工具 | 用途 |
| --- | --- |
| [build_a23_short24_path_span_candidate.py](build_a23_short24_path_span_candidate.py) | Offline short24 rebuild retaining the previously reviewed FS path capacity fix. |
| [audit_a23_short24_path_span.py](audit_a23_short24_path_span.py) | CPU-only regression checks for short24 filesystem path input capacity. |
| [build_a23_short24_candidate.py](build_a23_short24_candidate.py) | Build an isolated fixed16/24-byte ARM candidate; no deployment or receiver. |
| [audit_a23_short24_entry.py](audit_a23_short24_entry.py) | Exercise the entry's file-only modes and injected runtime persistence. |
| [build_a23_short24_entry.py](build_a23_short24_entry.py) | Verify/seal the prepared package and compile a dormant single-use entry. |
| [package_a23_short24.py](package_a23_short24.py) | Package the frozen short24 ELF/IPS against the last recovered card, file-only. |
| [analyze_a23_short24_session.py](analyze_a23_short24_session.py) | Relate supplied short24 host bytes to EXE3/OWN2; no provenance inference. |
| [audit_a23_short24_sdk.py](audit_a23_short24_sdk.py) | Compile the SDK capability; execute injected native I/O and C wire fixtures. |
| [analyze_a23_audio_cadence.py](analyze_a23_audio_cadence.py) | Read-only Q1 cadence analysis. No SDK, device, acquisition or ticket imports. |

## 分组

| 前缀 | 数量 |
| --- | --- |
| `audit` | 137 |
| `a23_*` | 110 |
| `analyze` | 59 |
| `build` | 58 |
| `collect` | 18 |
| `prepare` | 10 |
| `context65` | 7 |
| `io` | 6 |
| `model` | 4 |
| `lifecycle` | 2 |
| `package` | 2 |
| `sequence` | 2 |
| `summarize` | 2 |
| `decode` | 1 |
| `experiment.py` | 1 |
| `extract` | 1 |
| `gen` | 1 |
| `inspect` | 1 |
| `nso2elf.py` | 1 |
| `path` | 1 |
| `probe` | 1 |
| `research` | 1 |
| `validate` | 1 |

## a23_*（110）

| 工具 | 说明 |
| --- | --- |
| [a23_archive_read_view.py](a23_archive_read_view.py) | One-call archive byte reuse; isolated derivation, no acquisition entry. |
| [a23_bootstrap_archive.py](a23_bootstrap_archive.py) | Read-only bootstrap evidence, including absent or malformed legacy journals. |
| [a23_bootstrap_capture.py](a23_bootstrap_capture.py) | Descriptor-anchored, bounded reads of source marker and bootstrap journal. |
| [a23_bootstrap_worker.py](a23_bootstrap_worker.py) | Test-only interruption injection around the frozen journal bootstrap writes. |
| [a23_broker_archive.py](a23_broker_archive.py) | Read-only joined model envelope. Checks both actual and injected contexts. |
| [a23_broker_model.py](a23_broker_model.py) | One model child: observed hello -> guarded model consumption -> final files. |
| [a23_broker_supervision.py](a23_broker_supervision.py) | Separate fixed hello/execution deadlines for the fake-SDK model broker. |
| [a23_cached_build_relations.py](a23_cached_build_relations.py) | Pure structural build and journal-reference checks on pinned model bytes. |
| [a23_cached_clock_domains.py](a23_cached_clock_domains.py) | Typed, separate clock domains and model-only timing arithmetic over caches. |
| [a23_cached_collection_links.py](a23_cached_collection_links.py) | Pure joins of historical admission, verifier declarations and static collection. |
| [a23_cached_journal_epochs.py](a23_cached_journal_epochs.py) | Pure journal seals and two-epoch packet checks over caller-pinned bytes. |
| [a23_cached_outer_forensics.py](a23_cached_outer_forensics.py) | Complete the 96-member byte scope and join saved bootstrap declarations. |
| [a23_cached_permit_context.py](a23_cached_permit_context.py) | Cached simulated issuance, native permit and actual/injected context links. |
| [a23_cached_session_links.py](a23_cached_session_links.py) | Pure entry/driver/receipt/session byte relations; no clock-domain attestation. |
| [a23_capture_window.py](a23_capture_window.py) | Record a first model capture plus two descriptor-based reobservations. |
| [a23_capture_window_archive.py](a23_capture_window_archive.py) | Read-only repeated-observation model evidence; no atomic/current-source claim. |
| [a23_checked_export.py](a23_checked_export.py) | Pinned, model-only checked export and its pure archive consumer. |
| [a23_child_signal_bootstrap.py](a23_child_signal_bootstrap.py) | Offline signal-policy bootstrap. Restore before importing the frozen sampler. |
| [a23_child_signal_owner.py](a23_child_signal_owner.py) | Offline ready-gated restoration of the child's original thread signal mask. |
| [a23_collection_journal.py](a23_collection_journal.py) | One-attempt, file-only collection journal around frozen fake SDK evidence. |
| [a23_collection_journal_archive.py](a23_collection_journal_archive.py) | Read-only partial journal inspection and separately sealed forensic copies. |
| [a23_collection_worker.py](a23_collection_worker.py) | Isolated Python invocation for explicit file-only collection fault models. |
| [a23_commit_concurrency_model.py](a23_commit_concurrency_model.py) | Add deterministic threaded model schedules without changing driver/bridge/C. |
| [a23_completion_status_view.py](a23_completion_status_view.py) | Read-only OFFLINE presentation of a historical cut and optional later model observation. |
| [a23_concurrent_diagnostics.py](a23_concurrent_diagnostics.py) | Pure byte-cache diagnostics for declared offline cases; no filesystem calls. |
| [a23_context65_binding.py](a23_context65_binding.py) | Independent sequence65/context candidate; old49 build and issuers frozen. |
| [a23_context65_history.py](a23_context65_history.py) | Read-only local history scope, including the burned49 block and failed run. |
| [a23_device_binding.py](a23_device_binding.py) | Separate parent, window recipe and final ELF identities; file-only checks. |
| [a23_driver_fault_model.py](a23_driver_fault_model.py) | Derive a new fault fixture while retaining the frozen driver/link scope. |
| [a23_driver_worker_failure_model.py](a23_driver_worker_failure_model.py) | Integrate specified worker failures through fixture hooks; driver unchanged. |
| [a23_driver_worker_materials.py](a23_driver_worker_materials.py) | Pure cached-byte admission for fifteen specified driver/worker schedules. |
| [a23_execution_context.py](a23_execution_context.py) | Validate supplied context bytes. Agreement never proves process provenance. |
| [a23_failure_archive.py](a23_failure_archive.py) | Read-only complete/incomplete model archives, including absent child reports. |
| [a23_failure_collector.py](a23_failure_collector.py) | Collect already sealed model supervision and bounded raw execution files. |
| [a23_final_archive.py](a23_final_archive.py) | Bounded, file-only final archives; no live roots, receiver launch or issuance. |
| [a23_fixture_job_binding.py](a23_fixture_job_binding.py) | Pure fixture job/launch/receipt correlation. No permit or live provenance. |
| [a23_fixture_job_launcher.py](a23_fixture_job_launcher.py) | One-shot bounded launcher for the fixed Python fixture, never a receiver. |
| [a23_fixture_publication.py](a23_fixture_publication.py) | Filesystem publication candidate for disposable fixtures; never a launcher. |
| [a23_fixture_recovery.py](a23_fixture_recovery.py) | Pure interpretation of interrupted fixture publication; never authorizes reuse. |
| [a23_grouped_build_bytes.py](a23_grouped_build_bytes.py) | Offline build byte groups, externally pinned and consumed without file IO. |
| [a23_guard_cadence_revision.py](a23_guard_cadence_revision.py) | Derive a model-only explicit-check candidate from the sealed live75 build. |
| [a23_guarded_broker_model.py](a23_guarded_broker_model.py) | Model-only prelaunch source guard and post-exit file collection adapter. |
| [a23_guardian_failure_materials.py](a23_guardian_failure_materials.py) | Pure guardian failure evidence: exit notes never stand in for missing wait. |
| [a23_guardian_owned_materials.py](a23_guardian_owned_materials.py) | Pure guardian-owned worker handoff/wait comparison; never production authority. |
| [a23_integrated_fixture_io.py](a23_integrated_fixture_io.py) | Split the frozen fixture publication protocol across parent and child. |
| [a23_integrated_fixture_launcher.py](a23_integrated_fixture_launcher.py) | Bounded fixture-only launcher with synchronized prelaunch publication. |
| [a23_integrated_fixture_materials.py](a23_integrated_fixture_materials.py) | Pure synchronized-launch/result/cleanup admission for disposable fixtures. |
| [a23_interest_trace_candidate.py](a23_interest_trace_candidate.py) | Keep every interest fatal; record provider ingress in an isolated derivative. |
| [a23_isolated_driver_model.py](a23_isolated_driver_model.py) | Derive a finite model-only link scope from pinned, frozen sources. |
| [a23_lead32_binding.py](a23_lead32_binding.py) | New host-only plan and receipt; the six path-span device materials stay identical. |
| [a23_lifecycle_capsule.py](a23_lifecycle_capsule.py) | Decode an LCP1 prototype prefix. CRC/ordering are not physical provenance. |
| [a23_lifecycle_device_binding.py](a23_lifecycle_device_binding.py) | Bind the sealed lifecycle candidate's six files, including NPDM. File-only. |
| [a23_live103_interest_workflow.py](a23_live103_interest_workflow.py) | Strict success/failure trace consumers and new explicitly authorized workflow. |
| [a23_live109_short128_workflow.py](a23_live109_short128_workflow.py) | Strict success/failure trace consumers and new explicitly authorized workflow. |
| [a23_live112_short128_workflow.py](a23_live112_short128_workflow.py) | Strict success/failure trace consumers and new explicitly authorized workflow. |
| [a23_live120_lstat_workflow.py](a23_live120_lstat_workflow.py) | Strict success/failure trace consumers and new explicitly authorized workflow. |
| [a23_live126_interepoch_workflow.py](a23_live126_interepoch_workflow.py) | Dedicated fresh126 consumer/workflow; old workflow code remains immutable. |
| [a23_live132_completion_consumer.py](a23_live132_completion_consumer.py) | Require a bound completion fact in addition to all earlier offline checks. |
| [a23_live132_q1_consumer.py](a23_live132_q1_consumer.py) | Q1 dual-mode supplied-evidence consumer; modes never authenticate hardware origin. |
| [a23_live132_q1_workflow.py](a23_live132_q1_workflow.py) | Q1 workflow facade. Software capability never substitutes for new human authorization. |
| [a23_live132_terminal_consumer.py](a23_live132_terminal_consumer.py) | Bound offline receiver evidence: original SDK/export checks plus service ticks. |
| [a23_live75_two_epoch_workflow.py](a23_live75_two_epoch_workflow.py) | Fixed saved75 successor workflow. Preview never reserves or acquires USB. |
| [a23_live91_checked_workflow.py](a23_live91_checked_workflow.py) | Frozen current91 workflow and checked exporter; explicit authorization only. |
| [a23_live97_three_workflow.py](a23_live97_three_workflow.py) | Source-bound three-round workflow. Explicit new authorization precedes issue. |
| [a23_live_two_epoch_workflow.py](a23_live_two_epoch_workflow.py) | Dedicated two-epoch preview, explicitly authorized issue, capture and collection. |
| [a23_model_supervisor.py](a23_model_supervisor.py) | Bounded context-only model child supervision; no signal, acquisition or retry. |
| [a23_parent_crash_materials.py](a23_parent_crash_materials.py) | Pure parent-interruption evidence checks; exit observation is not orphan wait. |
| [a23_path_span_device_binding.py](a23_path_span_device_binding.py) | Bind the sealed path-span candidate's six files, including NPDM. File-only. |
| [a23_pinned_semantics.py](a23_pinned_semantics.py) | Pure, partial semantic inspection of six caller-pinned model byte strings. |
| [a23_pinned_view.py](a23_pinned_view.py) | Materialize separate byte copies; consumers cache verified immutable bytes. |
| [a23_pinned_view_archive.py](a23_pinned_view_archive.py) | Strict file-only byte-contract views; validated bytes returned from one read. |
| [a23_preretained_owner.py](a23_preretained_owner.py) | Offline pre-retained Popen prototype, pinned to inspected CPython semantics. |
| [a23_q2_epoch_lease_model.py](a23_q2_epoch_lease_model.py) | One-segment symbolic epoch credit lease. No SDK, backing, clock or I/O. |
| [a23_q2_generation_model.py](a23_q2_generation_model.py) | Finite symbolic Q2b model. No backing allocation, SDK, I/O, or permits. |
| [a23_quiet_device_binding.py](a23_quiet_device_binding.py) | Bind the sealed quiet candidate's six files, including NPDM. File-only. |
| [a23_quiet_driver_copy.py](a23_quiet_driver_copy.py) | Pinned transformations for an isolated, injected-clock-only driver copy. |
| [a23_sequence32_model.py](a23_sequence32_model.py) | Disposable file-only 32-sequence reservation model. No production writer/runner. |
| [a23_sequence_binding.py](a23_sequence_binding.py) | Isolated host candidate: fixed history-scoped sequence, unchanged device bytes. |
| [a23_sequence_history.py](a23_sequence_history.py) | Saved A23 history inventory and a temporary-only durable reservation model. |
| [a23_sequence_witness_model.py](a23_sequence_witness_model.py) | Offline sequence witness model. No reservation, firmware, card or USB access. |
| [a23_shared_sequence32.py](a23_shared_sequence32.py) | Shared32 namespace engine. Dormant formal branch; tests use temporary namespaces. |
| [a23_shared_sequence32_scope.py](a23_shared_sequence32_scope.py) | Live read-only scope for the dormant shared issuer and native permit. |
| [a23_sigint_guard_owner.py](a23_sigint_guard_owner.py) | Offline main-thread SIGINT deferral around the pinned pre-retained constructor. |
| [a23_spawn_boundary_owner.py](a23_spawn_boundary_owner.py) | Isolated repair for retained child with an interrupted stream-list assignment. |
| [a23_status_capture_revision.py](a23_status_capture_revision.py) | Derive an isolated STATUS fix; never mutate a frozen source or issue a job. |
| [a23_status_transport_materials.py](a23_status_transport_materials.py) | Pure status transport candidate evidence; local failure never proves wait. |
| [a23_supervisor_archive.py](a23_supervisor_archive.py) | Read-only model supervisor evidence; no executable launch or live roots. |
| [a23_supervisor_candidate.py](a23_supervisor_candidate.py) | Bounded, one-shot supervisor for the pinned offline Python fixture only. |
| [a23_supervisor_cleanup.py](a23_supervisor_cleanup.py) | One-shot cleanup candidate for the fixed offline pipe/exit fixture. |
| [a23_supervisor_cleanup_materials.py](a23_supervisor_cleanup_materials.py) | Pure cached cleanup dispositions. No process or filesystem operations. |
| [a23_supervisor_job_link.py](a23_supervisor_job_link.py) | Read-only declared cross-model job/SDK correspondence; never a permit. |
| [a23_supervisor_job_plan.py](a23_supervisor_job_plan.py) | Pinned static integration evidence and an unapplied read-only adapter diff. |
| [a23_supervisor_materials.py](a23_supervisor_materials.py) | Pure byte admission of observed fixture exits and pinned model materials. |
| [a23_supervisor_unified.py](a23_supervisor_unified.py) | Single bounded supervisor candidate; pinned offline fixture, no production API. |
| [a23_supervisor_unified_materials.py](a23_supervisor_unified_materials.py) | One pure byte admission policy for unified offline supervisor observations. |
| [a23_terminal_commit_io.py](a23_terminal_commit_io.py) | Exclusive local publication with a final manifest; no process supervision. |
| [a23_terminal_commit_materials.py](a23_terminal_commit_materials.py) | Pure commit visibility and observed sync checks; neither proves process wait. |
| [a23_terminal_deadline.py](a23_terminal_deadline.py) | Offline sampler supervision. Own the child handle; never infer old actors' wait. |
| [a23_terminal_deadline_worker.py](a23_terminal_deadline_worker.py) | Single offline sampling child. Read one bounded request; write one bounded response. |
| [a23_terminal_intake.py](a23_terminal_intake.py) | Offline /private/tmp directory sampler. Equal observations are not an atomic snapshot. |
| [a23_terminal_observation_consumer.py](a23_terminal_observation_consumer.py) | Independently recompute a bound OFFLINE terminal-service record. |
| [a23_terminal_owner.py](a23_terminal_owner.py) | Offline caller-owned sampler. Runtime object transfer is not PID recovery. |
| [a23_terminal_publication_materials.py](a23_terminal_publication_materials.py) | Pure interrupted local publication evidence; full local exit files are not wait. |
| [a23_terminal_recovery_materials.py](a23_terminal_recovery_materials.py) | Disk-byte-only local terminal classification; no lifecycle history is inferred. |
| [a23_three_epoch_candidate.py](a23_three_epoch_candidate.py) | Isolated fixed-three derivations. No issuer, live CLI or hardware launch. |
| [a23_two_epoch_baseline69.py](a23_two_epoch_baseline69.py) | Read-only adoption of the exact saved69 recovery; no card or issuance writer. |
| [a23_two_epoch_sdk_source.py](a23_two_epoch_sdk_source.py) | Pure reviewed derivation of a DISTINCT SDK driver from frozen offline core. |
| [a23_verified_scope.py](a23_verified_scope.py) | Read-only authority inputs for an embedded native verifier; no issuance. |
| [a23_versioned_driver_model.py](a23_versioned_driver_model.py) | Isolated versioned driver derivation; original production sources stay pinned. |
| [a23_worker_failure_materials.py](a23_worker_failure_materials.py) | Pure byte admission for the specified offline worker fixtures, not provenance. |

## analyze（59）

| 工具 | 说明 |
| --- | --- |
| [analyze_a23_argument_cache.py](analyze_a23_argument_cache.py) | Exact argument-fetch instruction profiles; parser entry state is injected. |
| [analyze_a23_audio_cadence.py](analyze_a23_audio_cadence.py) | Read-only Q1 cadence analysis. No SDK, device, acquisition or ticket imports. |
| [analyze_a23_context65_entry.py](analyze_a23_context65_entry.py) | Validate supplied waiting/SDK file ordering. Never authenticates a device run. |
| [analyze_a23_elf_boundaries.py](analyze_a23_elf_boundaries.py) | ELF symbol ranges and explicit SDK no-return contracts; never assume thread safety. |
| [analyze_a23_format_loop.py](analyze_a23_format_loop.py) | Actual narrow/integer formatter instruction loop; no graph pruning or device. |
| [analyze_a23_formatter.py](analyze_a23_formatter.py) | Guarded formatter dispatch and conditional default-locale pointer evidence. |
| [analyze_a23_integrated_memory.py](analyze_a23_integrated_memory.py) | Continuous formatter plus actual SDK memory-helper instructions in an offline model. |
| [analyze_a23_iso_retention.py](analyze_a23_iso_retention.py) | Offline ISO7 error/host-window comparison. No device access or authorization. |
| [analyze_a23_lead32_entry.py](analyze_a23_lead32_entry.py) | Validate supplied waiting/SDK file ordering. Never authenticates a device run. |
| [analyze_a23_linked_logs.py](analyze_a23_linked_logs.py) | Literal reaching definitions and bounded string-FILE instruction replay. |
| [analyze_a23_literal_scan.py](analyze_a23_literal_scan.py) | Replay wrapper initialization, TLS/default locale and ASCII scan to first fetch. |
| [analyze_a23_log_contract.py](analyze_a23_log_contract.py) | Narrow literal printf inventory and final-ELF snprintf buffer contract. |
| [analyze_a23_native_errors.py](analyze_a23_native_errors.py) | Compare five frozen A23 runs without modifying evidence or accessing USB. |
| [analyze_a23_paired_resources.py](analyze_a23_paired_resources.py) | Offline paired-resource AND epoch archive check. Never grants SDK permission. |
| [analyze_a23_parser_bridge.py](analyze_a23_parser_bridge.py) | Bound conversion-reset/dispatch/fetch replay; literal scanning is not executed. |
| [analyze_a23_sdk_memory.py](analyze_a23_sdk_memory.py) | Replay bound SDK memory helpers and record their exact memory accesses. |
| [analyze_a23_sequence32.py](analyze_a23_sequence32.py) | Read-only analysis of copied disposable32 model evidence; no authority granted. |
| [analyze_a23_sequence_entry.py](analyze_a23_sequence_entry.py) | Validate supplied waiting/SDK file ordering. Never authenticates a device run. |
| [analyze_a23_session_stack.py](analyze_a23_session_stack.py) | Conservative final-ELF SP/call audit; unresolved edges never yield a bound. |
| [analyze_a23_shared_sequence32.py](analyze_a23_shared_sequence32.py) | Read-only shared32/native-permit model chain verification. |
| [analyze_a23_short24.py](analyze_a23_short24.py) | Narrow file-only short24 payload/STATUS consumer, not a strict USB verdict. |
| [analyze_a23_short24_session.py](analyze_a23_short24_session.py) | Relate supplied short24 host bytes to EXE3/OWN2; no provenance inference. |
| [analyze_a23_two_epoch.py](analyze_a23_two_epoch.py) | Standalone offline two-epoch archive verification; integrity is not provenance. |
| [analyze_a23_two_epoch_entry.py](analyze_a23_two_epoch_entry.py) | Verify supplied SDK entry, context, wait/claim order and final checkpoint. |
| [analyze_a23_two_epoch_final.py](analyze_a23_two_epoch_final.py) | Read-only final model archive checks. No executable is run and no live root is consulted. |
| [analyze_a23_two_epoch_sdk.py](analyze_a23_two_epoch_sdk.py) | Standalone supplied SDK two-epoch verification; source labels are not provenance. |
| [analyze_a23_v2_association.py](analyze_a23_v2_association.py) | Offline comparison of supplied host and V2 files; never authenticates a run. |
| [analyze_a23_waiting_entry.py](analyze_a23_waiting_entry.py) | Validate supplied waiting/SDK file ordering. Never authenticates a device run. |
| [analyze_burst_window.py](analyze_burst_window.py) | Read-only strict single-burst classifier; serial and stability stay false. |
| [analyze_clock_audit.py](analyze_clock_audit.py) | Read-only one-burst clock audit; estimates have 1 ms API uncertainty. |
| [analyze_ep0_candidate_capture.py](analyze_ep0_candidate_capture.py) | Decode a simulation-only ownership snapshot + inner EP0 trace envelope. |
| [analyze_ep0_candidate_capture_v2.py](analyze_ep0_candidate_capture_v2.py) | Decode a simulation-only ownership snapshot + inner EP0 trace envelope. |
| [analyze_ep0_diagnostic.py](analyze_ep0_diagnostic.py) | Independent simulation-only diagnostic decoder; never accepts safe ownership. |
| [analyze_ep0_diagnostic_v2.py](analyze_ep0_diagnostic_v2.py) | Independent simulation-only diagnostic decoder; never accepts safe ownership. |
| [analyze_ep0_execution_v3.py](analyze_ep0_execution_v3.py) | Decode an independent EXE3 envelope; local correlation is not provenance. |
| [analyze_ep0_session.py](analyze_ep0_session.py) | Decode startup/EP0 local correlation; no ownership or origin authentication. |
| [analyze_ep0_session_v2.py](analyze_ep0_session_v2.py) | Decode startup/EP0 local correlation; no ownership or origin authentication. |
| [analyze_ep0_startup.py](analyze_ep0_startup.py) | Independent EP0INI1 CPU startup journal decoder; never authenticates ownership. |
| [analyze_ep0_trace.py](analyze_ep0_trace.py) | Decode the bounded EP0 trace prototype; simulation never authenticates capture. |
| [analyze_ep0_trace_v2.py](analyze_ep0_trace_v2.py) | Decode the bounded EP0 trace prototype; simulation never authenticates capture. |
| [analyze_io_usb_host_burst_collection.py](analyze_io_usb_host_burst_collection.py) | Freeze/audit injected burst artifacts and synthetic A23 logs offline only. |
| [analyze_io_usb_host_burst_executor.py](analyze_io_usb_host_burst_executor.py) | Independently bind injected burst journals to saved bytes. Simulation only. |
| [analyze_io_usb_host_burst_sdk.py](analyze_io_usb_host_burst_sdk.py) | Offline SDK burst host binding audit. Integrity is not hardware provenance. |
| [analyze_io_usb_host_burst_sdk_collection.py](analyze_io_usb_host_burst_sdk_collection.py) | Freeze/audit supplied SDK burst artifacts offline; no acquisition or approval. |
| [analyze_io_usb_host_collection.py](analyze_io_usb_host_collection.py) | Freeze/audit completed mock sessions with original reply bytes. No USB entry. |
| [analyze_io_usb_host_context65.py](analyze_io_usb_host_context65.py) | Offline SDK burst host binding audit. Integrity is not hardware provenance. |
| [analyze_io_usb_host_context65_evidence.py](analyze_io_usb_host_context65_evidence.py) | Independent, offline, simulation-only transaction bundle validator. |
| [analyze_io_usb_host_evidence.py](analyze_io_usb_host_evidence.py) | Independent, offline, simulation-only transaction bundle validator. |
| [analyze_io_usb_host_hardware.py](analyze_io_usb_host_hardware.py) | Read-only audits of SDK-origin no-TD observations; no native policy approval. |
| [analyze_io_usb_host_lead32.py](analyze_io_usb_host_lead32.py) | Offline SDK burst host binding audit. Integrity is not hardware provenance. |
| [analyze_io_usb_host_no_td.py](analyze_io_usb_host_no_td.py) | Audit no-TD observations in their declared log format; native policy stays unverified. |
| [analyze_io_usb_host_sequence.py](analyze_io_usb_host_sequence.py) | Offline SDK burst host binding audit. Integrity is not hardware provenance. |
| [analyze_io_usb_host_sequence_evidence.py](analyze_io_usb_host_sequence_evidence.py) | Independent, offline, simulation-only transaction bundle validator. |
| [analyze_io_usb_host_session.py](analyze_io_usb_host_session.py) | Offline simulation session journal audit; no callback-drain or USB claim. |
| [analyze_io_usb_host_timestamps.py](analyze_io_usb_host_timestamps.py) | Measure saved AbsoluteTime observations; never approves a native or bus policy. |
| [analyze_matched_serial_run.py](analyze_matched_serial_run.py) | Read-only matched serial analysis; full device log remains a separate gate. |
| [analyze_native_serial_run.py](analyze_native_serial_run.py) | Independently check saved serial native/raw/device evidence; never access USB. |
| [analyze_no_td_window.py](analyze_no_td_window.py) | Classify saved no-TD evidence without writing inputs or accessing USB. |
| [analyze_serial_clock.py](analyze_serial_clock.py) | Read-only bounded serial clock audit; frame estimates retain 1 ms uncertainty. |

## audit（137）

| 工具 | 说明 |
| --- | --- |
| [audit_a23_archive_read_view.py](audit_a23_archive_read_view.py) | Bounded file-only native audit for one-call archive read reuse. |
| [audit_a23_argument_cache.py](audit_a23_argument_cache.py) | Read-only parser/cache profiles against sealed final ELFs; no device. |
| [audit_a23_bootstrap_capture.py](audit_a23_bootstrap_capture.py) | Legacy bootstrap interruption plus descriptor replacement models; no hardware. |
| [audit_a23_bound_receiver.py](audit_a23_bound_receiver.py) | Build and test bound identities using new mock records and file-only claims. |
| [audit_a23_broker_model.py](audit_a23_broker_model.py) | End-to-end supervised fake SDK models; actual sandbox rejection retained. |
| [audit_a23_cached_build_relations.py](audit_a23_cached_build_relations.py) | Offline structural build-link subset, with rehashed semantic counterexamples. |
| [audit_a23_cached_clock_domains.py](audit_a23_cached_clock_domains.py) | Offline clock-domain profiles, timing boundaries and coherent file models. |
| [audit_a23_cached_collection_links.py](audit_a23_cached_collection_links.py) | Offline cached admission/verifier/static-collection semantic counterexamples. |
| [audit_a23_cached_journal_epochs.py](audit_a23_cached_journal_epochs.py) | Offline exact material scope, cached journal/epoch checks and counterexamples. |
| [audit_a23_cached_outer_forensics.py](audit_a23_cached_outer_forensics.py) | Offline full-manifest byte coverage and bootstrap declaration counterexamples. |
| [audit_a23_cached_permit_context.py](audit_a23_cached_permit_context.py) | Rehashed cached permit/context models, including coherent PID/context splices. |
| [audit_a23_cached_session_links.py](audit_a23_cached_session_links.py) | Offline cached entry-to-session linkage and reproducible semantic failures. |
| [audit_a23_capture_window.py](audit_a23_capture_window.py) | Late component mutation and residual final-observation boundary models. |
| [audit_a23_checked_export.py](audit_a23_checked_export.py) | Bounded fake-SDK controller and checked-export consumer audit. |
| [audit_a23_child_signal.py](audit_a23_child_signal.py) | Offline child mask/handler restoration and ready-gated termination fixtures. |
| [audit_a23_clock_candidate.py](audit_a23_clock_candidate.py) | Build isolated C clock arithmetic and compare it with a Fraction oracle. |
| [audit_a23_collection_journal.py](audit_a23_collection_journal.py) | Process interruption and unsafe-input audits; frozen SDK binaries are data only. |
| [audit_a23_commit_concurrency_model.py](audit_a23_commit_concurrency_model.py) | Replay specified commit/publisher/callback schedules and cached diagnostics. |
| [audit_a23_context65_baseline63.py](audit_a23_context65_baseline63.py) | Exercise injected owned invocations and static collections; never issue formally. |
| [audit_a23_context65_flag_card.py](audit_a23_context65_flag_card.py) | Freeze two-stage card adapter models using fake command transport only. |
| [audit_a23_context65_flag_repair.py](audit_a23_context65_flag_repair.py) | Seal disposable flag-repair success/failure models. No physical-card API. |
| [audit_a23_context65_receiver.py](audit_a23_context65_receiver.py) | Build bound sequence candidate; injected SDK, serializers and file claims only. |
| [audit_a23_context65_workflow.py](audit_a23_context65_workflow.py) | Exercise injected owned invocations and static collections; never issue formally. |
| [audit_a23_control_buffers.py](audit_a23_control_buffers.py) | Offline actual-source review of control buffer reuse and cleanup paths. |
| [audit_a23_diagnostic_readiness.py](audit_a23_diagnostic_readiness.py) | Bind the latest frozen EP0 candidate and replay prelude/diagnostic boundaries. |
| [audit_a23_driver_fault_model.py](audit_a23_driver_fault_model.py) | Replay complete-driver callback/deadline faults and non-atomic profile reads. |
| [audit_a23_driver_worker_failure_model.py](audit_a23_driver_worker_failure_model.py) | Full isolated driver schedules for specified worker failures and collection. |
| [audit_a23_elf_boundaries.py](audit_a23_elf_boundaries.py) | Read-only ELF symbol/abort review against sealed A23 candidates, no new builds. |
| [audit_a23_ep0.py](audit_a23_ep0.py) | Read saved A23 failure evidence and probe its actual EP0 source with stubs. |
| [audit_a23_execution_readiness.py](audit_a23_execution_readiness.py) | Replay the sealed V2 video loop with simulated services; offline planning only. |
| [audit_a23_failure_model.py](audit_a23_failure_model.py) | Native abrupt-exit fixtures and file-only failure archive fault injection. |
| [audit_a23_fixture_job_binding.py](audit_a23_fixture_job_binding.py) | Offline one-shot fixture launch binding; check mode never launches a process. |
| [audit_a23_fixture_publication.py](audit_a23_fixture_publication.py) | Audit interrupted file publication in fixed offline fixture processes. |
| [audit_a23_format_loop.py](audit_a23_format_loop.py) | Current linked format loops vs typed native snprintf; all work is offline. |
| [audit_a23_formatter.py](audit_a23_formatter.py) | Formatter switch/locale frontier review; offline only, sealed candidates unchanged. |
| [audit_a23_fs_path_span.py](audit_a23_fs_path_span.py) | Offline fixed-width path audit and guarded native prototype. No device access. |
| [audit_a23_grouped_build_bytes.py](audit_a23_grouped_build_bytes.py) | Capture historical build bytes for an offline grouped-cache review. |
| [audit_a23_guard_cadence.py](audit_a23_guard_cadence.py) | Offline native comparison; every SDK, clock and namespace is a test double. |
| [audit_a23_guard_session.py](audit_a23_guard_session.py) | Replay sealed guarded VideoStreamThread and serialize offline diagnostics only. |
| [audit_a23_guardian_failure.py](audit_a23_guardian_failure.py) | Offline guardian interruption with a direct-owner witness and read-only exit watches. |
| [audit_a23_guardian_owned.py](audit_a23_guardian_owned.py) | Disposable guardian-owned worker comparison; no production broker entry. |
| [audit_a23_hos_setup.py](audit_a23_hos_setup.py) | Bind HOS shared EP0 setup paths to saved A23 and replay scheduling hypotheses. |
| [audit_a23_host_execution_link.py](audit_a23_host_execution_link.py) | Audit a dormant IOKit adapter and supplied EXE3 collections, offline only. |
| [audit_a23_integrated_fixture.py](audit_a23_integrated_fixture.py) | Offline synchronized fixture launcher, publication and cleanup combinations. |
| [audit_a23_integrated_memory.py](audit_a23_integrated_memory.py) | Rebind new linked ELFs and replay formatter/SDK helpers together; no device access. |
| [audit_a23_interest_trace.py](audit_a23_interest_trace.py) | Eight bounded ingress tests, same poison policy, injected operations only. |
| [audit_a23_isolated_driver_model.py](audit_a23_isolated_driver_model.py) | Build and replay a numeric-clock driver with trimmed model-only providers. |
| [audit_a23_lead32_receiver.py](audit_a23_lead32_receiver.py) | Build host lead32 and run injected files/loops only; no acquisition or issuer. |
| [audit_a23_lead32_workflow.py](audit_a23_lead32_workflow.py) | Exercise copied static files and file-only claims. No issuer or acquisition. |
| [audit_a23_lifecycle_capsule.py](audit_a23_lifecycle_capsule.py) | Offline lifecycle capsule prototype and insertion review. Not a device build. |
| [audit_a23_lifecycle_preparation.py](audit_a23_lifecycle_preparation.py) | Freeze offline package/workflow preparation, not a deployment or invocation. |
| [audit_a23_lifecycle_receiver.py](audit_a23_lifecycle_receiver.py) | Build a distinct receiver and exercise static lifecycle collections; no acquire. |
| [audit_a23_linked_logs.py](audit_a23_linked_logs.py) | Rebind new ELF literals/FILE/dispatch/locale; instruction profiles, no device. |
| [audit_a23_literal_scan.py](audit_a23_literal_scan.py) | Offline default-locale ASCII scan/init evidence against sealed final ELFs. |
| [audit_a23_live103_interest.py](audit_a23_live103_interest.py) | Bounded fresh103 wiring checks; only temporary namespaces and injected SDK. |
| [audit_a23_live109_short128.py](audit_a23_live109_short128.py) | Fixed128/current109 integration: injected SDK, temporary roots only. |
| [audit_a23_live112_short128.py](audit_a23_live112_short128.py) | Rebind-only native checks; prior fixed128 transport matrix remains sealed. |
| [audit_a23_live120_lstat.py](audit_a23_live120_lstat.py) | Rebind-only native checks; prior fixed128 transport matrix remains sealed. |
| [audit_a23_live126_interepoch.py](audit_a23_live126_interepoch.py) | Bound fresh126 wiring checks; retain earlier transport and handoff matrices. |
| [audit_a23_live132_completion.py](audit_a23_live132_completion.py) | Bound end-of-export repair: focused former counterexamples and pending exit. |
| [audit_a23_live132_q1.py](audit_a23_live132_q1.py) | Q1 preparation checks: real-entry compilation, model execution, mode/authority rejection. |
| [audit_a23_live132_terminal.py](audit_a23_live132_terminal.py) | Focused current132 receiver integration checks; mock SDK operations only. |
| [audit_a23_live75_two_epoch.py](audit_a23_live75_two_epoch.py) | Saved75 live CLI checks and temporary successor namespace/native fixtures. |
| [audit_a23_live91_checked.py](audit_a23_live91_checked.py) | Only current91/145 rebase, checked-export and spent-history wiring checks. |
| [audit_a23_live97_three.py](audit_a23_live97_three.py) | Temporary-root tests of real three-round entry/scope/permit/export wiring. |
| [audit_a23_live_two_epoch.py](audit_a23_live_two_epoch.py) | Compile the live CLI; exercise only file modes and injected two-epoch paths. |
| [audit_a23_log_contract.py](audit_a23_log_contract.py) | Current logger language/length/FILE audit and host-only clamp control. |
| [audit_a23_memory_log_guard.py](audit_a23_memory_log_guard.py) | SDK leaf-helper evidence and isolated GetSize guard; no hardware or production edits. |
| [audit_a23_model_supervisor.py](audit_a23_model_supervisor.py) | Native context helper and bounded supervisor models only; no USB/SD/SDK. |
| [audit_a23_multiburst_admission.py](audit_a23_multiburst_admission.py) | File-only bounded multiburst research; no receiver, firmware, USB or card API. |
| [audit_a23_offline.py](audit_a23_offline.py) | Audit frozen A23 sources and saved transfers without USB or state changes. |
| [audit_a23_paired_sdk.py](audit_a23_paired_sdk.py) | File-only paired SDK capability review, mocked preparation and runtime I/O. |
| [audit_a23_parent_crash.py](audit_a23_parent_crash.py) | Fixed parent crash windows; observe worker exit without claiming orphan wait. |
| [audit_a23_parser_bridge.py](audit_a23_parser_bridge.py) | Audit conversion entry to actual fetch against existing sealed ELFs, offline. |
| [audit_a23_path_span_receiver.py](audit_a23_path_span_receiver.py) | Build a distinct receiver and exercise static lifecycle collections; no acquire. |
| [audit_a23_pinned_semantics.py](audit_a23_pinned_semantics.py) | File-only semantic counterexamples, using historical or explicit model pins. |
| [audit_a23_pinned_view.py](audit_a23_pinned_view.py) | Detached baseline byte views, hard-link policy, cached reads and write exits. |
| [audit_a23_postcompletion_semantics.py](audit_a23_postcompletion_semantics.py) | Post-sample semantics audit and status presentation; frozen receiver, no new candidate. |
| [audit_a23_postexport_boundary.py](audit_a23_postexport_boundary.py) | Audit late-fault cut points in the frozen receiver; no new receiver candidate. |
| [audit_a23_preretained_owner.py](audit_a23_preretained_owner.py) | Pre-retained constructor boundary fixtures; no production process manager. |
| [audit_a23_q2_epoch_lease_model.py](audit_a23_q2_epoch_lease_model.py) | Run the one-segment lease model checks and seal source-bound offline evidence. |
| [audit_a23_q2_evidence_budget.py](audit_a23_q2_evidence_budget.py) | Q2c static budget and handoff audit. No device, SDK or acquisition entry. |
| [audit_a23_q2_generation_model.py](audit_a23_q2_generation_model.py) | Run finite Q2b symbolic checks and seal evidence; never use SDK or hardware. |
| [audit_a23_quiet_driver_copy.py](audit_a23_quiet_driver_copy.py) | Compile-only isolated driver patch and Foundation-only clock bridge replay. |
| [audit_a23_quiet_paths.py](audit_a23_quiet_paths.py) | Fresh quiet-ELF wait/logger/save profiles, never a hardware stack certificate. |
| [audit_a23_quiet_poll_candidate.py](audit_a23_quiet_poll_candidate.py) | Isolated quiet-poll transitions and frozen arrival/poll deadline policy. |
| [audit_a23_quiet_receiver.py](audit_a23_quiet_receiver.py) | Build and test bound identities using new mock records and file-only claims. |
| [audit_a23_rearm.py](audit_a23_rearm.py) | Offline execution of recovered ISO7 patch and injected host owner lifetimes. |
| [audit_a23_scope_verifier.py](audit_a23_scope_verifier.py) | File-only native scope verification and complete injected entry chains. |
| [audit_a23_sequence_receiver.py](audit_a23_sequence_receiver.py) | Build bound sequence candidate; injected SDK, serializers and file claims only. |
| [audit_a23_sequence_witness.py](audit_a23_sequence_witness.py) | Offline replay matrix and sequence-witness feasibility audit. Never acquire. |
| [audit_a23_sequence_workflow.py](audit_a23_sequence_workflow.py) | Exercise copied static files and file-only claims. No issuer or acquisition. |
| [audit_a23_session_concurrency.py](audit_a23_session_concurrency.py) | Publication/interruption tests and final-ELF stack audit; existing runtime unchanged. |
| [audit_a23_shared_sequence32.py](audit_a23_shared_sequence32.py) | Compile file-only native permits and test cross-job shared32 ownership. |
| [audit_a23_short24_candidate.py](audit_a23_short24_candidate.py) | Execute the isolated controller in Unicorn and compare native payload bytes. |
| [audit_a23_short24_entry.py](audit_a23_short24_entry.py) | Exercise the entry's file-only modes and injected runtime persistence. |
| [audit_a23_short24_path_span.py](audit_a23_short24_path_span.py) | CPU-only regression checks for short24 filesystem path input capacity. |
| [audit_a23_short24_sdk.py](audit_a23_short24_sdk.py) | Compile the SDK capability; execute injected native I/O and C wire fixtures. |
| [audit_a23_sigint_guard.py](audit_a23_sigint_guard.py) | Actual native-return/PID-store SIGINT comparison; current CPython only. |
| [audit_a23_spawn_boundary.py](audit_a23_spawn_boundary.py) | Pinned local Python spawn boundary audit and direct-owner topology comparison. |
| [audit_a23_startup.py](audit_a23_startup.py) | Audit actual startup functions with injected service/thread failures, offline only. |
| [audit_a23_status_capture_revision.py](audit_a23_status_capture_revision.py) | Compile an isolated driver revision and run fake SDK + historical byte audits. |
| [audit_a23_status_transport.py](audit_a23_status_transport.py) | Offline explicit status-pipe failure candidate, preserving the guardian-loss baseline. |
| [audit_a23_supervisor_candidate.py](audit_a23_supervisor_candidate.py) | Run a pinned Python-only supervisor against cached driver model materials. |
| [audit_a23_supervisor_cleanup.py](audit_a23_supervisor_cleanup.py) | Replay fixed pipe/exit cleanup schedules without production/native execution. |
| [audit_a23_supervisor_job_link.py](audit_a23_supervisor_job_link.py) | Pure cached job/receipt correspondence and unapplied static read-only adapter. |
| [audit_a23_supervisor_unified.py](audit_a23_supervisor_unified.py) | Audit one supervisor/schema/policy over collection, cleanup and close faults. |
| [audit_a23_terminal_commit.py](audit_a23_terminal_commit.py) | Offline local commit marker and directory-sync protocol; no production entry. |
| [audit_a23_terminal_deadline.py](audit_a23_terminal_deadline.py) | Offline deadline trials and read-only verification of sealed observations. |
| [audit_a23_terminal_intake.py](audit_a23_terminal_intake.py) | Offline read-only directory intake cases; historical byte caches, no process fixtures. |
| [audit_a23_terminal_observation.py](audit_a23_terminal_observation.py) | One offline terminal wiring audit; no receiver build or hardware access. |
| [audit_a23_terminal_owner.py](audit_a23_terminal_owner.py) | Offline caller interruption and retained-handle transfer trials. |
| [audit_a23_terminal_publication.py](audit_a23_terminal_publication.py) | Offline interruption of local terminal publication; no production launcher. |
| [audit_a23_terminal_recovery.py](audit_a23_terminal_recovery.py) | Read-only cached local recovery classification; never starts a fixture. |
| [audit_a23_thread_paths.py](audit_a23_thread_paths.py) | Sealed wait-site profiles and actual capture retry/race checks; offline only. |
| [audit_a23_three_epoch.py](audit_a23_three_epoch.py) | Compile and exercise only injected fixed-three SDK resources and driver. |
| [audit_a23_trace_owner.py](audit_a23_trace_owner.py) | Offline lifecycle/ownership policy audit and libnx adapter ELF link. |
| [audit_a23_two_epoch.py](audit_a23_two_epoch.py) | Build/run a bounded offline receiver with injected resources and archive negatives. |
| [audit_a23_two_epoch_entry.py](audit_a23_two_epoch_entry.py) | Build the dormant entry, run only injected models and reject altered evidence. |
| [audit_a23_two_epoch_final.py](audit_a23_two_epoch_final.py) | Compile frozen injected operations; collect only after child exit; no hardware. |
| [audit_a23_two_epoch_sdk.py](audit_a23_two_epoch_sdk.py) | Offline SDK driver review. Fake operations only; never opens a device. |
| [audit_a23_two_epoch_workflow.py](audit_a23_two_epoch_workflow.py) | File-only saved69/atomic32 model audit; never writes the real ledger. |
| [audit_a23_v3_runtime.py](audit_a23_v3_runtime.py) | Audit the sealed V3 TLS/stack layout and logger with mocked FS only. |
| [audit_a23_v3_stack_profiles.py](audit_a23_v3_stack_profiles.py) | Current V3 logger and handle-wait profiles, with explicit non-proof boundaries. |
| [audit_a23_versioned_clock_candidate.py](audit_a23_versioned_clock_candidate.py) | Independent cooperative versioned profile/ticks candidate; no driver execution. |
| [audit_a23_versioned_driver_model.py](audit_a23_versioned_driver_model.py) | Replay complete-driver callback/deadline faults and non-atomic profile reads. |
| [audit_a23_waiting_collection.py](audit_a23_waiting_collection.py) | Audit static waiting/SDK/EXE3 collections using explicitly generated models. |
| [audit_a23_waiting_entry.py](audit_a23_waiting_entry.py) | Freeze and exercise the isolated waiting entry with injected operations only. |
| [audit_a23_waiting_receiver.py](audit_a23_waiting_receiver.py) | Build/freeze receiver and run injected loop only. No capture invocation. |
| [audit_a23_worker_failure_model.py](audit_a23_worker_failure_model.py) | Standalone C worker failure schedules and strict cached-material admission. |
| [audit_host_driver.py](audit_host_driver.py) | Read a decoded local MH_FILESET; export bounded, reproducible USB evidence. |
| [audit_host_driver_dispatch.py](audit_host_driver_dispatch.py) | Resolve selected virtual calls in a local kernelcache, without live I/O. |
| [audit_io_usb_host_device.py](audit_io_usb_host_device.py) | Correlate supplied STATUS bytes and an A23 log offline. Never grants USB pass. |
| [audit_io_usb_host_framework.py](audit_io_usb_host_framework.py) | Export the local IOUSBHost framework and selected kernel paths, without USB I/O. |
| [audit_lifecycle_card_companion.py](audit_lifecycle_card_companion.py) | Freeze the observed companion and isolated deployment models. No real card. |
| [audit_lifecycle_card_workflow.py](audit_lifecycle_card_workflow.py) | Exercise temporary cards and seal copied evidence; never instantiate MacCard. |
| [audit_path_span_readiness.py](audit_path_span_readiness.py) | Exercise temporary cards and seal copied evidence; never instantiate MacCard. |

## build（58）

| 工具 | 说明 |
| --- | --- |
| [build_a23_bound_receiver.py](build_a23_bound_receiver.py) | Build a new receiver with separate device identities. Always returns zero uses. |
| [build_a23_bounded_candidate.py](build_a23_bounded_candidate.py) | Isolated joint BURST preflight and per-ready-request trace budget candidate. |
| [build_a23_broker_model.py](build_a23_broker_model.py) | Two sealed roles for one fake-SDK child binary. No production entry mode. |
| [build_a23_capacity_v2_candidate.py](build_a23_capacity_v2_candidate.py) | Build isolated V2 capacity candidates and run computer-only boundary probes. |
| [build_a23_context65_receiver.py](build_a23_context65_receiver.py) | Build an isolated sequence-witness receiver, retaining the path-span device materials. Always return |
| [build_a23_diagnostic_sink.py](build_a23_diagnostic_sink.py) | Independent A23 diagnostic sink candidate; native FS models and ARM link only. |
| [build_a23_execution_v3_candidate.py](build_a23_execution_v3_candidate.py) | Create isolated execution candidates from sealed V2; never acquire hardware. |
| [build_a23_failure_model.py](build_a23_failure_model.py) | Two sealed roles for one fake-SDK child binary. No production entry mode. |
| [build_a23_guard_candidate.py](build_a23_guard_candidate.py) | Offline buffer/cleanup guarded A23 candidate, native models and ELF link only. |
| [build_a23_lead32_receiver.py](build_a23_lead32_receiver.py) | Build an isolated lead32 receiver, retaining the path-span device materials. Always returns zero use |
| [build_a23_lifecycle_candidate.py](build_a23_lifecycle_candidate.py) | Build a separate LCP1 device candidate, never package, deploy, issue or run ARM. |
| [build_a23_lifecycle_deployment.py](build_a23_lifecycle_deployment.py) | Prepare a file-only lifecycle deployment review. Never accesses a card or USB device. |
| [build_a23_lifecycle_receiver.py](build_a23_lifecycle_receiver.py) | Build an isolated lifecycle-candidate receiver with six device materials. Always returns zero uses. |
| [build_a23_live103_interest.py](build_a23_live103_interest.py) | Current103 candidate: preserve all-interest stop, capture raw message/ticks. |
| [build_a23_live109_short128.py](build_a23_live109_short128.py) | Fresh109, fixed three epochs and 128 transactions. Building never opens USB. |
| [build_a23_live112_short128.py](build_a23_live112_short128.py) | Rebind unchanged fixed128 transport to the last recovered112 and spent273. |
| [build_a23_live120_lstat.py](build_a23_live120_lstat.py) | Fresh120, unchanged fixed128 transport with lstat node typing in full guards. |
| [build_a23_live126_interepoch.py](build_a23_live126_interepoch.py) | Fresh126 fixed-three-epoch candidate with exclusive interepoch verifier handoff. |
| [build_a23_live132_completion.py](build_a23_live132_completion.py) | Offline receiver completion cut: one owner-queue continuation, immutable fact. |
| [build_a23_live132_q1.py](build_a23_live132_q1.py) | Q1 SDK-capable candidate; preparation never issues or launches a capture. |
| [build_a23_live132_terminal.py](build_a23_live132_terminal.py) | Current132 receiver adapter, compiled for file checks and offline fixtures only. |
| [build_a23_live75_two_epoch.py](build_a23_live75_two_epoch.py) | Bind the tested STATUS revision to saved75 and a fixed successor range. |
| [build_a23_live91_checked.py](build_a23_live91_checked.py) | Current91 checked-export receiver; build and checks never open USB. |
| [build_a23_live97_three.py](build_a23_live97_three.py) | Fresh97, fixed48, checked-export build. Building never issues or opens USB. |
| [build_a23_live_two_epoch.py](build_a23_live_two_epoch.py) | Build the dedicated live two-epoch CLI. Build/file checks never acquire USB. |
| [build_a23_log_candidate.py](build_a23_log_candidate.py) | Full isolated ARM logger clamp/type candidate; no device access. |
| [build_a23_log_guard_candidate.py](build_a23_log_guard_candidate.py) | Link isolated GetSize protection with new identities; never execute ARM or access devices. |
| [build_a23_path_span_candidate.py](build_a23_path_span_candidate.py) | Isolated full-width filesystem path candidate; never package, deploy or run ARM. |
| [build_a23_path_span_deployment.py](build_a23_path_span_deployment.py) | Prepare a file-only lifecycle deployment review. Never accesses a card or USB device. |
| [build_a23_path_span_receiver.py](build_a23_path_span_receiver.py) | Build an isolated lifecycle-candidate receiver with six device materials. Always returns zero uses. |
| [build_a23_quiet_candidate.py](build_a23_quiet_candidate.py) | Build an isolated USB-only, quiet-window candidate; no hardware execution. |
| [build_a23_quiet_deployment.py](build_a23_quiet_deployment.py) | Prepare a file-only quiet deployment review. Never accesses a card or USB device. |
| [build_a23_quiet_receiver.py](build_a23_quiet_receiver.py) | Build an isolated quiet-candidate receiver with six device materials. Always returns zero uses. |
| [build_a23_sequence_receiver.py](build_a23_sequence_receiver.py) | Build an isolated sequence-witness receiver, retaining the path-span device materials. Always return |
| [build_a23_session_candidate.py](build_a23_session_candidate.py) | New full ARM REL1 candidate, actual startup hooks and modeled FS shutdowns. |
| [build_a23_session_correlation.py](build_a23_session_correlation.py) | Memory-only startup/EP0 correlation prototype; no firmware/FS integration. |
| [build_a23_short24_candidate.py](build_a23_short24_candidate.py) | Build an isolated fixed16/24-byte ARM candidate; no deployment or receiver. |
| [build_a23_short24_entry.py](build_a23_short24_entry.py) | Verify/seal the prepared package and compile a dormant single-use entry. |
| [build_a23_short24_path_span_candidate.py](build_a23_short24_path_span_candidate.py) | Offline short24 rebuild retaining the previously reviewed FS path capacity fix. |
| [build_a23_startup_candidate.py](build_a23_startup_candidate.py) | Offline ARM startup hook candidate plus actual-function native replays. |
| [build_a23_startup_journal.py](build_a23_startup_journal.py) | Independent startup journal, native API adapter hooks and ARM object only. |
| [build_a23_supervisor_model.py](build_a23_supervisor_model.py) | Freeze sources and compile a context-only model helper, never a receiver. |
| [build_a23_trace_candidate.py](build_a23_trace_candidate.py) | Generate isolated A23 handler copies, replay them, and link full ELF only. |
| [build_a23_trace_sink.py](build_a23_trace_sink.py) | Offline extension of sealed A23 handler candidate: one-shot sink and stop window. |
| [build_a23_two_epoch_entry.py](build_a23_two_epoch_entry.py) | Build a file-only inspector and dormant two-epoch entry; acquisition unavailable. |
| [build_a23_verified_entry.py](build_a23_verified_entry.py) | Build a file-only verified entry, retaining all dormant SDK components. |
| [build_a23_wait_path_candidate.py](build_a23_wait_path_candidate.py) | Fixed REL1 path candidate and SDK handle-wait machine audit; no device access. |
| [build_a23_waiting_receiver.py](build_a23_waiting_receiver.py) | Build a dormant receiver and return a zero-use record; never issue or launch. |
| [build_burst_window_receiver.py](build_burst_window_receiver.py) | Prepare one A23 burst using the frozen no-TD diagnostic backend; no USB. |
| [build_clock_audit_receiver.py](build_clock_audit_receiver.py) | Build one burst with deferred Mach clock/USB frame timestamp recording; no USB. |
| [build_darwin_diagnostics.py](build_darwin_diagnostics.py) | Build an isolated libusb 1.0.30 receiver exposing native ISO evidence. |
| [build_event_audit_receiver.py](build_event_audit_receiver.py) | Build audit compatibility using the frozen A17 host64 timing receiver. |
| [build_host_microframe_audit.py](build_host_microframe_audit.py) | Build isolated A23 host microframe audit; preserve frozen A23 artifacts. |
| [build_matched_serial_receiver.py](build_matched_serial_receiver.py) | Build and validate the bounded matched-backend serial receiver without USB. |
| [build_native_guard_receiver.py](build_native_guard_receiver.py) | Build a serial receiver gated by exact native evidence before each resubmit. |
| [build_no_td_receiver.py](build_no_td_receiver.py) | Build an isolated, fresh-idle-only A23 no-TD receiver; never accesses USB. |
| [build_patch.py](build_patch.py) | Build fail-closed, Build-ID-specific A/B/C IPS32 experiment packages. |
| [build_serial_clock_receiver.py](build_serial_clock_receiver.py) | Build and validate the bounded matched-backend serial receiver without USB. |

## collect（18）

| 工具 | 说明 |
| --- | --- |
| [collect_a23_bound_execution.py](collect_a23_bound_execution.py) | Freeze supplied build/device/receipt/EXE3 agreement. No physical provenance. |
| [collect_a23_context65_baseline63.py](collect_a23_context65_baseline63.py) | Freeze an owned invocation with the new history transition checks. No USB. |
| [collect_a23_context65_envelope.py](collect_a23_context65_envelope.py) | Offline freeze/compare of supplied static files, including partial failures. |
| [collect_a23_context65_execution.py](collect_a23_context65_execution.py) | Preserve supplied lifecycle/optional EXE3 files. Never authenticate a physical run. |
| [collect_a23_context65_once.py](collect_a23_context65_once.py) | Freeze an owned invocation with the new history transition checks. No USB. |
| [collect_a23_context65_waiting.py](collect_a23_context65_waiting.py) | Freeze supplied waiting+SDK+EXE3 files; agreement is never provenance. |
| [collect_a23_execution_v3.py](collect_a23_execution_v3.py) | Offline freeze/compare of supplied static files, including partial failures. |
| [collect_a23_lead32_envelope.py](collect_a23_lead32_envelope.py) | Offline freeze/compare of supplied static files, including partial failures. |
| [collect_a23_lead32_execution.py](collect_a23_lead32_execution.py) | Preserve supplied lifecycle/optional EXE3 files. Never authenticate a physical run. |
| [collect_a23_lead32_waiting.py](collect_a23_lead32_waiting.py) | Freeze supplied waiting+SDK+EXE3 files; agreement is never provenance. |
| [collect_a23_lifecycle_execution.py](collect_a23_lifecycle_execution.py) | Preserve supplied lifecycle/optional EXE3 files. Never authenticate a physical run. |
| [collect_a23_path_span_execution.py](collect_a23_path_span_execution.py) | Preserve supplied lifecycle/optional EXE3 files. Never authenticate a physical run. |
| [collect_a23_quiet_execution.py](collect_a23_quiet_execution.py) | Freeze supplied build/device/receipt/EXE3 agreement. No physical provenance. |
| [collect_a23_sequence_envelope.py](collect_a23_sequence_envelope.py) | Offline freeze/compare of supplied static files, including partial failures. |
| [collect_a23_sequence_execution.py](collect_a23_sequence_execution.py) | Preserve supplied lifecycle/optional EXE3 files. Never authenticate a physical run. |
| [collect_a23_sequence_waiting.py](collect_a23_sequence_waiting.py) | Freeze supplied waiting+SDK+EXE3 files; agreement is never provenance. |
| [collect_a23_two_epoch_final.py](collect_a23_two_epoch_final.py) | Freeze supplied static models or an already exited supervised model child. |
| [collect_a23_waiting_execution.py](collect_a23_waiting_execution.py) | Freeze supplied waiting+SDK+EXE3 files; agreement is never provenance. |

## context65（7）

| 工具 | 说明 |
| --- | --- |
| [context65_baseline63.py](context65_baseline63.py) | Adopt one reviewed saved63 snapshot. All operations here are file-only. |
| [context65_baseline63_recovery.py](context65_baseline63_recovery.py) | Explicit read-only recovery. Import and job preparation never access a card. |
| [context65_flag_card.py](context65_flag_card.py) | Two explicit card phases: readonly backup/eject, then reinsert/one empty create. |
| [context65_flag_repair.py](context65_flag_repair.py) | Prepare a bounded flag repair and exercise it on temporary directory models. |
| [context65_once_reservation.py](context65_once_reservation.py) | Exclusive durable65 burn with an immutable invocation commitment. No USB. |
| [context65_recovery.py](context65_recovery.py) | Explicit read-only recovery. Import and job preparation never access a card. |
| [context65_workflow.py](context65_workflow.py) | File-only workflow binding for the immutable context65 receiver. |

## decode（1）

| 工具 | 说明 |
| --- | --- |
| [decode_a23_trace.py](decode_a23_trace.py) | Decode the A23 endpoint trace carried in the ISO report diagnostics. |

## experiment.py（1）

| 工具 | 说明 |
| --- | --- |
| [experiment.py](experiment.py) | One entry point for local A23 experiment status, restoration and capture. |

## extract（1）

| 工具 | 说明 |
| --- | --- |
| [extract_usb.py](extract_usb.py) | Extract a user's installed firmware usb ExeFS; never print key-tool output. |

## gen（1）

| 工具 | 说明 |
| --- | --- |
| [gen_alt1_nop_payload.py](gen_alt1_nop_payload.py) | Generate the runtime NOP payload header for the ALT1 endpoint-install test. |

## inspect（1）

| 工具 | 说明 |
| --- | --- |
| [inspect_a23_context65_flag_card.py](inspect_a23_context65_flag_card.py) | Read saved card-job files only; never probe a PID/card or release any claim. |

## io（6）

| 工具 | 说明 |
| --- | --- |
| [io_usb_host_burst_draft.py](io_usb_host_burst_draft.py) | Print/check an offline single-burst draft. Contains no USB executor or ticket writer. |
| [io_usb_host_burst_entry_plan.py](io_usb_host_burst_entry_plan.py) | Fixed SDK diagnostic plan; software fields never certify hardware. |
| [io_usb_host_burst_mock_log.py](io_usb_host_burst_mock_log.py) | Deterministic synthetic log for the injected BurstMock ISO7 snapshot only. |
| [io_usb_host_lead32_policy.py](io_usb_host_lead32_policy.py) | Independent exact-integer audit of provided simulation clock observations. |
| [io_usb_host_probe_plan.py](io_usb_host_probe_plan.py) | Fixed offline Mock observation plan. Printing this plan enables no capture. |
| [io_usb_host_runtime_policy.py](io_usb_host_runtime_policy.py) | Independent exact-integer audit of provided simulation clock observations. |

## lifecycle（2）

| 工具 | 说明 |
| --- | --- |
| [lifecycle_card_companion_deploy.py](lifecycle_card_companion_deploy.py) | Separate deployment variant for one observed Mac companion template. |
| [lifecycle_card_workflow.py](lifecycle_card_workflow.py) | Bounded card files and receipts. Import/--help never probes a card. |

## model（4）

| 工具 | 说明 |
| --- | --- |
| [model_a23_quiet_paths.py](model_a23_quiet_paths.py) | Current quiet ELF instruction models. No native ARM or actual SDK calls. |
| [model_a23_v3_logger_stack.py](model_a23_v3_logger_stack.py) | Continuous final-ELF logger/vsnprintf model; FS results alone are injected. |
| [model_a23_wait_machine.py](model_a23_wait_machine.py) | Replay sealed AArch64 handle-wait paths with injected SVC/ticks, never USB. |
| [model_uac_pcm_ring.py](model_uac_pcm_ring.py) | Model the UAC PCM ring / URB schedule and the A23 frame-cursor gap. |

## nso2elf.py（1）

| 工具 | 说明 |
| --- | --- |
| [nso2elf.py](nso2elf.py) | Convert a Switch NSO0 (shared object) into an ELF64 file. |

## package（2）

| 工具 | 说明 |
| --- | --- |
| [package_a23_short24.py](package_a23_short24.py) | Package the frozen short24 ELF/IPS against the last recovered card, file-only. |
| [package_experiment.py](package_experiment.py) | Build isolated ISO and rollback clients, verify NPDM IDs, package A/B/C. |

## path（1）

| 工具 | 说明 |
| --- | --- |
| [path_span_card_workflow.py](path_span_card_workflow.py) | Bounded card files and receipts. Import/--help never probes a card. |

## prepare（10）

| 工具 | 说明 |
| --- | --- |
| [prepare_a23_context65_baseline63.py](prepare_a23_context65_baseline63.py) | Preview by default; formal issuance needs explicit authorization and fresh receipts. |
| [prepare_a23_context65_once.py](prepare_a23_context65_once.py) | Preview by default; formal issuance needs explicit authorization and fresh receipts. |
| [prepare_a23_lead32_once.py](prepare_a23_lead32_once.py) | Preview one lifecycle diagnostic; --issue creates a new record after user authorization. |
| [prepare_a23_lifecycle_once.py](prepare_a23_lifecycle_once.py) | Preview one lifecycle diagnostic; --issue creates a new record after user authorization. |
| [prepare_a23_path_span_once.py](prepare_a23_path_span_once.py) | Preview one lifecycle diagnostic; --issue creates a new record after user authorization. |
| [prepare_a23_quiet_once.py](prepare_a23_quiet_once.py) | Preview one quiet diagnostic; --issue creates a new record after user authorization. |
| [prepare_a23_sequence_once.py](prepare_a23_sequence_once.py) | Preview one lifecycle diagnostic; --issue creates a new record after user authorization. |
| [prepare_a23_two_epoch.py](prepare_a23_two_epoch.py) | Read-only saved69/two-epoch preview. No issue/acquire/reserve command exists. |
| [prepare_io_usb_host_burst.py](prepare_io_usb_host_burst.py) | Build/freeze a dormant SDK burst receiver. Issues no usable capture count. |
| [prepare_io_usb_host_no_td.py](prepare_io_usb_host_no_td.py) | Offline build/freeze of the SDK receiver and one-use ticket; never captures. |

## probe（1）

| 工具 | 说明 |
| --- | --- |
| [probe_a23_ep0_trace.py](probe_a23_ep0_trace.py) | Instrument frozen A23 client source COPIES and export bounded simulated traces. |

## research（1）

| 工具 | 说明 |
| --- | --- |
| [research_storage.py](research_storage.py) | Lossless cold storage for explicitly selected offline research directories. |

## sequence（2）

| 工具 | 说明 |
| --- | --- |
| [sequence_once_reservation.py](sequence_once_reservation.py) | Durable one-block burns for the scoped sequence receiver. No device access. |
| [sequence_recovery.py](sequence_recovery.py) | Explicit post-capture read-only recovery; import and preparation access no card. |

## summarize（2）

| 工具 | 说明 |
| --- | --- |
| [summarize_host_microframe.py](summarize_host_microframe.py) | Summarize raw host query observations, retaining failures and uncertainty. |
| [summarize_run.py](summarize_run.py) | Decode host JSONL and raw controller words; preserve unverified claims. |

## validate（1）

| 工具 | 说明 |
| --- | --- |
| [validate_no_td_receiver.py](validate_no_td_receiver.py) | Exercise the real no-TD receiver under USB mocks; no hardware access. |
