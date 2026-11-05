English | [简体中文](README.zh-CN.md)

LiteArm Tool STM32 is a desktop host application for the LiteArm motion-control firmware (`litearm-stm32`, STM32H723). It monitors motor state, plots live curves, and sends control and motion commands over the onboard USB CDC port.

# LiteArm Tool STM32

The tool follows the interaction style of `/home/llx/dm-tool` and uses the **USB CDC command port**, not SocketCAN, because the firmware owns the motor CAN domain.

- Transport: onboard composite USB (gs_usb + CDC VCP), VID:PID `1d50:606f` → `/dev/ttyACM0`
- Protocol: `SOF(0xA5) | CMD | LEN | PAYLOAD | CRC16-CCITT-FALSE`. The implementation is ported from `litearm-stm32/tools/arm_audit.py` (latest G8 status frame layout, reviewed by firmware).

## Safety model (important)

**The firmware is the authority for all hard protection.** Slew limits, soft limits, NaN and invalid-value rejection, watchdog fail-soft, and the emergency-stop fallback live in the STM32 and do not depend on the host tool being online. This tool does **not** duplicate them.

The tool covers only the operator-intent layer that firmware cannot enforce:

1. **Motion pages are locked by default.** Unlock requires ticking "the arm is clear and the emergency stop is reachable". Disconnect, emergency stop, FAULT, and EMERGENCY re-lock automatically.
2. **Δq confirmation.** For `move_j` / `move_mit`, when the target differs from the current position by more than `confirm_threshold` (default 0.5 rad), every joint delta is listed and confirmed before sending. This prevents order-of-magnitude typos.
3. **Always-available emergency stop.** The red button in the top bar uses the `emergency_now()` bypass, so queued commands waiting for an ACK cannot delay it.
4. `reset` asks for confirmation. `enable` is disabled while FAULT or emergency-stop latch is active.
5. `move_mit` supports **single-frame** dispatch only. The tool provides no 100 Hz continuous stream control.
6. **Parameter page.** Values are clamped and range-checked in the GUI before sending (out-of-range cells turn red and are not sent). ff_mask changes, batch import and apply, and `param_save` all ask for confirmation. Writes take effect in RAM immediately.

## Parameter tuning page

Firmware master supports the runtime parameter write path. **Readback on 0x2B/0x2C requires firmware `27961a1+`** (parameter readback commands, merged into master; the 30-byte `RSP_FF_VEC` and 7-byte `RSP_FF_SCALAR` payloads redundantly carry the RSP id, and the decoder matches the real device layout).

| Area | Write | Read | Notes |
| --- | --- | --- | --- |
| Joint control / limits | `0x22` kp/kd/tau_max, `0x23` q_min/q_max | `0x24`→`0x49` (idx + 5×f32) | Per joint |
| Per-joint vectors | `0x26` item 1..11 (friction/ki/i_max/wall/gs/is/friction_v2) | `0x2B`→`0x4B` (7×f32) | One group at a time |
| Global scalars | `0x28` item 1..8 | `0x2C`→`0x4C` | Includes payload_mass/gravity/friction_model |
| ff_mask | `0x27` u32 | `0x2C` item 9 (f32 value, exact up to 0x1FF) | Checkbox group |
| Persist | `0x25` param_save (requires disabled state) | — | Second confirmation |

Usage:

1. Connect, open the **Parameters** tab, and click [Refresh current]. The tool reads `0x24×7` + `0x2B item 1-11` + `0x2C item 1-9` in one pass. The table then matches the firmware ledger, for example kp=[360,420,220,220,50,50,50], ff_mask=0x1BF, friction_model=1.
2. Double-click a cell to edit. Yellow means changed but not sent; red means out of range or failed. Use [Send selected rows] (kp/kd/tau_max and q_min/q_max are sent as pairs) or [Send all]. Every write waits for an ACK; failures are marked red and logged.
3. Global scalars use the spin boxes below the table; ff_mask uses the checkbox group. [Send global] sends them (changes are confirmed first).
4. Batch: use `presets/` (`current_master_defaults` factory 0x1BF, `se1_friction` enables only master and friction bits) or [Import YAML/JSON…] (`templates/params_example.yaml` documents units and ranges). A **diff preview** shows every old→new cell, then [Apply] sends all writes in order. "Persist to flash after sending" asks for a second confirmation and requires a disabled arm. [Export current] reads everything back to YAML in the same shape as import, so re-importing the same file produces an empty diff.
5. The status line shows the last result, ACK, or ERR. Disconnect disables the page; reconnection restores it.

Safety gates (the firmware still provides the backstop):

- **[Refresh current] must succeed** before [Send selected rows], [Send all], [Send global], or editing. Otherwise default global values (such as gravity=0) could be sent blindly while the arm is enabled and drop gravity compensation.
- While the arm is **enabled**, writes on 0x22/0x23/0x26/0x28/0x27 ask for "live control-law change" confirmation.
- Before limit writes (0x23), the tool checks each joint's current q against the new [q_min, q_max] and refuses out-of-range values, preventing an immediate POS_VIOL/FAULT.
- ff_mask changes, param_save, and batch apply all ask for confirmation. Readback replies are correlated by item/sub; stale replies are dropped and retried, and a timeout is reported as a failure.

The range mirror table is in `litetool/param_catalog.py` (pure Python, no Qt, shared by tests, YAML, and the UI). Values follow firmware `params.c` and `flash_store.c apply_loaded`. The parameter page includes a **Tuning guide** tab with dynamics and control-law formulas, symbol-to-UI mapping, a read-before-you-start section, a symptom-to-parameter table, and collapsible per-parameter explanations. The explanations share their source with the hover tooltips; selecting a row and clicking [Tuning guide] jumps to the matching entry.

Quick reference:

- Per joint: kp[0,500] kd[0,5] tau_max[0.1,120] q_min/q_max[-15,15] (min<max)
  friction[0,50] ki[0,1000] i_max[0,100] wall_stiff[0,2000] wall_damp[0,50]
  wall_tau_max[0,50] gs/is[0,20] friction_v[0,20] fc0[0,50] fc1[-50,0]
- Global: fric_db[1e-4,0.5] wall_margin[0,0.5] friction_slew[0,500]
  payload_mass[0,20] payload_com[-1,1]×3 gravity[-50,50]×3
  friction_model{0=v1 error direction, 1=v2 SE1 velocity direction} fric_v2_eps[1e-3,0.5]
- ff_mask bits: MASTER=0x01 G=0x02 INERTIA=0x04 CORIOLIS=0x08 FRICTION=0x10
  INTEGRAL=0x20 WALL=0x40 QUANT=0x80 VELREF=0x100

## Usage

```bash
pip install -r requirements.txt
python3 main.py            # A normal user account is enough if it is in the dialout group
```

`litearm-python` 2.1.0 or newer is required and is not on PyPI. See [Setup](docs/setup.md) for the exact install command.

After launch, choose the serial port in the top bar and connect. The top bar shows the firmware version (for example `Litearm1.4.0-7J`). The monitor page refreshes from the firmware's 100 Hz status stream. A 7-joint arm and a 1-joint bench are detected from the status frame length.

Configuration lives in [config.yaml](config.yaml). It contains interaction settings only, not limits.

## Code organization

```text
main.py                 Entry point
litetool/
  protocol.py           Frame codec/CRC/G8 status frame/ACK/ERR/TCP/tuning commands (pure functions)
  param_catalog.py      Tuning parameter catalog mirror + schema/diff/ff_mask + role/hint/detail (pure Python)
  tuning_guide.py       Tuning guide content (formulas, symbol mapping, prerequisites, symptom table; pure Python)
  checks.py             Δq intent-layer confirmation (the only "safety" module)
  client.py             State cache + command ACK pairing + emergency bypass + tuning reads/writes
  transport.py          find_ports + SerialLink background reader thread
  settings.py           config.yaml merge (tolerant)
  gui/
    session.py          Qt-free session controller (reader → client → PlotModel)
    bridge.py           Cross-thread Qt signal bridge
    plot_model.py       Thread-safe state ring buffer
    monitor_page.py     Monitor page   plot_page.py    Plot page
    control_page.py     Control page   motion_page.py  Motion page
    params_page.py      Parameter page (per-joint table, compact globals, batch import/export, flash persist)
    tuning_guide_page.py Tuning guide page (formulas, symptom table, expandable per-parameter details)
    main_window.py      Main window assembly + command bus + emergency/lock/Δq flows
templates/params_example.yaml   Import template with unit and range comments
presets/                        Factory and SE1 friction presets
tests/                          Offline tests (run without hardware)
```

Thread model: a serial reader thread (frames → state cache → full-rate ring buffer), a command worker thread (one command at a time, serialized by `_tx_lock`; the parameter page waits for each ACK and is mutually exclusive with the main command path through `busy_changed`), and the GUI main thread (20 Hz table and status refresh, 30 Hz plot redraw).

## Tests

```bash
python3 -m pytest          # 119 cases: protocol (including tuning read codecs), checks,
                           # client (FakeLink), transport, settings, plot model,
                           # parameter catalog (schema/range/diff), GUI smoke
```

## On-hardware acceptance checklist

Run this in order on the first setup or after a change. If any step differs from the expected result, stop and investigate. Do not skip steps.

1. **Read-only connection** (disabled, safe):
   - [ ] Choose the port in the top bar → connect → status turns green "● Online" and the firmware version appears
   - [ ] Monitor page mode=INIT, frame rate ≈ 100 Hz, seq increases without gaps (frame loss ≈ 0)
   - [ ] The table shows q/dq/tau/temperature/err per joint. Unplug the cable → red "● Offline" and all command buttons are disabled
2. **Plots**:
   - [ ] The plot page scrolls with state. Toggle J1..J7 channels. "Freeze" pauses and "Clear" redraws
3. **Basic control** (engages the magnetic brake; support the arm):
   - [ ] enable → ACK; mode enters MOVE_J after a move
   - [ ] disable / clear fault / speed multiplier slider take effect
   - [ ] Emergency stop → mode=EMERGENCY and the FAULT lamp lights; enable is rejected; **reset** returns to INIT and all lamps turn off
4. **Motion dispatch** (start at low speed, sp=0.1):
   - [ ] The motion page shows the lock banner; tick the confirmation to unlock
   - [ ] move_j target = current position + 0.1 rad → small movement to target
   - [ ] move_j target differs by more than 0.5 rad → Δq confirmation appears; cancelling sends nothing
   - [ ] Press emergency stop during a move → immediate lock + mode=EMERGENCY; reset and unlock to move again
5. **Failure paths**:
   - [ ] Click other buttons rapidly during a command → "busy" message, no concurrent dispatch
   - [ ] Enter NaN or a huge value for move_j → log shows firmware ERR 0x02 rejection and the arm does not move

## Firmware compatibility (1.4.x / 1.5.0)

- **Automatic dual status-frame layout.** ≤1.4.0 is `4+21N`; 1.5.0 (M7) is `6+21N` (trailing joint_fault u16 axis bitmap, flags bit9=enabled). The decoder detects the layout from frame length.
- Degraded behavior on older firmware: the arm-enabled indicator is always off (no bit9), no axis-break marker, and seq wraps at 8 bits. Frame-loss statistics are only exact on 1.5.0, where seq is a real u16 and increments only on successful sends.
- **1.5.0 semantic changes** (M3/M8/L4):
  - Emergency-stop/EMERGENCY latch exits **only through [reset]**. [Disable] no longer clears it.
  - Motion commands while disabled return `ERR 0x03` (not a fake ACK); the log shows "rejected by firmware: not ready/not enabled".
  - Enable-latch rejections return `ERR 0x06` (reset first; retrying does not help), distinguished from the retryable 0x03. The GUI enable retry logic retries only 0x03.
  - The monitor page adds an "axis break" (red) status column, driven directly by the firmware G7 per-axis latch bitmap instead of inferring it from err.

## Firmware 1.5.1 changes (2026-09-08)

- Control rate 400→300 Hz (classic CAN at 1 Mbit/s: bus load ~72%→~54%); the disabled standby probe drops to 100 Hz (standby load ~72%→~18%). The host tool does not notice: the state stream stays at 100 Hz and watchdog/staleness timing is unchanged.
- **Speed semantics (L5 governor).** The control-page slider is a global ceiling; the effective speed is `min(move_j sp, slider)`. HOME no longer silently rewrites the global speed. The firmware explicitly rejects `sp>1.0` on move_j/move_p with `ERR 0x02` (unit trap: sp is a 0..1 fraction, so passing 30 is not full speed).
- KIN_BENCH replies include a LINK diagnostic line with four link counters: crc/ovf/rfdrop/txfail.

## Known limits

- Frame loss accumulates only on the **receive** side (seq differencing). The firmware pushes at 100 Hz and there is no ACK state stream.
- Plot data at 100 Hz goes into a ring buffer (last 30 s); plotting redraws at 30 Hz without decimation.
- The first version has no automatic reconnect. Reconnect manually after going offline.
