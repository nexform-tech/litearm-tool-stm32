"""English tuning-guide content (generated translation)."""

FORMULA_TEXT = """τ_joint = PD_j + gs_j·G_j(q) + is_j·[M(q)·q̈ + C(q,q̇)·q̇]_j + τ_fric_j + τ_int_j + τ_wall_j(off by default) + τ_quant_j + τ_velref_j

PD_j      = kp_j·(q_d − q) + kd_j·(q̇_d − q̇)      (executed inside the motor's MIT mode, kp≤500, kd≤5)
G/M/C     = firmware built-in identified model (litearm_id.urdf: MDH geometry + identified inertia); gs/is = per-joint scaling knobs
τ_fric v2 = fv_j·q̇_d + fc0_j·max(tanh(q̇_d/ε),0) + fc1_j·max(−tanh(q̇_d/ε),0)   (friction_model=1, velocity direction, slew-limited)
v1(fallback) = friction_j·tanh(e/fric_db)      (friction_model=0, error direction)
τ_int     = ki_j·∫(q_d−q)dt, clamped to ±i_max
final law τ = clamp(τ, ±tau_max)   ← torque clamp = safety ceiling
"""

SYMBOL_MAP = [
    ("kp_j / kd_j", "kp/kd columns in the table (this joint's MIT stiffness/damping; PD is executed inside the motor)"),
    ("gs_j", "gs (gravity_scale) column in the table — per-joint gravity knob; measured baseline [1, 1, 1, 1, 1, 1, 1]"),
    ("is_j", "is (inertia_scale) column in the table; the FF_CORIOLIS bit decides whether C(q,q̇)·q̇ is included"),
    ("G_j(q) / M(q) / C(q,q̇)", "firmware built-in identified dynamics (litearm_id.urdf); compile-time constants, not changed directly from the GUI"),
    ("q_d / q̇_d", "desired position/desired velocity = trajectory-planning output (not measured values); that is why v2 friction does not pick up encoder noise"),
    ("q / q̇", "encoder-measured position/velocity"),
    ("fv_j / fc0_j / fc1_j", "friction_v / friction_fc0 / friction_fc1 columns in the table (v2, signs fv≥0, fc0≥0, fc1≤0)"),
    ("ε", "global friction_model v2: fric_v2_eps (tanh smoothing bandwidth)"),
    ("friction_j / fric_db", "v1 friction: friction column + global fric_db (only when friction_model=0)"),
    ("τ_int, ki_j, i_max_j", "integral term: ki column, output clamped to ±i_max (i_max in the table)"),
    ("τ_wall_j", "limit virtual wall (wall_stiff/wall_damp/wall_tau_max columns; FF_WALL off by default)"),
    ("τ_quant_j / τ_velref_j", "MIT quantization compensation (FF_QUANT) / velocity-reference torque (FF_VELREF), toggled via the ff_mask bits by default"),
    ("±tau_max", "per-joint tau_max column = torque clamp (safety ceiling; for saturation see the symptom table)"),
]

READ_FIRST = [
    "Changes go into RAM immediately: they take effect as soon as they are sent and do not touch Flash (after power-off the values revert to the factory/last persisted values).",
    "Only persisting makes them durable: param_save (0x25) writes Flash, and the firmware requires the joint to be in the disabled state (it rejects 0x04 in the enabled state).",
    "Writing while enabled = changing the control law live: writing kp/kd/tau/gs/is/friction/ff_mask etc. while the arm is enabled changes the motor commands immediately — the GUI asks for a second confirmation; before operating, make sure the surroundings are safe and the emergency stop is within reach.",
    "The firmware always backstops: NaN/out-of-range values are silently clamped or rejected (0x02); soft limits/velocity envelope/watchdog live in the firmware, and the GUI only warns rather than backstopping.",
    "Friction v2 is the factory default (friction_model=1, FF_FRICTION on): friction v1/the friction column has no effect under v2; keep it at 0.",
    "Tuning principle: change only 1~2 parameters at a time, in small steps (<10%), and record the old values each time so you can roll back.",
]

SYMPTOM_TABLE = [
    ("Droop at target / soft holding", "ki↑ (load-bearing axes); **check the mounting orientation first**",
     "Don't rush to adjust gs/is — under the identified model they should always stay at the baseline [1, 1, 1, 1, 1, 1, 1]; "
     "using them to compensate for droop amounts to disguising model error as a calibrated value. First go to the [Mounting orientation] page to check whether the current mounting orientation is correct; "
     "if a payload is attached, fill in payload_mass first"),
    ("Gravity compensation points the wrong way after side/inverted mounting", "change the gravity vector (0x28 item6)",
     "Choose the orientation on the [Mounting orientation] page (the buttons carry vector labels, so you don't have to guess which side 'side mount +y' means). "
     "**Must disable first** — since firmware 1.5.3 the armed state returns ERR{0x28,0x04}, "
     "and the three components are not atomic (mid-write the magnitude is 13.87 and the direction is off by 45°)"),
    ("Steady-state residual / square corners drawn inaccurately", "kp↑ (load-bearing axes), is↑", "kp is constrained by the 500 upper limit + the oscillation knee; step per axis in small increments"),
    ("Jerky motion at low speed (stick-slip)", "friction_v/fc0↑, lower the velocity envelope", "friction v2 is on by default; too large and it stutters through zero crossing"),
    ("Chatter / whine / high-frequency vibration", "kp↓, kd↑ (≤5)", "jerk/acc are compile-time constants; for the read-only hint see the comments in defaults.c"),
    ("Overshoot / recoil at target", "kd↑ (≤5)", "there are also S-curve constants in defaults.c (compile-time)"),
    ("τ always pinned at ±tau_max (saturation)", "lower the velocity envelope / reduce the load; do not add kp", "saturation = insufficient torque budget, not insufficient stiffness"),
    ("Tracking-error FAULT triggered", "lower speed_limit / vel_max", "the tracking-error limit lives in the firmware (0.25~0.35 rad depending on the axis)"),
    ("Reference for feel testing", "toggle friction_model 0/1, switch ff_mask bits", "see the ff_mask bit legend below"),
]

HEADINGS = {
    "title": "Formulas & tuning guide",
    "formula": "1) Dynamics / control-law formulas",
    "read_first": "2) Read before you start",
    "symptoms": "3) Symptom → suggested parameters",
    "ff_bits": "4) ff_mask bit legend",
    "note": "Explanation:",
    "footer": "The above is an empirical starting point; try in small steps and record each time; the authoritative clamps/limits always live in the firmware.",
    "symbols": "Symbol",
    "ui_param": "UI parameter",
    "symptom": "Symptom",
    "first_move": "First action",
    "remarks": "Remarks",
    "bit": "Bit",
    "value": "Value",
    "meaning": "Meaning",
}

EXPLANATION = (
    "PD and all feedforward terms are combined inside the firmware by the "
    "ff_mask enable bits; the factory default is ff_mask=0x1BF(447). The "
    "symbols map to UI parameters in the table below (hovering the matching "
    "row/column on the Parameters page shows the same explanation)."
)
