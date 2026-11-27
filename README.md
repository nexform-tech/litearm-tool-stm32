English | [简体中文](README.zh-CN.md)

# LiteArm Tool STM32

Desktop host tool for the LiteArm motion-control firmware (`litearm-stm32`, STM32H723).

**All interaction goes through [`litearm-python`](https://github.com/nexform-tech/litearm-python)** —
the tool no longer carries its own protocol implementation; it only provides the UI, the
operator-intent safety layer, and the tuning ledger. Transport is the onboard composite USB
CDC port (gs_usb + CDC VCP, VID:PID `1d50:606f` → `/dev/ttyACM0`).

Requires `litearm-python >= 2.4.0` (firmware 1.12.3 fault-detail-on-demand query).

## Architecture

```text
GUI main thread ──submit(fn)──▶ task queue ──▶ SdkWorker thread ──▶ litearm.Arm ──▶ USB CDC
     ▲                                             │
     └────── 20 Hz read worker.state  ◀────────────┘   100 Hz state hook → plot ring buffer
```

**The serial port has exactly one owner.** `litearm.Arm` is designed for a single consumer:
`_Ack.expect` / `pump` / `_read_status` all pull frames from the same port. If the GUI polls
state while also sending commands (two reader threads), the state poll eats the command's ACK —
which shows up as a **random** "no reply (timeout)".

So every SDK call is funnelled through the `SdkWorker` thread in `litetool/sdk_worker.py`:
when idle it calls `get_state(refresh=True)` (the firmware pushes at 100 Hz, so this call is
itself the 100 Hz state source); when a task arrives it runs the task. The two are serialized.
The SDK is **unmodified**.

**The single private coupling** (guarded by `tests/test_sdk_hook.py`): wrapping
`Arm._a._on_status` lets frames consumed inside blocking calls such as `movej` reach the plot.
Without it the plot would freeze during motion — exactly when the waveform matters most. If the
hook cannot be attached, `_attach_state_hook()` **raises** instead of degrading silently.

## UI

Top bar (port / connect / firmware version / motion unlock / ⛔ emergency stop) + a **persistent
status strip** (mode / enabled / six safety flag lamps / seq / dropped frames / frame rate) +
three navigation groups on the left + a collapsible log at the bottom.

| Group | Page | What it does |
| --- | --- | --- |
| Monitor | **Overview** | Per-joint state table + 100 Hz three-pane linked plot (the old "Monitor" and "Plot" pages merged; one click enlarges the plot; CSV export of the selected joints with units, temperatures and drive error codes) |
| | **Capture** | Firmware 300 Hz control-tick capture: record / progress / read-back preview / export raw bytes / export the parsed samples as CSV |
| | **Faults** | Per-axis fault reasons (`0x51` on demand when `flags` bit11 is set) + flags + `drop_hold`; all 7 axes on one screen, reason and action in separate columns |
| Operate | **Machine** | Enable / disable / reset / clear faults / home / global speed / park / read state / reset reason |
| | **Joints** | `move_j` / `move_js` / single-joint `move_mit` / whole-arm `move_mit_all`; one-click ready pose `[0, 0.5, 0, -1, 0, 0.6, 0]` (trimmed/padded to the axis count) |
| | **Cartesian** | Read TCP / `ik` solve / `move_p` |
| | **Zero-G** | Hand-guiding (keep-alive is maintained by the SDK background thread; this tool sends no heartbeat frames) |
| Tuning | **Parameters** | Joint parameters and the 0x26/0x27/0x28 feed-forward family: read back / edit and send / ff_mask / batch import-export / persist to flash / factory reset |
| | **Tuning guide** | Formulas and symbol mapping, read-before-you-start notes, symptom→parameter quick table, expandable per-parameter details |
| | **Diagnostics** | `KIN_BENCH` self-test, reset reason, link counters (CRC / queue full / CAN failures / control-tick overruns), error-code text, diagnostics bundle |

## Coverage: SDK public surface → UI entry

Every public method of `litearm-python` v2.4.0+ has an entry point (`tests/test_sdk_hook.py`
watches whether the SDK side of this table still exists; `tests/test_pages_sdk.py` watches
whether the UI is actually wired to it).

| SDK | UI entry |
| --- | --- |
| `connect` / `close` / `reconnect` | Top bar connect / disconnect (reconnect = disconnect then connect) |
| `firmware` / `n` / `last_reset_reason` | Top-bar firmware version, Machine page, Diagnostics page |
| `enable` / `disable` / `reset` / `clear_faults` | Machine page (the last three ask for confirmation) |
| `emergency_stop` | Top bar ⛔ emergency stop (**queue-jumping** path, see "Safety model") |
| `home` | Machine page [Home] (confirmation + Δq hint) |
| `set_speed` | Machine page global speed (0..100 integer percent) |
| `park` / `set_motion_mode` | Machine page [Park]. The firmware only recognizes `mode=0` (park); other values return ACK without changing the mode, so no useless knob is exposed |
| `movej` | Joints page (Δq confirmation above the threshold) |
| `move_js` | Joints page, single shot (the page states the 0.1 s watchdog semantics) |
| `send_mit` / `send_mit_all` | Joints page, single joint / whole arm, single frame |
| `move_p` | Cartesian page (pose-magnitude confirmation above the threshold) |
| `ik` | Cartesian page [Solve IK] (computes only, never moves; the seed may be the current measured angles) |
| `get_tcp` | Cartesian page [Read current TCP pose], Overview |
| `get_state` | 100 Hz continuous feed (status strip + overview table + plot) |
| `get_status_now` | Machine page [Read state GET_STATUS] |
| `get_state().fault_detail_available` / `get_fault_detail()` | Faults page (query `0x51` once when bit11 is set; older firmware shows "reason unavailable") |
| `describe` / `describe_fault` / `describe_exc` | Faults page / log: error code → title + cause + action; unregistered codes are never blank |
| `zero_g` / `zero_g_start` / `zero_g_stop` / `zero_g_active` / `zero_g_error` | Zero-G page (buttons follow the **actual** state; a broken keep-alive shows its reason) |
| `set_ff_mask` / `get_ff_mask` / `ff_preset` | Parameters page ff_mask checkbox group |
| `set_ff_vec` / `get_ff_vec` | Parameters page per-joint vectors (1.12.3: 1..11, 15, 16; 12..14 removed) |
| `set_ff_scalar` / `get_ff_scalar` | Parameters page global scalars (1.12.3: 1..8, 11, 17, 18; 10 and 12..16 removed) |
| `set_gravity_scale` / `set_inertia_scale` | Parameters page `gravity_scale` / `inertia_scale` vectors (named wrappers over the same 0x26 items 7/8) |
| `set_payload` / `set_gravity_vector` | Parameters page `payload_mass` / `payload_com` / `gravity` scalars (0x28 items 4/5/6) |
| `save_params` | Parameters page [Persist to flash] (confirmation; the arm must be disabled) |
| `params.get_joint_param` / `all_joint_params` | Parameters page [Refresh current] |
| `params.set_joint_param` / `set_joint_limits` | Parameters page per-joint send (limits are sent as a pair) |
| `params.reset_factory` | Parameters page [Factory reset] |
| `log.start` / `stop` / `reader` / `capture` / `dump` | Capture page |
| `LogReader.total` / `wait_for` / `read_all` / `iter_chunks` / `samples` | Capture page progress / read-back preview / full capture |
| `diag.kin_bench` | Diagnostics page [Run KIN_BENCH self-test] |
| `find_cdc_port` | Top-bar port drop-down (`litetool/ports.py` also lists every candidate; the onboard CDC port is always first) |

## Safety model (important)

**The firmware is the authority for every hard protection**: slew limits, soft limits, NaN and
invalid-value rejection, watchdog fail-soft, and the emergency-stop backstop all live in the
STM32 and do not depend on the host tool being online. This tool does **not** duplicate them.

The tool covers only the operator-intent layer the firmware cannot enforce:

1. **Motion unlock (one global switch).** After ticking "the arm is clear and the emergency stop
   is reachable" in the top bar, the Machine [Home] / Joints / Cartesian / Zero-G pages are
   released. **Disconnect, emergency stop, FAULT/latch, and reset** all retract the unlock.
   Ticking it while disconnected is refused.
   *Why one global switch instead of one per page*: the risk is "sending a large motion by
   mistake", which belongs to the command, not to a page; four independent switches only train
   people to tick them all reflexively.
   **The gate is enforced in `MainWindow._motion_denied()`, not in each page's `setEnabled`** —
   greyed-out buttons are only UX; every path that can reach a handler (a programmatic emit,
   a page that forgot to disable one widget, a shortcut) must be blocked here.
2. **Δq confirmation.** For `movej` / `move_js` / `move_mit` / `move_mit_all`, when the target
   differs from the current position by more than `confirm_threshold` (default 0.5 rad), every
   joint delta is listed and confirmed. `move_p` additionally confirms pose magnitude
   (0.05 m position / 0.30 rad orientation).
   **Without a baseline the command is refused, not waved through**: when no state frame has
   arrived or TCP has never been read, the input boxes still hold defaults — exactly the moment
   a slip is most likely. `move_p` automatically reads TCP once when no baseline exists.
3. **Always-available emergency stop.** The red top-bar button goes through
   `SdkWorker.emergency_now()`: the GUI thread **writes the frame directly**, without queueing
   and without waiting for an ACK. An in-flight `movej` can occupy the owner thread for over ten
   seconds, so the emergency stop must bypass the queue. That path **writes only, never reads**,
   so it is neither blocked by an in-flight command nor competing with the owner thread for
   frames.
   The cost is that it **cannot** claim "disabled": a frame sent is not a firmware action. The UI
   text strictly distinguishes "emergency-stop frame sent — visually confirm the arm has
   stopped" from "emergency stop NOT sent — use the hardware stop or cut power now".
   The emergency stop also **drops queued commands** (its meaning is "stop", not "finish what is
   in hand") and **tears down the zero-G keep-alive** (otherwise that thread would keep sending
   empty frames every 40 ms while the UI still says "dragging").
   The one in-flight command cannot be pre-empted, but its result will be rejected by the
   firmware's EMERGENCY latch — the arm will not actually move.
4. **Emergency stop / fault automatically re-locks**, and `reset` re-locks as well (an old
   unlock does not survive an emergency stop).
5. Parameters page: **[Refresh current] must succeed** before anything can be sent; writing the
   control law while the arm is enabled asks for confirmation; before a limit write every joint's
   current q is checked against the new [q_min, q_max]; persisting to flash, batch apply, and
   ff_mask changes all ask for confirmation.
   **Parameter items follow the board's measured capability**: [Refresh current] probes
   `0x2B`/`0x2C` item by item; an item the board rejects with `ERR{cmd,0x02}` is hidden and
   excluded from sending. The UI no longer guesses a firmware's feature set from a local catalog
   (the catalog supplies labels/ranges; the board answers whether an item exists). Timeouts and
   link errors are still reported as faults, never mistaken for "the board lacks this item".
6. Every motion page states its "single frame / single shot" semantics. Under the firmware's
   0.1 s watchdog, continuous `move_js` servoing requires the caller to resend at ≥10 Hz; this
   tool provides no continuous stream.

## Usage

```bash
pip install -e ../litearm-python     # interaction layer (>= 2.4.0)
pip install -r requirements.txt
python3 main.py                       # a normal user is enough if the port is in the dialout group
```

After launch: choose the port in the top bar → connect → the firmware version appears in the top
bar (for example `Litearm1.12.3-7J`). The connection checks the firmware naming convention
(minimum 1.5.0). The overview page refreshes from the 100 Hz stream; a 7-joint arm and a 1-joint
bench are detected from the status-frame length.

Configuration lives in [config.yaml](config.yaml) (interaction settings only, no limits).

**Single instance only.** A second launch does not open the serial port; it brings the running
window to the front and exits. The lock is a local socket (`QLocalServer`), so a crash is cleaned
up by the next launch. The second process shows a short message explaining why it is exiting.

## Code organization

```text
main.py                 Entry point (thin shell, forwards to litetool.app:main)
litetool/
  app.py                Launch entry (`python3 -m litetool` / the `litearm-tool` command)
  instance.py           Single-instance lock (local socket; second launch focuses the window)
  sdk_worker.py         ★ the only thread that owns pa.Arm + task queue + state hook
  params_io.py          Parameter read/write shape layer over pa.Arm (pages want (ok, code))
  diagnostics.py        Error-code text / diagnostics bundle / link-counter summary
  model_io.py           HYY model and parameter import/export
  hyy_config.py         HYY configuration parsing
  ports.py              Port enumeration (onboard CDC first)
  plot_model.py         Thread-safe state ring buffer (with measured frame rate)
  checks.py             Intent-layer confirmation (Δq / pose magnitude; the only "safety" module)
  param_catalog.py      Tuning catalog mirror + schema/diff/ff_mask + role/hint/detail
  tuning_guide.py       Tuning-guide content (formulas / symbol mapping / symptom table)
  firmware_defaults.py  Parses firmware defaults.c (source of truth for presets/ and consistency checks)
  settings.py           config.yaml merge (type + range validation)
  csv_export.py         CSV writer for the plot window and 300 Hz capture (units in headers)
  gui/
    bridge.py           Cross-thread Qt signal bridge (log / task result / online state)
    widgets.py          Log panel / persistent status strip / joint table / banner / left navigation
    pages/
      overview_page.py  Overview      capture_page.py  Capture
      fault_page.py     Faults        machine_page.py  Machine
      joint_page.py     Joints        cart_page.py     Cartesian
      zerog_page.py     Zero-G        params_page.py   Parameters
      guide_page.py     Tuning guide  diag_page.py     Diagnostics
      installation_page.py  Installation direction
      common.py         Shared pose/joint input widgets
      plot_pane.py      Three-pane linked plot component
    main_window.py      Main-window assembly + command gate (Δq / unlock / emergency flows)
templates/params_example.yaml   Import template with unit and range comments
presets/                        Factory / SE1 friction presets
tests/                          Offline tests (no hardware required)
```

**Thread model**: one SDK owner thread (the only one touching `Arm`) and the GUI main thread
(20 Hz reads a snapshot to refresh the UI, 30 Hz redraws the plot). The parameters and capture
pages no longer create their own threads; everything is `submit`ted to the owner thread.

## Tests

```bash
python3 -m pytest          # 429 passed (all offline, no hardware required)
```

| File | What it guards |
| --- | --- |
| `test_sdk_worker.py` | Port ownership / task queue / state hook / offline detection / dropped-frame counters / **emergency-stop bypass** |
| `test_sdk_hook.py` | The tool's private coupling to the SDK (`_a._on_status`, `_write_cmd(guarded=)`) and the public surface |
| `test_pages_sdk.py` | Page → SDK **wiring** (which SDK call each button really reaches) |
| `test_params_io.py` | Parameter read/write shape layer (including ERR code passthrough) |
| `test_params_flow.py` | Parameters-page safety gates (no send before refresh / enabled-state confirmation / out-of-range limit rejection) |
| `test_safety_ui.py` | The emergency stop never lies / dangerous commands confirm twice / unlock retracts automatically / Δq confirmation |
| `test_fault_query.py` | bit11 → `0x51` trigger / de-duplication / invalidation after clearing faults |
| `test_fault_display.py` | Fallback when an older firmware leaves `fault_reason` empty |
| `test_fault_page.py` | Faults-page layout and all 7 axes on one screen |
| `test_diagnostics.py` | Error-code text and the diagnostics bundle |
| `test_gui_smoke.py` | Build and layout regression (3 navigation groups, 9 pages, 1J bench, motion pages locked by default) |
| `test_checks.py` `test_plot_model.py` `test_param_catalog.py` `test_settings.py` `test_tuning_guide.py` | Intent layer and pure data layer |
| `test_preset_sync.py` | Field-by-field comparison of `presets/` and `templates/` against firmware `defaults.c` (runs when the firmware tree is present; `LITEARM_FW_DIR` can point to it) |

## On-hardware acceptance checklist (STM32 + motors/CAN online)

> Run in order on first setup or after a change. If any step differs from the expected result,
> stop and investigate. Do not skip steps.

1. **Read-only connection** (disabled, safe):
   - [ ] Choose the port in the top bar → connect → the status dot turns green "● Online" and the firmware version appears
   - [ ] The persistent status strip shows mode=INIT, frame rate ≈ 100 Hz, seq increasing with no jumps (dropped frames ≈ 0)
   - [ ] The overview table shows q/dq/tau/temperature/err per joint; unplug the serial cable → red "● Offline", all command buttons disabled
   - [ ] Press the emergency stop while disconnected → it must clearly say "emergency stop NOT sent", never "disabled"
2. **Plot**: the overview scrolls with the state; the J1–J7 channel checkboxes switch traces; "Freeze" pauses and "Clear" redraws; [Enlarge plot] collapses the state table. **Send one `movej` and confirm the plot keeps updating during the motion** (state hook).
3. **Basic control** (the magnets will engage; support the arm):
   - [ ] [Home] is not clickable before unlocking; it becomes clickable after ticking the unlock
   - [ ] `enable` → ACK; `disable` / clear faults / reset / global speed take effect
   - [ ] Emergency stop → mode=EMERGENCY, FAULT lamp on; the unlock is retracted; `enable` is refused; `reset` → back to INIT, all lamps off, still locked
4. **Motion commands** (start slow, sp=0.1):
   - [ ] `move_j` to current + 0.1 rad → small motion, arrives
   - [ ] `move_j` with a delta > 0.5 rad → Δq confirmation; cancelling sends nothing
   - [ ] [Ready pose] fills the target with `[0, 0.5, 0, -1, 0, 0.6, 0]` and sends it through the same confirmation
   - [ ] Cartesian page [Read current TCP pose] returns a value; [Solve IK] returns 7 numbers; a small `move_p` arrives
   - [ ] Joints page `move_mit`, single frame, single joint, small magnitude
5. **Zero-G**: the arm can be hand-dragged after entering; the button and the status strip agree; after exit the joints return inside the soft limits; unplugging the cable shows "keep-alive lost" and resets the button
6. **Capture**: set n=300 → [Start recording] → wait 1 s → [Progress] should show ~300 ticks → [Read back and preview] draws three curves → [Export raw bytes…] writes a file
7. **Diagnostics**: [Run KIN_BENCH self-test] prints the raw text and counters (crc/rfd/txf, etc.)
8. **Parameters**: see the next section
9. **Faults page** (create a controlled fault per the acceptance plan): state-frame bit11=1 → the Faults page automatically shows the per-axis reason; clearing faults clears the reasons. Older firmware (no `0x51`) shows "reason unavailable", which does not mean "no fault".
10. **Abnormal paths**:
   - [ ] Click other buttons rapidly while a command is running → "busy", no concurrent sends
   - [ ] Enter an extreme value for `move_j` → the log shows the firmware ERR rejection, the arm does not move

## Parameter tuning page

The read commands `0x24` / `0x2B` / `0x2C` require firmware 1.5.x (parameter readback).

| Area | Write | Read | Notes |
| --- | --- | --- | --- |
| Joint control / limits | `0x22` kp/kd/tau_max, `0x23` q_min/q_max | `0x24` | Per joint |
| Per-joint vectors | `0x26` items 1..11 + 15/16 | `0x2B` | One 7-value group at a time; 12..14 removed in 1.11.0; 16=drag_gain (1.12.0) |
| Global scalars | `0x28` items 1..8 + 11 + 17,18 | `0x2C` | Includes payload_mass/gravity/friction_model/drag_db/hold_kp_gain; item 10 removed in 1.12.0 |
| ff_mask | `0x27` u32 | `0x2C` item 9 | Checkbox group |
| Factory reset | `0x36` param_reset (requires disabled) | — | Confirmation |
| Persist | `0x25` param_save (requires disabled) | — | Confirmation |

⚠ **Exact 1.12.3 item sets** (the tool displays what the board actually supports; it does not
guess from a local whitelist):

- `0x26`: **1..11, 15, 16** (12..14 removed)
- `0x28`: **1..8, 11, 17, 18** (item 9 is reserved for reading `ff_mask` via `0x2C`; 10 and 12..16 removed)
- `0x2B` / `0x2C` read paths use the same sets as their write counterparts

Usage:

1. Connect, open the **Parameters** page, and click [Refresh current]: `0x24×7` + `0x2B` item by
   item + `0x2C` item by item are read once and populate the table (unsupported items return
   `ERR{cmd,0x02}` and are skipped automatically).
2. Double-click a cell to edit. Yellow = changed but not sent; red = out of range or failed.
   Use [Send selected rows] (kp/kd/tau_max and q_min/q_max are sent as pairs) or [Send all].
   Every write waits for an ACK; failures are marked red and logged.
3. Global scalars use the spin boxes below the table; ff_mask uses the checkbox group.
   [Send global] sends them (changes are confirmed first).
4. Batch: use `presets/` or [Import YAML/JSON…] (the template
   `templates/params_example.yaml` documents units and ranges) → a **diff preview** shows every
   old→new cell → [Apply] sends all writes in order → optionally tick "persist to flash after
   sending" (a second confirmation; the arm must first be disabled on the Machine page).
   [Export current] reads everything back to YAML in the same shape as import, so re-importing
   the same file produces an empty diff (closed loop).
5. The status line shows the latest result, ACK, or ERR. Disconnect disables the page and shows
   a notice; reconnecting restores it.

**Factory baseline** (matching firmware `defaults.c`, guarded field by field by
`tests/test_preset_sync.py`): `kp=[400,400,300,300,50,50,50]`, `ff_mask=0x1BF` (= G + inertia +
Coriolis + friction + integral; see the bit definitions below). These two numbers are the most
easily stale copies — when the firmware changes, update this page and `presets/`.

The range mirror table lives in `litetool/param_catalog.py` (pure Python, no Qt, shared by tests,
YAML, and the UI). Values follow firmware `params.c` and `flash_store.c apply_loaded`.

- Per joint: kp[0,500] kd[0,5] tau_max[0.1,120] q_min/q_max[-15,15] (min<max)
  friction[0,50] ki[0,1000] i_max[0,100] wall_stiff[0,2000] wall_damp[0,50]
  wall_tau_max[0,50] gs/is[0,20] friction_v[0,20] fc0[0,50] fc1[-50,0]
  drag_gain[0,5] (per joint since 1.12.0, 0x26 item 16)
- Global: fric_db[1e-4,0.5] wall_margin[0,0.5] friction_slew[0,500]
  payload_mass[0,20] payload_com[-1,1]×3 gravity[-50,50]×3
  friction_model{0=v1 error direction, 1=v2 SE1 velocity direction, 2=drag} fric_v2_eps[1e-3,0.5]
  drag_db[0,0.5] (0=hard sign) wall_fw_kd[0,5] hold_kp_gain[0,5]
- ff_mask bits: MASTER=0x01 G=0x02 INERTIA=0x04 CORIOLIS=0x08 FRICTION=0x10
  INTEGRAL=0x20 WALL=0x40 QUANT=0x80 VELREF=0x100

## Firmware compatibility

- **State-frame dual layout**: ≤1.4.0 = `4+21N`; 1.5.0+ = `6+21N` (tail joint_fault u16 bitmap,
  flags bit9=enabled). `litearm._protocol` identifies the layout from the frame length.
- **The SDK enforces a version gate on connect**: below 1.5.0 it refuses to connect
  (`FirmwareMismatchError`).
- **1.5.0 semantic changes** (M3/M8/L4): the emergency-stop latch can only be cleared by
  [reset]; motion commands while disabled return `ERR 0x03`; enable latch rejections return
  `ERR 0x06` (reset first, retrying is useless); the overview state column adds "dropped axis"
  (red).
- **1.5.1 (2026-09-08)**: control frequency 400→300 Hz. The host is unaffected: the state stream
  is still 100 Hz. **Speed semantics (L5 governor)**: the Machine-page slider is a global cap;
  actual speed = min(move_j's sp, slider value). HOME no longer silently rewrites the global
  speed; `sp>1.0` is explicitly rejected by the firmware with `ERR 0x02`. The KIN_BENCH reply
  includes the LINK diagnostic line (crc/ovf/rfdrop/txfail).
- **1.5.2**: M6b motor timeout protection (`RID_TIMEOUT=9`). The monitor err column shows 13 as
  "timeout protection".
- **1.11.0 (2026-11-07)**: zero-G became a stateless law (RNEA + drag + wall); the spring-machine
  parameters `zg_kp/zg_kd/zg_damping/engage/vel_thr` were removed.
- **1.12.0 (2026-11-12)**: the drag-friction compensation ratio became **per joint**
  (`0x26` item 16); `0x28` item 10 (global `drag_gain`) was removed; flash moved to **v11**, so
  re-import the model and parameters after flashing.
- **1.12.1 (2026-11-12)**: zero-G exit / INIT hold now includes gravity feed-forward; no protocol
  change.
- **1.12.3 (2026-11-13)**: the state frame is back to **153 B**; `flags` bit11 = fault detail
  available; `CMD_GET_FAULT 0x51` added (7J = 13 B). The tool queries once when bit11 is set. The
  1.12.2 161 B transitional layout is still parsed by the SDK. Older firmware has no `0x51`, so
  the reason shows "unavailable".

## Known limits

- State-frame drops are counted only on the **receive side** (seq differences); the firmware
  pushes at 100 Hz and there is no ACKed state stream.
- Plot data enters the ring buffer at the full 100 Hz (the last `plot_window_s`); redraw runs at
  30 Hz without decimation.
- No automatic reconnect: reconnect manually after going offline (connecting retracts the motion
  unlock).
- The Parameters page always has 7 joint columns (`param_catalog.NUM_JOINTS`). On a 1J bench only
  J1 is readable; J2..J7 show "—", are locked for editing, and are excluded from sends (the
  firmware has one joint and the SDK's `_check_idx` rejects the rest).
- After a disconnect the tool no longer echoes the last frame: `SdkWorker` drops the state
  snapshot when offline/closed, leaving the status strip and table blank — showing stale telemetry
  as live data would make people believe the arm is still where it was.
- Fault reasons are queried only when `flags` bit11=1; older firmware (no `0x51`) shows "reason
  unavailable", which must not be read as "no fault".
- The UI's firmware-error display is the command name + generic code meaning (`describe`); the
  per-command detail is in the SDK exception's `err_reason` message (the `str(e)` of
  `CommandRejectedError`).
