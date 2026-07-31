# -*- coding: utf-8 -*-
"""主题系统测试：注册表完整性、圆角解析、主题应用、配置默认值。"""

import pytest

import card_window as cw
import themes
from alias_store import AliasStore
from app_config import AppConfig
from card_window import FONT_SIZE_MIN

BALL_KEYS = {"grad", "text", "flash_added", "flash_removed"}
CARD_KEYS = {
    "panel", "border", "line", "title", "count", "text", "muted",
    "row_bg", "row_border", "row_selected_bg", "row_selected_border",
    "notify_added", "notify_removed",
}
STYLE_KEYS = {"radius_bonus", "radius_min", "border_alpha", "gradient"}


def test_registry_completeness():
    assert len(themes.BALL_THEMES) >= 4, "至少 4 组悬浮球主题"
    assert len(themes.CARD_THEMES) >= 4, "至少 4 组卡片主题"
    assert set(themes.CARD_STYLES) == {"卡片", "气泡", "极简"}
    for name, t in themes.BALL_THEMES.items():
        assert set(t) == BALL_KEYS, f"球主题缺键: {name}"
        assert len(t["grad"]) == 2
    for name, t in themes.CARD_THEMES.items():
        assert set(t) == CARD_KEYS, f"卡片主题缺键: {name}"
        assert len(t["panel"]) == 3
    for name, s in themes.CARD_STYLES.items():
        assert set(s) == STYLE_KEYS, f"卡片风格缺键: {name}"


def test_resolve_radius_card_style():
    assert themes.resolve_radius(12, "卡片") == 12
    assert themes.resolve_radius(0, "卡片") == 0  # 直角


def test_resolve_radius_bubble_min():
    # 气泡风格保证最小 18
    assert themes.resolve_radius(0, "气泡") == 18
    assert themes.resolve_radius(12, "气泡") == 18
    assert themes.resolve_radius(20, "气泡") == 24  # 钳制到 24


def test_resolve_radius_minimal_and_clamp():
    assert themes.resolve_radius(12, "极简") == 8
    assert themes.resolve_radius(24, "卡片") == 24
    assert themes.resolve_radius(99, "卡片") == 24
    assert themes.resolve_radius("abc", "卡片") == 0  # 非法输入


def test_fallback_for_unknown_names():
    assert themes.ball_theme("不存在")["grad"] == themes.BALL_THEMES["深空蓝"]["grad"]
    assert themes.card_theme("不存在")["panel"] == themes.CARD_THEMES["深色"]["panel"]
    assert themes.card_style("不存在")["radius_bonus"] == 0


def test_config_defaults_include_appearance(tmp_path):
    cfg = AppConfig(path=tmp_path / "config.json")
    assert cfg.ball_theme == "深空蓝"
    assert cfg.card_theme == "深色"
    assert cfg.card_style == "卡片"
    assert isinstance(cfg.card_radius, int)
    assert 0 <= cfg.card_radius <= themes.RADIUS_MAX
    assert cfg.font_family == ""
    assert cfg.font_size == 12
    assert cfg.font_color == ""
    assert cfg.card_width == 320


def test_apply_theme_font_and_color(qapp, tmp_path):
    config = AppConfig(path=tmp_path / "config.json")
    config.set("font_size", 14)
    config.set("font_color", "#FF0000")
    config.set("font_family", "微软雅黑")
    card = cw.CardWindow(AliasStore(path=tmp_path / "aliases.json"), config)
    qss = card.styleSheet()
    assert "font-size: 16px" in qss      # 标题 = 字号 + 2
    assert "font-size: 13px" in qss      # 计数 = 字号 - 1
    assert "#FF0000" in qss              # 颜色覆盖
    assert card.font().family() == "微软雅黑"


def test_apply_theme_card_width(qapp, tmp_path):
    config = AppConfig(path=tmp_path / "config.json")
    config.set("card_width", 400)
    card = cw.CardWindow(AliasStore(path=tmp_path / "aliases.json"), config)
    card.show()
    qapp.processEvents()
    assert card.width() == 400
    assert card.minimumWidth() == 400  # setFixedWidth 锁定


def test_apply_theme_generates_theme_qss(qapp, tmp_path):
    config = AppConfig(path=tmp_path / "config.json")
    config.set("card_theme", "云白")
    config.set("card_radius", 0)  # 直角
    aliases = AliasStore(path=tmp_path / "aliases.json")
    card = cw.CardWindow(aliases, config)
    qss = card.styleSheet()
    assert "rgba(245,247,250" in qss          # 云白面板色
    assert "border-radius: 0px" in qss        # 直角生效
    assert card._row_normal_qss and card._row_selected_qss
    assert card._notify_colors is config and False or card._notify_colors["panel"] == (245, 247, 250)


def test_apply_theme_bubble_style(qapp, tmp_path):
    config = AppConfig(path=tmp_path / "config.json")
    config.set("card_style", "气泡")
    config.set("card_radius", 0)
    card = cw.CardWindow(AliasStore(path=tmp_path / "aliases.json"), config)
    qss = card.styleSheet()
    assert "border-radius: 18px" in qss       # 气泡最小半径
    assert "qlineargradient" in qss           # 气泡渐变背景


def test_settings_dialog_populates_themes(qapp, tmp_path):
    from settings_dialog import SettingsDialog

    config = AppConfig(path=tmp_path / "config.json")
    dialog = SettingsDialog(config)
    assert dialog._ball_combo.count() == len(themes.BALL_THEMES)
    assert dialog._card_combo.count() == len(themes.CARD_THEMES)
    assert dialog._style_combo.count() == len(themes.CARD_STYLES)
    assert dialog._radius_slider.maximum() == themes.RADIUS_MAX
    dialog.deleteLater()


def test_settings_dialog_change_applies_and_persists(qapp, tmp_path):
    from settings_dialog import SettingsDialog

    config = AppConfig(path=tmp_path / "config.json")
    previewed = []
    dialog = SettingsDialog(config, on_preview=lambda: previewed.append(1))
    dialog._ball_combo.setCurrentText("黑金")
    assert config.ball_theme == "黑金"
    assert previewed  # 预览回调被触发
    dialog._radius_slider.setValue(0)
    assert config.card_radius == 0
    assert config.card_style == "卡片"
    # 持久化：重新加载仍保留
    reloaded = AppConfig(path=tmp_path / "config.json")
    assert reloaded.ball_theme == "黑金"
    assert reloaded.card_radius == 0
    dialog.deleteLater()


def test_settings_dialog_typography_controls(qapp, tmp_path):
    from settings_dialog import SettingsDialog

    config = AppConfig(path=tmp_path / "config.json")
    dialog = SettingsDialog(config)
    # 字体：可编辑 + 有「跟随系统」项（不依赖系统已装字体）
    assert dialog._font_combo.isEditable()
    assert dialog._font_combo.itemData(0) == ""
    assert dialog._font_combo.count() >= 1
    # 字号 / 宽度范围
    assert dialog._font_size_spin.minimum() == FONT_SIZE_MIN
    assert dialog._font_size_spin.value() == 12
    assert dialog._width_spin.minimum() == 240
    assert dialog._width_spin.maximum() == 480
    assert dialog._width_spin.value() == 320
    # 无自定义颜色时「跟随主题」不可点
    assert not dialog._color_reset.isEnabled()
    dialog.deleteLater()


def test_settings_dialog_typography_apply(qapp, tmp_path):
    from settings_dialog import SettingsDialog

    config = AppConfig(path=tmp_path / "config.json")
    previewed = []
    dialog = SettingsDialog(config, on_preview=lambda: previewed.append(1))
    dialog._font_size_spin.setValue(16)
    assert config.font_size == 16
    dialog._width_spin.setValue(360)
    assert config.card_width == 360
    # 手输自定义字体名（可编辑下拉框）
    dialog._font_combo.setEditText("微软雅黑")
    assert config.font_family == "微软雅黑"
    assert len(previewed) >= 3
    dialog.deleteLater()
