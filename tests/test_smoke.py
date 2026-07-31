# -*- coding: utf-8 -*-
"""冒烟测试：完整装配不崩溃、入口可导入、死代码已删除。"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_acrylic_dead_code_removed():
    assert not (ROOT / "acrylic.py").exists(), "acrylic.py 死代码应已删除"


def test_main_importable():
    import importlib

    importlib.import_module("main")  # 模块级导入不创建 QApplication


def test_full_wiring_smoke(qapp, tmp_path, monkeypatch):
    """按 main.py 的方式装配全部对象，验证无导入/构造回归。"""
    from alias_store import AliasStore
    from app_config import AppConfig
    from card_window import CardWindow
    from float_ball import FloatBall
    from serial_monitor import PortInfo, SerialMonitor
    from settings_dialog import SettingsDialog

    monkeypatch.setattr(SerialMonitor, "_snapshot", staticmethod(lambda: {}))
    config = AppConfig(path=tmp_path / "config.json")
    aliases = AliasStore(path=tmp_path / "aliases.json")
    monitor = SerialMonitor()
    qapp.installNativeEventFilter(monitor.event_filter)
    card = CardWindow(aliases)
    ball = FloatBall(card)

    card.update_ports(monitor.ports, monitor.details)
    ball.set_port_count(len(monitor.ports))
    assert ball._port_count == 0

    # 设置对话框可构造
    dialog = SettingsDialog(config)
    assert dialog is not None
    dialog.deleteLater()

    # 事件驱动路径：注入快照后刷新，通知与计数联动
    monkeypatch.setattr(
        SerialMonitor,
        "_snapshot",
        staticmethod(
            lambda: {"COM1": PortInfo("COM1", "主节点", vid=0x1A86, pid=0x7523)}
        ),
    )
    monitor.refresh()
    card.update_ports(monitor.ports, monitor.details)
    ball.set_port_count(len(monitor.ports))
    assert ball._port_count == 1
    assert card._count_label.text() == "1 个串口"
