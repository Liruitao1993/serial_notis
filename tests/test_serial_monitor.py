# -*- coding: utf-8 -*-
"""SerialMonitor 核心逻辑测试：diff、失败保护、去抖、事件过滤器。"""

import ctypes
import ctypes.wintypes as wt
import logging
import time
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QCoreApplication

from serial_monitor import (
    PortInfo,
    SerialMonitor,
    WM_DEVICECHANGE,
    _port_info,
)

def make_port(device, desc="", vid=None, pid=None, manufacturer="", hwid=""):
    return SimpleNamespace(
        device=device,
        description=desc,
        vid=vid,
        pid=pid,
        manufacturer=manufacturer,
        hwid=hwid,
    )


def make_monitor(monkeypatch, snapshots):
    """用注入的快照序列构造 SerialMonitor（__init__ 消耗第一个）。"""
    it = iter(snapshots)

    def fake_snapshot():
        try:
            return next(it)
        except StopIteration:
            raise AssertionError("snapshot 序列耗尽")

    monkeypatch.setattr(SerialMonitor, "_snapshot", staticmethod(fake_snapshot))
    return SerialMonitor()


def pump(ms):
    """处理 Qt 事件直至定时器触发。"""
    end = time.time() + ms / 1000
    while time.time() < end:
        QCoreApplication.processEvents()
        time.sleep(0.005)


# ---------- 快照比对与信号 ----------


def test_refresh_emits_added_and_removed(monkeypatch):
    a1 = make_port("COM1", "主节点")
    a2 = make_port("COM2", "从节点")
    m = make_monitor(
        monkeypatch,
        [
            {"COM1": a1},            # __init__
            {"COM1": a1, "COM2": a2},  # 插入 COM2
            {"COM1": a1},            # 拔出 COM2
        ],
    )
    added, removed = [], []
    m.port_added.connect(lambda d, s: added.append((d, s)))
    m.port_removed.connect(lambda d, s: removed.append((d, s)))

    m.refresh()
    assert added == [("COM2", "从节点")]

    m.refresh()
    assert removed == [("COM2", "从节点")]
    assert m.ports == {"COM1": "主节点"}


def test_refresh_unchanged_no_signals(monkeypatch):
    a1 = make_port("COM1", "x")
    m = make_monitor(monkeypatch, [{"COM1": a1}, {"COM1": a1}])
    added = []
    m.port_added.connect(lambda d, s: added.append(d))
    m.refresh()
    assert added == []


# ---------- 枚举失败保护 ----------


def test_snapshot_failure_keeps_old_state(monkeypatch, caplog):
    """枚举抛异常：记日志、保留旧快照、不误报拔出。"""
    from serial.tools import list_ports

    a1 = make_port("COM1", "主节点")
    calls = {"n": 0}

    def fake_comports():
        calls["n"] += 1
        if calls["n"] == 1:
            return [a1]
        raise OSError("boom")

    monkeypatch.setattr(list_ports, "comports", fake_comports)
    m = SerialMonitor()  # 第一次成功
    assert m.ports == {"COM1": "主节点"}
    removed = []
    m.port_removed.connect(lambda d, s: removed.append((d, s)))

    with caplog.at_level(logging.ERROR, logger="serial_monitor"):
        m.refresh()  # 失败：不得误报拔出
    assert removed == []
    assert m.ports == {"COM1": "主节点"}
    assert "枚举串口失败" in caplog.text


# ---------- schedule_refresh 去抖合并 ----------


def test_schedule_refresh_coalesces(qapp, monkeypatch):
    a1 = make_port("COM1", "a")
    a2 = make_port("COM2", "b")
    m = make_monitor(monkeypatch, [{"COM1": a1}, {"COM1": a1, "COM2": a2}, {"COM1": a1}])
    added = []
    m.port_added.connect(lambda d, s: added.append((d, s)))

    # 200ms 内连发两次事件，只应触发一次 refresh
    m.schedule_refresh()
    m.schedule_refresh()
    pump(350)
    assert added == [("COM2", "b")]

    # 二次确认：不再有多余刷新
    pump(350)
    assert added == [("COM2", "b")]


# ---------- 事件过滤器 ----------


def test_event_filter_forwards_wm_devicechange(qapp, monkeypatch):
    a1 = make_port("COM1", "a")
    a2 = make_port("COM2", "b")
    m = make_monitor(monkeypatch, [{"COM1": a1}, {"COM1": a1, "COM2": a2}])
    added = []
    m.port_added.connect(lambda d, s: added.append((d, s)))

    msg = wt.MSG()
    msg.message = WM_DEVICECHANGE
    consumed = m.event_filter.nativeEventFilter(
        b"windows_generic_MSG", int(ctypes.addressof(msg))
    )
    assert consumed is False  # 不吞事件
    pump(350)
    assert added == [("COM2", "b")]


def test_event_filter_ignores_other_messages(qapp, monkeypatch):
    m = make_monitor(monkeypatch, [{}, {}])
    msg = wt.MSG()
    msg.message = 0x0100  # WM_KEYDOWN
    consumed = m.event_filter.nativeEventFilter(
        b"windows_generic_MSG", int(ctypes.addressof(msg))
    )
    assert consumed is False


# ---------- PortInfo / _port_info ----------


def test_vidpid_format():
    info = PortInfo("COM1", vid=0x1A86, pid=0x7523)
    assert info.vidpid == "1A86:7523"
    assert PortInfo("COM1").vidpid == ""


def test_port_info_extraction_defaults():
    port = make_port("COM9", "描述", 0x1A86, 0x7523, "CH340", "USB\\VID_1A86")
    info = _port_info(port)
    assert (info.device, info.description) == ("COM9", "描述")
    assert (info.vid, info.pid) == (0x1A86, 0x7523)
    assert info.manufacturer == "CH340"
    assert info.vidpid == "1A86:7523"


def test_port_info_missing_fields():
    port = SimpleNamespace(device="COM3", description=None)  # 无 vid/pid 等属性
    info = _port_info(port)
    assert info.description == ""
    assert info.vid is None and info.vidpid == ""
    assert info.manufacturer == "" and info.hwid == ""


# ---------- 廉价预检轮询（性能优化） ----------


def test_poll_skips_full_enumeration_when_unchanged(monkeypatch):
    """COM 口集合未变：轮询不得触发全量枚举（空闲开销接近 0）。"""
    a1 = make_port("COM1", "a")
    m = make_monitor(monkeypatch, [{"COM1": a1}])  # __init__ 消耗唯一快照
    m._cheap_sig = frozenset({"COM1"})  # 固定初始签名，隔离真实机器状态

    # 廉价预检始终返回与初始相同的集合
    monkeypatch.setattr(
        "serial_monitor._cheap_port_names", lambda: frozenset({"COM1"})
    )
    full_calls = {"n": 0}
    orig_snapshot = SerialMonitor._snapshot  # staticmethod，无 self

    def counting_snapshot():
        full_calls["n"] += 1
        return orig_snapshot()

    monkeypatch.setattr(SerialMonitor, "_snapshot", staticmethod(counting_snapshot))

    m._poll_tick()
    m._poll_tick()
    assert full_calls["n"] == 0  # 未做全量枚举


def test_poll_full_enumerates_when_set_changes(monkeypatch):
    """COM 口集合变化：轮询触发全量枚举并发信号。"""
    a1 = make_port("COM1", "a")
    a2 = make_port("COM2", "b")
    m = make_monitor(
        monkeypatch,
        [{"COM1": a1}, {"COM1": a1, "COM2": a2}],
    )
    m._cheap_sig = frozenset({"COM1"})  # 初始只有 COM1
    added = []
    m.port_added.connect(lambda d, s: added.append((d, s)))

    # 预检返回新增 COM2 的集合
    monkeypatch.setattr(
        "serial_monitor._cheap_port_names",
        lambda: frozenset({"COM1", "COM2"}),
    )
    m._poll_tick()
    assert added == [("COM2", "b")]
    # 全量枚举后签名已同步，再轮询（预检仍返回两个口）不应重复触发
    m._poll_tick()
    assert added == [("COM2", "b")]


def test_poll_falls_back_when_cheap_unavailable(monkeypatch):
    """廉价预检返回 None（非 Windows/调用失败）：回退全量枚举，不漏检。"""
    a1 = make_port("COM1", "a")
    m = make_monitor(monkeypatch, [{"COM1": a1}, {"COM1": a1}])
    m._cheap_sig = frozenset({"COM1"})
    monkeypatch.setattr("serial_monitor._cheap_port_names", lambda: None)
    # 不应抛异常；全量枚举内容一致，无信号
    m._poll_tick()


def test_cheap_port_names_returns_frozenset_or_none():
    """廉价预检在 Windows 上返回 COM 名集合，失败时返回 None（不抛异常）。"""
    import serial_monitor

    sig = serial_monitor._cheap_port_names()
    assert sig is None or isinstance(sig, frozenset)
    if sig is not None:
        assert all(isinstance(n, str) and n for n in sig)


# ---------- 响应档位相关的时序与 fast-path ----------


def test_set_timings_updates_intervals(monkeypatch):
    """set_timings 同时更新轮询间隔与事件复核延迟。"""
    m = make_monitor(monkeypatch, [{"COM1": make_port("COM1")}])
    m.set_timings(poll_ms=500, event_delay_ms=100)
    assert m._poll_ms == 500
    assert m._event_delay_ms == 100
    assert m._poll_timer.interval() == 500
    assert m._refresh_timer.interval() == 100


def test_set_timings_only_updates_given_values(monkeypatch):
    """只更新传入的项，未传入的保持原值。"""
    m = make_monitor(monkeypatch, [{"COM1": make_port("COM1")}])
    m.set_timings(poll_ms=2000, event_delay_ms=300)
    m.set_timings(poll_ms=500)
    assert m._poll_ms == 500
    assert m._event_delay_ms == 300


def test_set_timings_clamps_lower_bound(monkeypatch):
    """过小的间隔被夹到下限，避免定时器空转。"""
    m = make_monitor(monkeypatch, [{"COM1": make_port("COM1")}])
    m.set_timings(poll_ms=1, event_delay_ms=-50)
    assert m._poll_ms == 100
    assert m._event_delay_ms == 0


def test_schedule_refresh_fast_path(monkeypatch):
    """预检已看到新口时立即刷新，不必等事件复核周期（这是提示变快的关键）。"""
    a1 = make_port("COM1", "主节点")
    a2 = make_port("COM2", "从节点")
    m = make_monitor(monkeypatch, [{"COM1": a1}, {"COM1": a1, "COM2": a2}])
    m._cheap_sig = frozenset({"COM1"})
    monkeypatch.setattr(
        "serial_monitor._cheap_port_names", lambda: frozenset({"COM1", "COM2"})
    )
    added = []
    m.port_added.connect(lambda d, s: added.append(d))

    m.schedule_refresh()

    assert added == ["COM2"]
    # 仍安排一次延迟复核，用于补全随后才就绪的描述 / VID:PID
    assert m._refresh_timer.isActive()


def test_schedule_refresh_waits_when_precheck_unchanged(monkeypatch):
    """预检无变化时不立即枚举，只安排延迟复核（保持原有兜底行为）。"""
    m = make_monitor(monkeypatch, [{"COM1": make_port("COM1")}])
    m._cheap_sig = frozenset({"COM1"})
    monkeypatch.setattr("serial_monitor._cheap_port_names", lambda: frozenset({"COM1"}))
    added = []
    m.port_added.connect(lambda d, s: added.append(d))

    m.schedule_refresh()

    assert added == []
    assert m._refresh_timer.isActive()


def test_schedule_refresh_falls_back_when_precheck_unavailable(monkeypatch):
    """预检不可用（返回 None）时退回延迟复核，不漏检也不误报。"""
    m = make_monitor(monkeypatch, [{"COM1": make_port("COM1")}])
    monkeypatch.setattr("serial_monitor._cheap_port_names", lambda: None)

    m.schedule_refresh()

    assert m._refresh_timer.isActive()
