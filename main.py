"""串口提示助手入口：悬浮球 + 亚克力卡片 + 串口插拔监测。"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from PySide6.QtCore import QDir, QLockFile, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from alias_store import AliasStore
from app_config import AppConfig
from app_paths import data_file
from autostart import Autostart
from card_window import CardWindow
from com_manager import try_run_com_task
from com_manager_dialog import ComManagerDialog
from float_ball import FloatBall
import perf_profile
from serial_monitor import SerialMonitor
from settings_dialog import SettingsDialog
from usb_popup import UsbPopup

LOG_FILE = data_file("app.log")
LOCK_NAME = "serial_notis.lock"
# 「自动」档跟随电源状态的巡检间隔（毫秒）
POWER_CHECK_INTERVAL_MS = 30000


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
    # 提权子任务模式：--com-task 由 run_elevated 启动，执行完即退出
    # （不走 GUI/单实例/托盘，必须在 QApplication 之前处理）
    if try_run_com_task(sys.argv):
        return 0

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
    ball.apply_mascot(config.ball_mascot)
    popup = UsbPopup()
    popup.set_duration(config.popup_duration_ms)

    # 响应档位：把「兜底轮询间隔 / 事件复核延迟 / 动效帧率」按档位一次性应用。
    # 记录上次生效的参数，避免电源巡检时反复重设定时器。
    applied_perf = {}

    def apply_perf_profile():
        """按响应档位应用各处节奏（「自动」档读电源状态：插电=均衡、电池=省电）。"""
        params, actual = perf_profile.resolve(config.perf_profile)
        if params == applied_perf.get("params"):
            return
        applied_perf["params"] = params
        monitor.set_timings(params["poll_ms"], params["event_delay_ms"])
        ball.set_anim_fps(params["anim_fps"])
        logging.getLogger("app").info(
            "响应档位 %s（生效 %s）：预检 %dms / 事件复核 %dms / 动效 %dfps",
            config.perf_profile, actual,
            params["poll_ms"], params["event_delay_ms"], params["anim_fps"],
        )

    apply_perf_profile()

    # 电源状态巡检：只为「自动」档服务（插上电源转均衡、拔电转省电）
    power_timer = QTimer()
    power_timer.setInterval(POWER_CHECK_INTERVAL_MS)
    power_timer.timeout.connect(apply_perf_profile)
    power_timer.start()
    # 初始状态
    card.update_ports(monitor.ports, monitor.details)
    ball.set_port_count(len(monitor.ports))

    def on_port_added(device, desc):
        card.update_ports(monitor.ports, monitor.details)
        ball.set_port_count(len(monitor.ports))
        card.add_notification(
            device, desc, added=True, lifetime_ms=config.notify_lifetime_ms
        )
        card.log_event(device, desc, added=True)
        ball.flash(added=True)
        alias = aliases.get(device)
        popup.show_popup(added=True, port=device, alias=alias, desc=desc)
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
        card.log_event(device, desc, added=False)
        ball.flash(added=False)
        alias = aliases.get(device)
        popup.show_popup(added=False, port=device, alias=alias, desc=desc)
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
        """设置对话框即时预览：重绘卡片与悬浮球，并重设响应档位。"""
        card.apply_theme()
        ball.apply_theme()
        ball.apply_mascot(config.ball_mascot)
        ball.apply_animation()
        popup.set_duration(config.popup_duration_ms)
        apply_perf_profile()

    settings_action = QAction("设置…", menu)
    settings_action.triggered.connect(
        lambda: SettingsDialog(config, on_preview=on_preview).exec()
    )
    com_mgr_action = QAction("串口号管理（清理/固定口号）…", menu)
    com_mgr_action.triggered.connect(lambda: ComManagerDialog().exec())
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
    menu.addAction(com_mgr_action)
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
