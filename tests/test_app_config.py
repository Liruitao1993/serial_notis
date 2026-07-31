# -*- coding: utf-8 -*-
"""AppConfig 配置测试。"""

import json

import pytest

from app_config import AppConfig, DEFAULTS


def test_defaults(tmp_path):
    cfg = AppConfig(path=tmp_path / "config.json")
    assert cfg.notify_lifetime_ms == 20000
    assert cfg.auto_show_card is True
    assert cfg.notify_on_remove is True


def test_set_persists(tmp_path):
    path = tmp_path / "config.json"
    cfg = AppConfig(path=path)
    cfg.set("notify_lifetime_ms", 5000)
    cfg.set("auto_show_card", False)

    reloaded = AppConfig(path=path)
    assert reloaded.notify_lifetime_ms == 5000
    assert reloaded.auto_show_card is False


def test_unknown_key_raises(tmp_path):
    cfg = AppConfig(path=tmp_path / "config.json")
    with pytest.raises(KeyError):
        cfg.set("nonsense", 1)
    with pytest.raises(AttributeError):
        _ = cfg.nonsense


def test_type_coercion(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"notify_lifetime_ms": "abc", "auto_show_card": "false"}),
        encoding="utf-8",
    )
    cfg = AppConfig(path=path)
    assert cfg.notify_lifetime_ms == DEFAULTS["notify_lifetime_ms"]  # 非法值回退
    assert cfg.auto_show_card is False  # 字符串布尔正确解析


def test_corrupt_file_uses_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{{{{", encoding="utf-8")
    cfg = AppConfig(path=path)
    assert cfg.notify_lifetime_ms == 20000
