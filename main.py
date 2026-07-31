# -*- coding: utf-8 -*-
"""串口提示助手入口：悬浮球 + 亚克力卡片 + 串口插拔监测。"""

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from alias_store import AliasStore
from card_window import CardWindow
from float_ball import FloatBall
from serial_monitor import SerialMonitor


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
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    monitor = SerialMonitor()
    aliases = AliasStore()
    card = CardWindow(aliases)
    ball = FloatBall(card, monitor)

    # 初始状态
    card.update_ports(monitor.ports)
    ball.set_port_count(len(monitor.ports))

    def on_port_added(device, desc):
        card.update_ports(monitor.ports)
        ball.set_port_count(len(monitor.ports))
        card.add_notification(device, desc, added=True)
        ball.flash(added=True)
        if not card.isVisible():
            card.auto_shown = True
            ball.show_card()

    def on_port_removed(device, desc):
        card.update_ports(monitor.ports)
        ball.set_port_count(len(monitor.ports))
        card.add_notification(device, desc, added=False)
        ball.flash(added=False)
        if not card.isVisible():
            card.auto_shown = True
            ball.show_card()

    monitor.port_added.connect(on_port_added)
    monitor.port_removed.connect(on_port_removed)

    def on_refresh():
        # 重新枚举串口（差异会发插拔信号），并强制重建列表修复叠影
        monitor.refresh()
        card.update_ports(monitor.ports)
        ball.set_port_count(len(monitor.ports))

    card.refresh_requested.connect(on_refresh)

    # 系统托盘：防止误关无法退出
    tray = QSystemTrayIcon(_make_tray_icon(), app)
    tray.setToolTip("串口提示助手")
    menu = QMenu()
    show_action = QAction("显示悬浮球", menu)
    show_action.triggered.connect(ball.show)
    quit_action = QAction("退出", menu)
    quit_action.triggered.connect(app.quit)
    menu.addAction(show_action)
    menu.addSeparator()
    menu.addAction(quit_action)
    tray.setContextMenu(menu)
    tray.show()

    ball.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
