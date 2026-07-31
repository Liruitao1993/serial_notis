# -*- coding: utf-8 -*-
"""串口提示助手入口：悬浮球 + 亚克力卡片 + 串口插拔监测。"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from PySide6.QtCore import QDir, QLockFile, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from alias_store import AliasStore
from app_config import AppConfig
from app_paths import data_file
from autostart import Autostart
from card_window import CardWindow
from float_ball import FloatBall
from serial_monitor import SerialMonitor
from settings_dialog import SettingsDialog

LOG_FILE = data_file("app.log")
LOCK_NAME = "serial_notis.lock"


def _setup_logging():
    """滚动日志到 exe 旁 app.log（1MB 轮转），源码运行时同时输出控制台。"""
    handler = RotatingFileHandler(
        LOG_FILE, maxBytes=1_000_000, backupCount=1, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    if not getattr(sys, "frozen", False):
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        root.addHandler(console)


def _handle_exception(exc_type, exc, tb):
    """未捕获异常：写日志并弹窗，避免无声崩溃。"""
    logging.getLogger("app").critical("未捕获异常", exc_info=(exc_type, exc, tb))
    try:
        QMessageBox.critical(
            None, "串口提示助手", f"程序出现未预期错误：\n{exc}\n详情见日志 {LOG_FILE}"
        )
    except Exception:
        pass


def _make_tray_icon():
    """程序化画一个小圆点图标，避免依赖资源文件。"""
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(90, 140, 240))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(2, 2, 28, 28)
    painter.setPen(QColor("white"))
    font = painter.font()
    font.setBold(True)
    font.setPointSize(12)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "S")
    painter.end()
    return QIcon(pixmap)


def main():
    _setup_logging()
    sys.excepthook = _handle_exception

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # 单实例保护：第二个实例直接提示退出
    lock = QLockFile(os.path.join(QDir.tempPath(), LOCK_NAME))
    if not lock.tryLock(100):
        logging.getLogger("app").info("检测到已有实例，退出")
        QMessageBox.information(None, "串口提示助手", "程序已在运行中。")
        return 0

    config = AppConfig()
    monitor = SerialMonitor()
    app.installNativeEventFilter(monitor.event_filter)
    aliases = AliasStore()
    card = CardWindow(aliases, config)
    ball = FloatBall(card, config)

    # 初始状态
    card.update_ports(monitor.ports, monitor.details)
    ball.set_port_count(len(monitor.ports))

    def on_port_added(device, desc):
        card.update_ports(monitor.ports, monitor.details)
        ball.set_port_count(len(monitor.ports))
        card.add_notification(
            device, desc, added=True, lifetime_ms=config.notify_lifetime_ms
        )
        ball.flash(added=True)
        if config.auto_show_card and not card.isVisible():
            card.auto_shown = True
            ball.show_card()

    def on_port_removed(device, desc):
        card.update_ports(monitor.ports, monitor.details)
        ball.set_port_count(len(monitor.ports))
        if config.notify_on_remove:
            card.add_notification(
                device, desc, added=False, lifetime_ms=config.notify_lifetime_ms
            )
        ball.flash(added=False)
        if config.auto_show_card and not card.isVisible():
            card.auto_shown = True
            ball.show_card()

    monitor.port_added.connect(on_port_added)
    monitor.port_removed.connect(on_port_removed)

    def on_refresh():
        # 重新枚举串口（差异会发插拔信号），并强制重建列表修复叠影
        monitor.refresh()
        card.update_ports(monitor.ports, monitor.details, force=True)
        ball.set_port_count(len(monitor.ports))

    card.refresh_requested.connect(on_refresh)

    # 系统托盘：防止误关无法退出
    tray = QSystemTrayIcon(_make_tray_icon(), app)
    tray.setToolTip("串口提示助手")
    menu = QMenu()
    show_action = QAction("显示悬浮球", menu)
    show_action.triggered.connect(ball.show)
    def on_preview():
        """设置对话框即时预览：重绘卡片与悬浮球。"""
        card.apply_theme()
        ball.apply_theme()

    settings_action = QAction("设置…", menu)
    settings_action.triggered.connect(
        lambda: SettingsDialog(config, on_preview=on_preview).exec()
    )
    autostart = Autostart()
    autostart_action = QAction("开机自启", menu)
    autostart_action.setCheckable(True)
    autostart_action.setChecked(autostart.enabled)
    autostart_action.triggered.connect(autostart.set_enabled)
    quit_action = QAction("退出", menu)
    quit_action.triggered.connect(app.quit)
    menu.addAction(show_action)
    menu.addSeparator()
    menu.addAction(settings_action)
    menu.addAction(autostart_action)
    menu.addSeparator()
    menu.addAction(quit_action)
    tray.setContextMenu(menu)
    tray.show()

    ball.set_context_menu(menu)
    ball.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
