# -*- coding: utf-8 -*-
"""响应档位测试：参数表完整性、解析与回退、电池判定、设置与配置联动。"""

from types import SimpleNamespace

import pytest

import perf_profile
from app_config import AppConfig, DEFAULTS
from perf_profile import (
    AUTO_ON_AC,
    AUTO_ON_BATTERY,
    DEFAULT_PROFILE,
    PROFILE_NAMES,
    PROFILES,
    on_battery,
    resolve,
)

REQUIRED_KEYS = ("poll_ms", "event_delay_ms", "anim_fps")
# 除「自动」外的实际档位
CONCRETE_PROFILES = [name for name in PROFILE_NAMES if name != "自动"]


# ---------- 参数表 ----------


def test_profiles_complete():
    """每个档位都必须给出三项参数，且取值在合理区间。"""
    assert CONCRETE_PROFILES  # 至少有一个实际档位
    for name in CONCRETE_PROFILES:
        assert name in PROFILES, f"档位 {name} 缺少参数表"
        params = PROFILES[name]
        assert set(params) == set(REQUIRED_KEYS)
        assert 100 <= params["poll_ms"] <= 60000
        assert 0 <= params["event_delay_ms"] <= 2000
        assert 0 <= params["anim_fps"] <= 60


def test_profile_order_monotonic():
    """省电 → 均衡 → 敏捷：轮询间隔与事件复核延迟单调不增（越省电越慢）。"""
    power = PROFILES["省电"]
    balanced = PROFILES["均衡"]
    agile = PROFILES["敏捷"]
    assert power["poll_ms"] >= balanced["poll_ms"] >= agile["poll_ms"]
    assert power["event_delay_ms"] >= balanced["event_delay_ms"] >= agile["event_delay_ms"]
    # 省电档靠低帧率冻结动效来减少唤醒
    assert power["anim_fps"] < balanced["anim_fps"]


def test_default_profile_is_first_option():
    """默认档必须是设置里的第一项（「自动」），且配置默认值一致。"""
    assert DEFAULT_PROFILE == "自动"
    assert PROFILE_NAMES[0] == DEFAULT_PROFILE
    assert DEFAULTS["perf_profile"] == DEFAULT_PROFILE


# ---------- 解析 ----------


def test_resolve_auto_follows_power_source():
    """「自动」档：插电 → 均衡，电池 → 省电。"""
    ac_params, ac_name = resolve("自动", battery=False)
    battery_params, battery_name = resolve("自动", battery=True)
    assert ac_name == AUTO_ON_AC
    assert ac_params == PROFILES[AUTO_ON_AC]
    assert battery_name == AUTO_ON_BATTERY
    assert battery_params == PROFILES[AUTO_ON_BATTERY]
    # 电池下动效帧率不高于插电
    assert battery_params["anim_fps"] <= ac_params["anim_fps"]


@pytest.mark.parametrize("name", CONCRETE_PROFILES)
def test_resolve_explicit_profile_ignores_battery(name):
    """显式档位不受电源状态影响。"""
    params, actual = resolve(name, battery=True)
    assert actual == name
    assert params == PROFILES[name]


def test_resolve_unknown_falls_back(monkeypatch):
    """非法档位名不抛异常，回退到默认档并按电源状态解析。"""
    monkeypatch.setattr(perf_profile, "on_battery", lambda: False)
    params, actual = resolve("不存在的档位")
    assert actual == AUTO_ON_AC
    assert params == PROFILES[AUTO_ON_AC]


def test_resolve_returns_copy():
    """返回参数副本，调用方修改不会污染 PROFILES。"""
    params, _ = resolve("均衡", battery=False)
    params["poll_ms"] = 999999
    assert PROFILES["均衡"]["poll_ms"] != 999999


# ---------- 电源状态 ----------


def _fake_windll(acline, ok=True):
    """伪造 kernel32.GetSystemPowerStatus：写入真实结构的 ACLineStatus。"""

    class FakeKernel32:
        def GetSystemPowerStatus(self, ptr):
            if ok:
                status = ptr._obj if hasattr(ptr, "_obj") else None
                if status is not None:
                    status.ACLineStatus = acline
            return 1 if ok else 0

    class FakeWindll:
        kernel32 = FakeKernel32()

    return FakeWindll()


def test_on_battery_detects_battery(monkeypatch):
    """ACLineStatus == 0 判为电池供电。"""
    monkeypatch.setattr(perf_profile, "_PowerStatus", lambda: SimpleNamespace(ACLineStatus=0))
    monkeypatch.setattr(perf_profile.ctypes, "byref", lambda obj: SimpleNamespace(_obj=obj))
    monkeypatch.setattr(perf_profile.ctypes, "windll", _fake_windll(0))
    assert on_battery() is True


def test_on_battery_detects_ac(monkeypatch):
    """ACLineStatus == 1 判为插电。"""
    monkeypatch.setattr(perf_profile, "_PowerStatus", lambda: SimpleNamespace(ACLineStatus=1))
    monkeypatch.setattr(perf_profile.ctypes, "byref", lambda obj: SimpleNamespace(_obj=obj))
    monkeypatch.setattr(perf_profile.ctypes, "windll", _fake_windll(1))
    assert on_battery() is False


def test_on_battery_handles_api_failure(monkeypatch):
    """API 返回 0（失败）时按插电处理。"""
    monkeypatch.setattr(perf_profile, "_PowerStatus", lambda: SimpleNamespace(ACLineStatus=0))
    monkeypatch.setattr(perf_profile.ctypes, "byref", lambda obj: SimpleNamespace(_obj=obj))
    monkeypatch.setattr(perf_profile.ctypes, "windll", _fake_windll(0, ok=False))
    assert on_battery() is False


def test_on_battery_handles_exception(monkeypatch):
    """读取电源状态抛异常时不冒泡，按插电处理。"""

    class Boom:
        @property
        def kernel32(self):
            raise OSError("no power info")

    monkeypatch.setattr(perf_profile.ctypes, "windll", Boom())
    assert on_battery() is False


# ---------- 与配置 / 界面联动 ----------


def test_config_persists_profile(tmp_path):
    """响应档位可持久化并重新加载。"""
    path = tmp_path / "config.json"
    cfg = AppConfig(path=path)
    assert cfg.perf_profile == DEFAULT_PROFILE
    cfg.set("perf_profile", "敏捷")
    assert AppConfig(path=path).perf_profile == "敏捷"


def test_config_profile_in_defaults():
    assert "perf_profile" in DEFAULTS


def test_settings_dialog_has_profile_combo(qapp, tmp_path):
    """设置对话框提供响应档位下拉，切换即时写入配置并触发预览。"""
    from settings_dialog import SettingsDialog

    cfg = AppConfig(path=tmp_path / "config.json")
    previews = []
    dlg = SettingsDialog(cfg, on_preview=lambda: previews.append(1))
    try:
        assert dlg._perf_combo.count() == len(PROFILE_NAMES)
        assert dlg._perf_combo.currentText() == DEFAULT_PROFILE
        dlg._perf_combo.setCurrentText("敏捷")
        assert cfg.perf_profile == "敏捷"
        assert previews, "切换档位应触发即时预览回调"
    finally:
        dlg.deleteLater()
