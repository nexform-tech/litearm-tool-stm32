English | [简体中文](capability-matrix.zh-CN.md)

This document maps the capabilities of `litearm-studio` (GitHub `main`, 2026-11-20, `35e7092`) to
`litearm-tool-stm32`, records what is deliberately not migrated, and gives the dependency order for
the remaining work. It is the deliverable for issue #15 and the capability/migration boundary
required by planning#18.

Status is as of **2026-11-27**, after the first implementation pass (PR #21–#29). "In review"
means an open pull request, not merged.

# Studio → tool capability matrix

## Capability map

| Capability | litearm-studio | litearm-tool-stm32 | Status |
| --- | --- | --- | --- |
| USB CDC connect / port pick | Yes | Yes, onboard CDC first | Delivered |
| Link loss recovery | Yes, daemon state machine | Automatic redial (last port, then enumerated candidates, backoff) | In review, PR #24 |
| 100 Hz state stream | 50 Hz broadcast | 100 Hz owner-thread feed + status hook | Delivered |
| Live plot | Yes | 100 Hz ring buffer, 30 Hz redraw, per-joint selection | Delivered |
| Machine control | Enable / disable / reset / clear faults / speed | Same + home / park / read state / reset reason | Delivered |
| Joint motion | `movej` | `movej` / `move_js` / `move_mit` / `move_mit_all` | Delivered |
| Joint sliders + soft limits + ready pose | Sliders, firmware soft limits, ready pose | Numeric `movej` inputs; one-click ready pose | Sliders declined 2026-11-27; ready pose in review, PR #27 |
| Cartesian absolute | `movep` | `get_tcp` / `ik` / `move_p` | Delivered |
| Cartesian jog / straight line / stop | Base/tool jog, `movel`, controlled stop, takeover | Jog + `movel` + controlled stop + explicit `movej` takeover | In review, PR #25 |
| Zero-G hand guiding | Yes | Yes, SDK keep-alive, exit-to-hold | Delivered |
| LiteGrip gripper | Page, telemetry, calibration, settings (Linux only) | Page + owner thread, telemetry, calibration, zero-torque stop | In review, PR #28 (Linux only; hardware acceptance pending) |
| Activation | Page + service client | Same contract, stdlib client | In review, PR #18 |
| USB DFU firmware upgrade | Page + DfuSe engine | DfuSe engine copied verbatim, tool adapter | In review, PR #19 |
| Parameters / feed-forward | Per-joint gains and limits | Full catalog, 0x26/0x27/0x28, ff_mask, import/export, flash | Delivered, deeper than studio |
| Tuning guide | No | Formula, symptom table, per-parameter detail | Tool extra |
| Diagnostics | Partial | KIN_BENCH, reset reason, link counters, diagnostics bundle | Delivered, deeper than studio |
| Fault detail | Basic | Per-axis reason + action, 0x51 on demand, event history | Delivered, deeper than studio |
| 300 Hz control-tick capture | No (20 Hz browser telemetry) | Firmware capture, preview, raw + parsed CSV | Delivered; CSV in review, PR #22 |
| 3D digital twin | Yes | URDF/STL, FK, 60 Hz smoothed render, LOD | In review, PR #17 |
| Structured logs | JSONL + web viewer | JSONL, redaction, PyQt viewer, restart history | In review, PR #23 |
| CSV export | Browser telemetry export | Plot window + capture samples | In review, PR #22 |
| Single instance / fake device | Daemon lock + `--fake` | Fake device in PR #17; single-instance lock in PR #21 | In review, issues #13/#17 |
| Chinese / English UI | Yes | Chinese only | Not started, issue #12 |
| Light / dark theme | Yes | Dark only | Not started; no issue |
| Windows build | Yes (exe) | PyInstaller onedir script; offline build verified on the host Windows | In review, PR #29 (real CDC/DFU/OpenGL pending) |
| Joint zero-offset calibration | Not a studio feature (`zeroJoints` = firmware home) | None | New scope, issue #20; firmware command IDs unassigned |

## Migration boundaries

### Reuse, do not rewrite

| Area | Rule |
| --- | --- |
| Serial ownership | One owner thread holds the SDK and the port. Jog/stop takeovers are **write-only bypasses**, the same lane class as the emergency stop; they never read the port from the GUI thread. |
| Activation | Port studio's client contract: license record shape, registration validation, service error codes, consent document. The tool has the only outbound network point. |
| DFU | The DfuSe engine and image pipeline are copied verbatim from studio/upstream `dfu-flash`. Any timing change goes back upstream first. |
| Gripper | Port studio's session, calibration and CAN adapter; do not reimplement the gripper protocol. Linux only. |
| Log schema | Keep studio's OpenTelemetry field names and JSONL layout so `jq`, Loki and Fluent Bit keep working. Do not import FastAPI/WebSocket. |
| 3D assets | Use `litearm-description` URDF/meshes and studio's decimated/LOD process; no Node/pnpm build chain inside the tool. |

### Deliberately not migrated

| Item | Decision |
| --- | --- |
| Tauri/React frontend | Replaced by PyQt pages; the web UI is not ported. |
| FastAPI daemon and WebSocket protocol | Not ported; the tool is one process with one SDK owner thread. |
| Browser telemetry store and retention policy | Not ported; the tool's 100 Hz ring buffer and 300 Hz firmware capture are the data sources. |
| QtWebEngine / embedded browser | Excluded. |
| VR runtime and rendering | Stays in `litearm-vr-studio`; the tool does not host VR. |
| Studio web i18n stack | Not ported; issue #12 uses Qt translation or a string table. |
| Theme toggle | Not ported for now; add only on request. |

## Remaining work and order

The stages are ordered by dependency and risk. Issue numbers are in `litearm-tool-stm32` unless
stated otherwise.

| Stage | Issue | Depends on | Exit criteria |
| --- | --- | --- | --- |
| M0 | #13 single instance + fake device | — | Second launch focuses the first window; `--fake` runs without a port |
| M0 | #10 structured logs | — | JSONL on disk, filterable page, restart history |
| M0 | #11 CSV export | — | Plot window and capture samples export with units |
| M0 | #15 this document | — | Capability map and boundaries accepted |
| M1 | #6 link recovery | — | Replug/port change recovers without restoring the unlock |
| M1 | #5 Cartesian jog + `movel` + stop | #6; firmware `LITEARM_CART_PLAN` | Bench and real-arm acceptance |
| M1 | #4 ready pose (sliders declined) | — | One-click ready pose; numeric inputs stay. PR #27 |
| M2 | #8 activation | Activation service + unactivated arm | Unactivated → activated → enable |
| M2 | #9 DFU | #8 for branch stacking; real board | Success, cancel, unplug runs |
| M2 | #16 3D digital twin | Target GPU and Windows | 60 FPS at 1080p; ≤10 MB packaging delta |
| M2 | #7 LiteGrip gripper | `litegrip` SDK + CAN adapter | Read/write/calibrate with telemetry. PR #28 |
| M3 | #12 Chinese/English UI | M1/M2 strings stable | Language switch without restart |
| M3 | #14 Windows packaging | M1/M2 features | Frozen build starts and connects on Windows. Offline build in PR #29; real CDC/DFU/OpenGL pending |
| M3 | #20 joint zeroing | Firmware command IDs and persistence | Manual zero + auto approach on hardware |

Issue #3 (3D spike) reached a positive conclusion: `pyqtgraph.opengl` plus PyOpenGL works in the
tool's PyQt5 stack. The implementation is tracked by #16; do not open a separate 3D track.

The first implementation pass is in review as PR #21–#29. Single instance and fake mode are split
across #21 and #17; ready pose is #27; gripper is #28; Windows packaging is #29. No merges are
assumed here: the "in review" rows describe code, not a shipped main branch.

## Acceptance mapping (planning#18)

| planning#18 criterion | Evidence |
| --- | --- |
| Core flows: connect, control, state/plot, logs, settings | Capability map above; pages and tests in this repository |
| Reuse transport, protocol, state chain; key behavior tested | Single-owner `SdkWorker`; offline suites for the state hook, safety gates, logs and jog math |
| Packaged build starts and connects on the target platform | Linux PyInstaller onedir; on-hardware checklist; Windows is issue #14 |
| Capability comparison and migration boundaries documented | This document |
