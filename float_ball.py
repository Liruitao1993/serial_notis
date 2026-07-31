# -*- coding: utf-8 -*-
"""加速球式悬浮球：无边框、置顶、可拖拽，点击切换卡片显示。

同时承担 WM_DEVICECHANGE 原生事件监听，驱动串口监视器刷新。
"""

from PySide6.QtCore import Property, Qt, QPoint, QPropertyAnimation, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

BALL_SIZE = 56
DRAG_THRESHOLD = 4
# 事件闪烁时长（毫秒）
FLASH_DURATION_MS = 2000

WM_DEVICECHANGE = 0x0219


class FloatBall(QWidget):
    """悬浮球本体。"""

    def __init__(self, card, monitor, parent=None):
        super().__init__(parent)
        self._card = card
        self._monitor = monitor

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(BALL_SIZE, BALL_SIZE)

        self._port_count = 0
        self._pressed = False
        self._dragging = False
        self._press_pos = QPoint()

        # 事件闪烁描边（0.0~1.0 强度）
        self._flash_strength = 0.0
        self._flash_color = QColor(120, 220, 140)
        self._flash_anim = QPropertyAnimation(self, b"flashStrength", self)
        self._flash_anim.setDuration(FLASH_DURATION_MS)
        self._flash_anim.setKeyValueAt(0.0, 0.0)
        self._flash_anim.setKeyValueAt(0.15, 1.0)
        self._flash_anim.setKeyValueAt(0.5, 0.35)
        self._flash_anim.setKeyValueAt(0.75, 1.0)
        self._flash_anim.setKeyValueAt(1.0, 0.0)

        # 初始位置：屏幕右侧中部
        screen = self.screen().availableGeometry()
        self.move(screen.right() - BALL_SIZE - 12, screen.center().y() - BALL_SIZE // 2)

    # ---------- 闪烁属性 ----------

    def _get_flash(self):
        return self._flash_strength

    def _set_flash(self, value):
        self._flash_strength = value
        self.update()

    flashStrength = Property(float, _get_flash, _set_flash)

    def flash(self, added):
        """串口事件时的红/绿描边呼吸提示。"""
        self._flash_color = QColor(120, 220, 140) if added else QColor(230, 80, 80)
        self._flash_anim.stop()
        self._flash_anim.start()

    def set_port_count(self, count):
        self._port_count = count
        self.update()

    # ---------- 绘制 ----------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(3, 3, -3, -3)

        # 半透明径向渐变球体
        gradient = QRadialGradient(rect.center().x() - 8, rect.center().y() - 8, BALL_SIZE)
        gradient.setColorAt(0.0, QColor(90, 140, 240, 210))
        gradient.setColorAt(0.7, QColor(50, 80, 170, 190))
        gradient.setColorAt(1.0, QColor(35, 55, 120, 170))
        painter.setPen(QPen(QColor(255, 255, 255, 60), 1))
        painter.setBrush(gradient)
        painter.drawEllipse(rect)

        # 事件闪烁描边
        if self._flash_strength > 0.01:
            color = QColor(self._flash_color)
            color.setAlpha(int(230 * self._flash_strength))
            painter.setPen(QPen(color, 3))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(rect)

        # 中心：串口数量
        painter.setPen(QColor(255, 255, 255, 235))
        font = QFont(self.font())
        font.setPointSize(15)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect.adjusted(0, -5, 0, -5), Qt.AlignCenter, str(self._port_count))

        font.setPointSize(6)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255, 170))
        painter.drawText(rect.adjusted(0, 16, 0, 0), Qt.AlignCenter, "串口")

    # ---------- 拖拽 / 点击 ----------

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._pressed = True
            self._dragging = False
            self._press_pos = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event):
        if not self._pressed:
            return
        global_pos = event.globalPosition().toPoint()
        if not self._dragging:
            if (global_pos - self._press_pos - self.pos()).manhattanLength() <= DRAG_THRESHOLD:
                return
            self._dragging = True
        self.move(global_pos - self._press_pos)
        if self._card.isVisible():
            self._card.move(self._card_pos())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._pressed:
            self._pressed = False
            if not self._dragging:
                self.toggle_card()
            self._dragging = False

    # ---------- 卡片 ----------

    def toggle_card(self):
        if self._card.isVisible():
            self._card.hide()
        else:
            self._card.auto_shown = False
            self.show_card()

    def show_card(self):
        self._card.show()
        QTimer.singleShot(0, lambda: self._card.move(self._card_pos()))

    def _card_pos(self):
        """卡片放在球的左侧或右侧，自适应屏幕边缘。"""
        screen = self.screen().availableGeometry()
        card = self._card
        gap = 10
        x = self.x() - card.width() - gap  # 优先左侧
        if x < screen.left():
            x = self.x() + self.width() + gap  # 放不下改右侧
        y = self.y()
        y = max(screen.top(), min(y, screen.bottom() - card.height()))
        x = max(screen.left(), min(x, screen.right() - card.width()))
        return QPoint(x, y)

    # ---------- 原生事件：设备插拔广播 ----------

    def nativeEvent(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            import ctypes.wintypes as wt
            import ctypes

            msg = ctypes.cast(int(message), ctypes.POINTER(wt.MSG)).contents
            if msg.message == WM_DEVICECHANGE:
                self._monitor.schedule_refresh()
        return super().nativeEvent(event_type, message)
