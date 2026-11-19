"""tuning_guide 纯内容测试 —— 公式/速查表/读前须知/ff 位, 无需 Qt。

公式语义以固件 litearm-stm32 master 源码为准 (law.c / control_loop.c /
litearm.h FF_* / defaults.c); 本测试只做文案关键段一致性与结构非空检查。
"""
import pytest

from litetool import param_catalog as C
from litetool import tuning_guide as G


def test_formula_key_segments_present():
    assert "τ_joint" in G.FORMULA_TEXT
    assert "PD_j" in G.FORMULA_TEXT
    assert "kp_j·(q_d − q)" in G.FORMULA_TEXT or "kp" in G.FORMULA_TEXT
    assert "clamp(τ, ±tau_max)" in G.FORMULA_TEXT
    assert "gs_j·G_j(q)" in G.FORMULA_TEXT
    assert "is_j·[M(q)·q̈ + C(q,q̇)·q̇]_j" in G.FORMULA_TEXT
    assert "fc0_j·max(tanh(q̇_d/ε),0)" in G.FORMULA_TEXT
    assert "friction_model=1" in G.FORMULA_TEXT and "friction_model=0" in G.FORMULA_TEXT
    assert "friction_j·tanh(e/fric_db)" in G.FORMULA_TEXT
    assert "±i_max" in G.FORMULA_TEXT


def test_symbol_map_references_ui_and_gs_baseline():
    symbols = [s for s, _ in G.SYMBOL_MAP]
    assert "gs_j" in symbols and "is_j" in symbols and "kp_j / kd_j" in symbols
    assert any("gs" in s and "gravity_scale" in s for s in symbols) or any(
        "gravity_scale" in d for _s, d in G.SYMBOL_MAP)
    assert any(G.GS_BASELINE in d for _s, d in G.SYMBOL_MAP)
    assert all(s and d for s, d in G.SYMBOL_MAP)


def test_read_first_notice_nonempty():
    assert len(G.READ_FIRST) >= 5
    assert all(x for x in G.READ_FIRST)
    assert any("RAM" in x for x in G.READ_FIRST)
    assert any("Flash" in x or "固化" in x for x in G.READ_FIRST)
    assert any("enable" in x or "使能" in x for x in G.READ_FIRST)


def test_symptom_table_rows_nonempty_and_cover_key_symptoms():
    assert len(G.SYMPTOM_TABLE) >= 6
    for symp, act, note in G.SYMPTOM_TABLE:
        assert symp and act.strip(), (symp, act)
        assert note
    joined = "".join(r[0] for r in G.SYMPTOM_TABLE)
    for kw in ("下垂", "残差", "抖", "回冲", "饱和", "一顿"):
        assert kw in joined, kw


def test_build_html_has_sections():
    html = G.build_guide_html()
    assert html.startswith("<html>") and html.endswith("</html>")
    for frag in ("动力学 / 控制律公式", "读前须知", "症状 → 建议参数",
                 "ff_mask 位含义脚注", G.GS_BASELINE, "<table"):
        assert frag in html, frag
    # 速查表首列全部渲染进 HTML
    for symp, _act, _note in G.SYMPTOM_TABLE:
        assert symp in html


def test_ff_footnote_rows_match_catalog_bits():
    html = G.build_guide_html()
    for _i, (bit, name, label) in enumerate(C.FF_BITS):
        assert name in html
        assert label in html
    # detail 表为 9 行 (不含标题)
    assert G.FF_BITS_ROWS == [(_b, n, _l) for _b, n, _l in C.FF_BITS]


# ---------------- 数值文案必须跟随固件真源 (2026-09-13) ----------------
def test_gs_baseline_matches_firmware():
    """出厂 gs 基线以固件 defaults.c 为准 (旧值 [1,0.93,0.88,0.87,1,1,1] 是换辨识惯量前的老口径)。"""
    import ast

    from litetool import firmware_defaults as FD

    if FD.find_firmware_dir() is None:
        pytest.skip("未找到 litearm-stm32 固件仓")
    fw = FD.load_firmware_defaults()
    assert ast.literal_eval(G.GS_BASELINE) == [j["gravity_scale"] for j in fw["joints"]]
    # 同一常量必须被指南与参数目录共同使用 (避免两处各写一份再漂移)
    assert G.GS_BASELINE == C.GS_BASELINE
    assert G.GS_BASELINE in C.JOINT_BY_KEY["gravity_scale"].hint


def test_no_stale_cad_mass_scale_in_texts():
    """模型源已是辨识模型 (litearm_id.urdf), 旧的 "CAD 质量 ×1.8635" 口径不得再出现。"""
    texts = [G.FORMULA_TEXT, G.__doc__ or ""] + [d for _s, d in G.SYMBOL_MAP]
    texts += [C.JOINT_BY_KEY["gravity_scale"].hint, C.JOINT_BY_KEY["gravity_scale"].detail]
    texts += [p.detail for p in C.JOINT_PARAMS]
    blob = "\n".join(texts)
    assert "1.8635" not in blob, "调参文案仍引用已废弃的 CAD 质量口径 ×1.8635"
    assert "0.93" not in blob and "CAD 质心残差" not in blob, "调参文案仍有废弃的 gs 基线"
