English | [简体中文](capability-matrix.zh-CN.md)

This document maps the capabilities of `litearm-studio` (GitHub `main`, 2026-11-20, `35e7092`) to
`litearm-tool-stm32`, records what is deliberately not migrated, and gives the dependency order for
the remaining work. It is the deliverable for issue #15 and the capability/migration boundary
required by planning#18.

Status is as of **2026-11-28**, after the implementation pass through PR #36 and the
Chinese/English UI work (issue #12). Remaining work is joint zeroing (#20) and hardware
acceptance on a real arm, gripper, DFU board and Windows CDC.

# Studio → tool capability matrix

## Capability map

| Capability | litearm-studio | litearm-tool-stm32 | Status |
| --- | --- | --- | --- |
| USB CDC connect / port pick | Yes | Yes, onboard CDC first | Delivered |
| Link loss recovery | Yes, daemon state machine | Automatic redial (last port, then enumerated candidates, backoff) | Delivered, PR #24 |
| 100 Hz state stream | 50 Hz broadcast | 100 Hz owner-thread feed + status hook | Delivered |
| Live plot | Yes | 100 Hz ring buffer, 30 Hz redraw, per-joint selection | Delivered |
| Machine control | Enable / disable / reset / clear faults / speed | Same + home / park / read state / reset reason | Delivered |
| Joint motion | `movej` | `movej` / `move_js` / `move_mit` / `move_mit_all` | Delivered |
| Joint sliders + soft limits + ready pose | Sliders, firmware soft limits, ready pose | Numeric `movej` inputs; one-click ready pose | Sliders declined 2026-11-27; ready pose delivered, PR #27 |
| Cartesian absolute | `movep` | `get_tcp` / `ik` / `move_p`; ready pose through the same joint-space `movej` gate | Delivered |
| Cartesian jog / straight line / stop | Base/tool jog, `movel`, controlled stop, takeover | Jog + `movel` + controlled stop + explicit `movej` takeover | Delivered, PR #25 |
| Zero-G hand guiding | Yes | Yes, SDK keep-alive, exit-to-hold | Delivered |
| LiteGrip gripper | Page, telemetry, calibration, settings (Linux only) | Page + owner thread, telemetry, calibration, zero-torque stop, CAN channel enumeration | Delivered, PR #28/#34 (Linux only; hardware acceptance pending) |
| Activation | Page + service client | Same contract, stdlib client | Delivered, PR #18 |
| USB DFU firmware upgrade | Page + DfuSe engine | DfuSe engine copied verbatim, tool adapter | Delivered, PR #19 (real-board acceptance pending) |
| Parameters / feed-forward | Per-joint gains and limits | Full catalog, 0x26/0x27/0x28, ff_mask, import/export, flash | Delivered, deeper than studio |
| Tuning guide | No | Formula, symptom table, per-parameter detail | Tool extra |
| Diagnostics | Partial | KIN_BENCH, reset reason, link counters, diagnostics bundle | Delivered, deeper than studio |
| Fault detail | Basic | Per-axis reason + action, 0x51 on demand, event history | Delivered, deeper than studio |
| 300 Hz control-tick capture | No (20 Hz browser telemetry) | Firmware capture, preview, raw + parsed CSV | Delivered, including CSV, PR #22 |
| 3D digital twin | Yes | URDF/STL, FK, 60 Hz smoothed render, LOD; Windows Mesa fallback | Delivered, PR #17 (target-GPU 60 FPS / real-arm acceptance pending) |
| Structured logs | JSONL + web viewer | JSONL, redaction, PyQt viewer, restart history | Delivered, PR #23 |
| CSV export | Browser telemetry export | Plot window + capture samples | Delivered, PR #22 |
| Single instance / fake device | Daemon lock + `--fake` | Single-instance lock and `--fake` demo mode | Delivered, PR #21 + #33 |
| Chinese / English UI | Yes | Chinese + English; live switch, system default, persisted per machine | Delivered, PR #40 |
| Light / dark theme | Yes | Dark only | Not migrated; add on request |
| Windows build | Yes (exe) | PyInstaller onedir; tag releases build Linux and Windows bundles | Delivered, PR #29/#35/#36 (real CDC/DFU acceptance pending; Windows/OpenGL verified, including software-GL fallback) |
| Release artifacts | Studio desktop build | Every tag attaches Linux tar.gz + `.deb` + Windows zip with `.sha256` sidecars | Delivered, PR #35/#36 |
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
| Studio web i18n stack | Not ported. The tool uses a lightweight Chinese-source string table (automatic fallback) plus a `QSettings` language choice; no Qt Linguist or Web i18n dependency. |
| Theme toggle | Not ported for now; add only on request. |

## Remaining work

All capabilities in the map are delivered except the rows marked otherwise. What is left:

| Item | Issue | Depends on | Exit criteria |
| --- | --- | --- | --- |
| Joint zero-offset calibration | #20 | Firmware command IDs and persistence | Manual zero + auto approach on hardware |
| Hardware acceptance | #5, #7, #9, #14, #16 | Real arm, gripper CAN adapter, DFU board, Windows host | Cartesian/jog, gripper, DFU success/cancel/unplug, Windows CDC/DFU; 3D at 60 FPS on target GPU |

The implementation pass (PR #21–#36) is merged. Fake mode was split from the 3D work into #33; the
release pipeline (#35) builds Linux and Windows bundles on every tag; #36 fixed the Windows
PowerShell BOM. Issues #3 and #16 are delivered by #17 — do not open a second 3D track.

## Acceptance mapping (planning#18)

| planning#18 criterion | Evidence |
| --- | --- |
| Core flows: connect, control, state/plot, logs, settings | Capability map above; pages and tests in this repository |
| Reuse transport, protocol, state chain; key behavior tested | Single-owner `SdkWorker`; offline suites for the state hook, safety gates, logs and jog math |
| Packaged build starts and connects on the target platform | Every tag builds the Linux tar.gz/.deb and the Windows zip with checksums (PR #35); real CDC/DFU acceptance remains |
| Capability comparison and migration boundaries documented | This document |
