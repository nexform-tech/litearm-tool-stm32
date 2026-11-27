"""settings.py 测试 —— 配置合并/容错。"""

from litetool import settings


def test_defaults():
    s = settings.Settings.load(None)
    assert s.confirm_threshold == 0.5
    assert s.plot_window_s == 30.0


def test_load_overrides_known_keys(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("confirm_threshold: 0.3\ndefault_speed: 0.1\n", encoding="utf-8")
    s = settings.Settings.load(str(cfg))
    assert s.confirm_threshold == 0.3
    assert s.default_speed == 0.1
    assert s.plot_window_s == 30.0        # 未覆盖项保持默认


def test_load_missing_file_returns_defaults(tmp_path):
    s = settings.Settings.load(str(tmp_path / "nope.yaml"))
    assert s.confirm_threshold == 0.5


def test_load_ignores_unknown_key(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("unknown_option: 1\nconfirm_threshold: 0.2\n", encoding="utf-8")
    s = settings.Settings.load(str(cfg))
    assert s.confirm_threshold == 0.2
    assert not hasattr(s, "unknown_option")


def test_load_invalid_yaml_returns_defaults(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text(": : :\n", encoding="utf-8")
    s = settings.Settings.load(str(cfg))
    assert s.confirm_threshold == 0.5


def test_scene_lod_defaults_on_and_parses_bool(tmp_path):
    s = settings.Settings.load(None)
    assert s.scene_lod is True
    cfg = tmp_path / "c.yaml"
    cfg.write_text("scene_lod: false\n", encoding="utf-8")
    assert settings.Settings.load(str(cfg)).scene_lod is False


def test_scene_lod_rejects_non_bool(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("scene_lod: 1\n", encoding="utf-8")
    assert settings.Settings.load(str(cfg)).scene_lod is True


def test_scene_software_gl_defaults_off_and_parses_bool(tmp_path):
    assert settings.Settings.load(None).scene_software_gl is False
    cfg = tmp_path / "c.yaml"
    cfg.write_text("scene_software_gl: true\n", encoding="utf-8")
    assert settings.Settings.load(str(cfg)).scene_software_gl is True
