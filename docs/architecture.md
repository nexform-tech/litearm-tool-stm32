English | [简体中文](architecture.zh-CN.md)

This document describes the structure of LiteArm Tool STM32 for developers who change the GUI, command path, or parameter catalog.

# Architecture

## Context

The tool is a PyQt5 desktop application that talks to LiteArm STM32 firmware over a USB CDC serial port. It shows motor state at 100 Hz, plots recent history, dispatches control and motion commands, and edits runtime parameters.

The tool does not implement hard safety. Slew limits, soft limits, invalid-value rejection, the watchdog, and the emergency-stop fallback belong to the firmware. The tool implements only the operator-intent layer: confirmation dialogs, motion-page locking, parameter range checks, and the emergency-stop bypass.

Constraints:

- One serial port has one owner. The firmware pushes status at 100 Hz and does not wait for the host.
- Commands are request/response with ACK and ERR frames. A queued command must never block the emergency stop.
- The parameter catalog must be usable without Qt so tests and YAML import/export share it.

## Components

| Component | Responsibility | Depends on |
|---|---|---|
| `litetool/protocol.py` | Frame codec, CRC, G8 status frame, ACK/ERR, tuning command codecs | Standard library only |
| `litetool/param_catalog.py` | Parameter mirror: schema, ranges, diff, ff_mask, roles, hints, details | `protocol.py` |
| `litetool/tuning_guide.py` | Tuning guide text: formulas, symbol mapping, prerequisite notes, symptom table | Standard library only |
| `litetool/checks.py` | Δq intent confirmation and motion-page lock checks | Standard library only |
| `litetool/client.py` | State cache, ACK pairing, emergency bypass, parameter read/write | `protocol.py`, `transport.py` |
| `litetool/transport.py` | Port discovery and `SerialLink` background reader | `pyserial` |
| `litetool/settings.py` | Tolerant `config.yaml` merge | `PyYAML` |
| `litetool/gui/session.py` | Qt-free session controller: reader → client → plot model | `client.py`, `plot_model.py` |
| `litetool/gui/bridge.py` | Cross-thread Qt signal bridge | PyQt5 |
| `litetool/gui/plot_model.py` | Thread-safe ring buffer of recent state | Standard library |
| `litetool/gui/*_page.py` | Monitor, plot, control, motion, parameter, and tuning-guide pages | PyQt5, `pyqtgraph` |
| `litetool/gui/main_window.py` | Window assembly, command bus, emergency/lock/Δq flows | All GUI modules |

## Data flow

```text
USB CDC ──frames──▶ SerialLink reader thread ──▶ Client state cache ──▶ PlotModel ring buffer
                                                          │
GUI 20 Hz sampling ───────────────────────────────────────┘
                                                          │
GUI command ──▶ command worker (one at a time) ──▶ Client ──▶ SerialLink ──▶ USB CDC
```

Read path: the serial reader decodes frames, updates the state cache, and appends every sample to the ring buffer. The GUI samples the cache at 20 Hz for tables and status lamps, and redraws the plot at 30 Hz.

Write path: GUI actions submit one command to the worker. The worker serializes commands with `_tx_lock` and waits for the ACK or ERR. The parameter page runs its own write batches but shares the busy flag, so it cannot interleave with the main command path. The emergency stop bypasses the queue through `emergency_now()`.

## Boundaries

- This repository contains the host tool, its parameter mirror, presets, and offline tests.
- Firmware, motor control, and hard safety live in `litearm-stm32`.
- The serial protocol SDK lives in `litearm-python`.
- Hardware acceptance steps are documented in the README; they are not automated here.

## Decisions

- **No SocketCAN.** The firmware owns the motor CAN domain, so the host uses the USB CDC command port.
- **The firmware is the safety authority.** Duplicating limits in the GUI would create two sources of truth that can disagree.
- **Single command worker.** One serial port cannot serve concurrent readers safely; serializing commands keeps ACK pairing unambiguous.
- **Pure-Python catalog.** `param_catalog.py` and `tuning_guide.py` carry no Qt imports so tests, YAML import/export, and the UI use the same definitions.
- **Automatic status-frame layout detection.** Firmware 1.4.x and 1.5.0 use different frame lengths; the decoder selects the layout from the length instead of requiring a version flag.
