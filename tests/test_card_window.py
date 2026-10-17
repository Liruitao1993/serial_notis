# -*- coding: utf-8 -*-
"""CardWindow 列表重建逻辑测试：指纹缓存、force 重建、详情传递、自然排序、事件历史。"""

from datetime import datetime

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame

import card_window as cw
from alias_store import AliasStore
from serial_monitor import PortInfo


class FakeRow(QFrame):
    """替身行：记录实例，模拟 PortRow 的对外接口。"""

    instances = []

    edit_requested = Signal(str)
    clicked = Signal(str)

    def __init__(self, device, desc, alias, info=None, parent=None, **kwargs):
        super().__init__(parent)
        self.device = device
        self.desc = desc
        self.alias = alias
        self.info = info
        self._selected = False
        FakeRow.instances.append(self)

    def set_selected(self, selected):
        self._selected = selected


def make_card(tmp_path):
    aliases = AliasStore(path=tmp_path / "aliases.json")
    return cw.CardWindow(aliases)


def test_update_ports_signature_cache(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(cw, "PortRow", FakeRow)
    FakeRow.instances.clear()
    card = make_card(tmp_path)

    ports = {"COM1": "主节点"}
    details = {"COM1": PortInfo("COM1", "主节点", vid=0x1A86, pid=0x7523)}
    card.update_ports(ports, details)
    n1 = len(FakeRow.instances)
    assert n1 == 1
    assert card._count_label.text() == "1 个串口"

    # 内容未变：跳过重建
    card.update_ports(ports, details)
    assert len(FakeRow.instances) == n1

    # force=True：强制重建（修复叠影）
    card.update_ports(ports, details, force=True)
    assert len(FakeRow.instances) == n1 + 1


def test_update_ports_passes_details(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(cw, "PortRow", FakeRow)
    FakeRow.instances.clear()
    card = make_card(tmp_path)

    details = {"COM2": PortInfo("COM2", "从节点", vid=0x10C4, pid=0xEA60, manufacturer="CP210x")}
    card.update_ports({"COM2": "从节点"}, details)

    row = FakeRow.instances[-1]
    assert row.info is not None
    assert row.info.vidpid == "10C4:EA60"
    assert row.info.manufacturer == "CP210x"


def test_update_ports_empty(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(cw, "PortRow", FakeRow)
    FakeRow.instances.clear()
    card = make_card(tmp_path)
    card.update_ports({})
    assert FakeRow.instances == []
    assert card._count_label.text() == "0 个串口"


def test_port_sort_key_natural_order():
    key = cw.CardWindow._port_sort_key
    ports = ["COM10", "COM2", "COM1", "COM64"]
    assert sorted(ports, key=key) == ["COM1", "COM2", "COM10", "COM64"]


# ---------- 插拔事件历史记录 ----------


def test_log_event_max_limit(qapp, tmp_path):
    card = make_card(tmp_path)
    for i in range(12):
        card.log_event(f"COM{i}", f"设备{i}", added=(i % 2 == 0))
    assert len(card._event_log) == cw.EVENT_LOG_MAX
    # 最早两条（COM0, COM1）被淘汰
    assert card._event_log[0]["device"] == "COM2"
    assert card._event_log[-1]["device"] == "COM11"


def test_log_event_timestamp(qapp, tmp_path):
    card = make_card(tmp_path)
    card.log_event("COM1", "USB 串口", added=True)
    assert isinstance(card._event_log[0]["timestamp"], datetime)


def test_log_event_added_flag(qapp, tmp_path):
    card = make_card(tmp_path)
    card.log_event("COM1", "设备A", added=True)
    card.log_event("COM2", "设备B", added=False)
    assert card._event_log[0]["added"] is True
    assert card._event_log[1]["added"] is False


def test_history_toggle(qapp, tmp_path):
    card = make_card(tmp_path)
    assert card._history_visible is False
    card._on_history_clicked()
    assert card._history_visible is True
    card._on_history_clicked()
    assert card._history_visible is False


def test_log_event_updates_visible_panel(qapp, tmp_path):
    card = make_card(tmp_path)
    card._history_visible = True
    # 面板初始为空（暂无记录）
    before = card._history_layout.count()
    card.log_event("COM1", "USB 串口", added=True)
    after = card._history_layout.count()
    assert after > before  # 新增了一条 EventLogItem
