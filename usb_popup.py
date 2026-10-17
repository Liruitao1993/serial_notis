# -*- coding: utf-8 -*-
"""居中 USB 3D 弹框：串口插入/拔出时在屏幕中央显示大图标，几秒后消失。

纯 QPainter 绘制，无图片资源。
"""

import math

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QPoint, Property, QRectF
from PySide6.QtGui import (
    QColor, QPainter, QPen, QBrush, QRadialGradient, QLinearGradient,
    QPainterPath, QFont,
)
from PySide6.QtWidgets import QWidget


POPUP_WIDTH = 210
POPUP_HEIGHT = 250
DEFAULT_DURATION_MS = 2500
FADE_IN_MS = 220
FADE_OUT_MS = 350


class UsbPopup(QWidget):
    """居中 USB 3D 动画弹框。

    调用 show_popup(added=True/False) 即可显示。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(POPUP_WIDTH, POPUP_HEIGHT)

        self._added = True
        self._port_name = ""
        self._alias = ""
        self._desc = ""
        self._duration_ms = DEFAULT_DURATION_MS
        self._progress = 0.0  # 0.0 ~ 1.0 总进度
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._tick)
        self._elapsed = 0
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    def set_duration(self, ms):
        """设置弹框展示时长（毫秒）。"""
        self._duration_ms = max(FADE_IN_MS + FADE_OUT_MS + 100, int(ms))

    def show_popup(self, added=True, port="", alias="", desc=""):
        """显示弹框。

        Args:
            added: True 插入（绿色），False 拔出（红色）。
            port: COM 口号，如 "COM3"。
            alias: 备注/别名。
            desc: 设备描述。
        """
        # 防重入：先停止旧弹框的动画和隐藏定时器
        self._anim_timer.stop()
        self._hide_timer.stop()

        self._added = added
        self._port_name = port or ""
        self._alias = alias or ""
        self._desc = desc or ""
        self._elapsed = 0
        self._progress = 0.0
        # 屏幕正中间
        screen = self.screen().availableGeometry()
        self.move(
            screen.center().x() - POPUP_WIDTH // 2,
            screen.center().y() - POPUP_HEIGHT // 2,
        )
        self.show()
        self.raise_()
        self._anim_timer.start(1000 // 60)
        self._hide_timer.start(self._duration_ms)

    def _tick(self):
        self._elapsed += 1000 // 60
        self._progress = min(1.0, self._elapsed / self._duration_ms)
        self.update()
        if self._elapsed >= self._duration_ms:
            self._anim_timer.stop()

    # ---------- 绘制 ----------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        p = self._progress
        dur = self._duration_ms
        # 淡入淡出 alpha
        if p < FADE_IN_MS / dur:
            t = p / (FADE_IN_MS / dur)
            alpha = t
        elif p > 1 - FADE_OUT_MS / dur:
            t = (p - (1 - FADE_OUT_MS / dur)) / (FADE_OUT_MS / dur)
            alpha = 1.0 - t
        else:
            alpha = 1.0

        if alpha <= 0.01:
            return

        painter.setOpacity(alpha)

        cx = self.width() / 2
        cy = self.height() / 2

        # 插入/拔出的主题色
        if self._added:
            base = QColor(46, 204, 113)    # 主色 绿
            dark = QColor(22, 160, 90)
            light = QColor(120, 240, 160)
            glow = QColor(46, 204, 113, 80)
        else:
            base = QColor(231, 76, 60)      # 主色 红
            dark = QColor(192, 57, 43)
            light = QColor(255, 140, 120)
            glow = QColor(231, 76, 60, 80)

        # 弹入动画：插入=从下往上+放大，拔出=从上往下+缩小
        if self._added:
            ease = _ease_out_back(min(1.0, p / 0.25))
            scale = 0.5 + ease * 0.5
            y_offset = (1 - ease) * 40
        else:
            # 先放大出现，快结束时向上退场
            if p < 0.2:
                ease = _ease_out_back(p / 0.2)
                scale = 0.5 + ease * 0.5
                y_offset = (1 - ease) * -40
            elif p > 0.7:
                t_out = (p - 0.7) / 0.3
                scale = 1.0 - t_out * 0.4
                y_offset = -t_out * 50
            else:
                scale = 1.0
                y_offset = 0

        painter.save()
        painter.translate(cx, cy + y_offset)
        painter.scale(scale, scale)

        # ---------- 外发光圆盘（偏上，图标中心） ----------
        icon_cy = -30  # 图标中心 y（相对窗体中心偏上）
        outer_r = 78
        for i in range(3):
            r = outer_r + i * 6
            a = int(50 - i * 15)
            g = QRadialGradient(0, icon_cy, r)
            gc = QColor(base)
            gc.setAlpha(a)
            g.setColorAt(0.7, QColor(base.red(), base.green(), base.blue(), a))
            g.setColorAt(1.0, QColor(base.red(), base.green(), base.blue(), 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(g)
            painter.drawEllipse(_rect(0, icon_cy, r))

        # ---------- 圆形面板 ----------
        panel_r = 66
        grad = QRadialGradient(-15, icon_cy - 20, panel_r * 1.4)
        top = QColor(255, 255, 255, 245)
        mid = QColor(240, 244, 250, 240)
        bot = QColor(210, 218, 230, 240)
        grad.setColorAt(0.0, top)
        grad.setColorAt(0.6, mid)
        grad.setColorAt(1.0, bot)
        painter.setPen(QPen(QColor(255, 255, 255, 180), 2))
        painter.setBrush(grad)
        painter.drawEllipse(_rect(0, icon_cy, panel_r))

        # 内阴影
        shadow = QRadialGradient(0, icon_cy, panel_r)
        shadow.setColorAt(0.85, QColor(0, 0, 0, 0))
        shadow.setColorAt(1.0, QColor(0, 0, 0, 30))
        painter.setBrush(shadow)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(_rect(0, icon_cy, panel_r))

        # ---------- USB 3D 图标 ----------
        painter.save()
        painter.translate(0, icon_cy)
        _draw_usb_icon(painter, base, dark, light)
        painter.restore()

        # ---------- 文字区：深色半透明圆角底条 + 白字 + 阴影 ----------
        # 底条位置（圆形面板下方）
        panel_bottom_y = icon_cy + panel_r
        text_top = panel_bottom_y + 10
        text_width = 170

        status_text = "已连接" if self._added else "已断开"

        # 计算需要显示的行数
        lines = []
        # 行1：状态 + COM 号合并显示
        if self._port_name:
            lines.append(("com", self._port_name))
        lines.append(("status", status_text))
        # 行2：备注
        show_text = self._alias or self._desc
        if show_text:
            lines.append(("sub", show_text))

        # 底条高度
        line_heights = {"com": 30, "status": 22, "sub": 18}
        total_h = sum(line_heights[t] for t, _ in lines) + 14  # 上下内边距各 7

        bg_rect = QRectF(
            -text_width / 2,
            text_top,
            text_width,
            total_h,
        )

        # 背景：深色半透明 + 边框（毛玻璃感）
        bg_grad = QLinearGradient(0, bg_rect.top(), 0, bg_rect.bottom())
        bg_grad.setColorAt(0.0, QColor(20, 24, 32, 200))
        bg_grad.setColorAt(1.0, QColor(12, 15, 22, 210))
        painter.setPen(QPen(QColor(255, 255, 255, 25), 1))
        painter.setBrush(bg_grad)
        painter.drawRoundedRect(bg_rect, 12, 12)

        # 内发光顶边（细微高光）
        hl_grad = QLinearGradient(0, bg_rect.top(), 0, bg_rect.top() + 6)
        hl_grad.setColorAt(0.0, QColor(255, 255, 255, 30))
        hl_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(hl_grad)
        # 用裁剪只画顶部区域
        painter.drawRoundedRect(
            QRectF(bg_rect.left() + 1, bg_rect.top() + 1, bg_rect.width() - 2, 8),
            12, 12,
        )

        # 逐行写文字
        cursor_y = text_top + 7
        for line_type, text in lines:
            h = line_heights[line_type]
            font = QFont(self.font())

            if line_type == "com":
                font.setPointSize(19)
                font.setBold(True)
                color = QColor(255, 255, 255, 245)
                shadow_color = QColor(0, 0, 0, 120)
            elif line_type == "status":
                font.setPointSize(11)
                font.setBold(True)
                # 状态文字用主题色（亮绿/亮红）
                if self._added:
                    color = QColor(120, 240, 170, 240)
                else:
                    color = QColor(255, 130, 120, 240)
                shadow_color = QColor(0, 0, 0, 100)
            else:  # sub
                font.setPointSize(9)
                font.setBold(False)
                color = QColor(200, 210, 225, 220)
                shadow_color = QColor(0, 0, 0, 90)

            painter.setFont(font)
            metrics = painter.fontMetrics()
            if line_type == "sub":
                text = metrics.elidedText(text, Qt.ElideRight, text_width - 24)

            # 阴影（偏移 1px）
            painter.setPen(shadow_color)
            painter.drawText(
                QRectF(bg_rect.left() + 1, cursor_y + 1, bg_rect.width(), h),
                Qt.AlignCenter,
                text,
            )
            # 主文字
            painter.setPen(color)
            painter.drawText(
                QRectF(bg_rect.left(), cursor_y, bg_rect.width(), h),
                Qt.AlignCenter,
                text,
            )
            cursor_y += h

        painter.restore()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._anim_timer.stop()


def _ease_out_back(t):
    """Ease out back 缓动：超过一点再弹回。"""
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * math.pow(t - 1, 3) + c1 * math.pow(t - 1, 2)


def _rect(cx, cy, r, h=None):
    """返回中心 (cx, cy) 半径 r（或宽 2r 高 2h）的 QRectF。"""
    if h is None:
        h = r
    return QRectF(cx - r, cy - h, r * 2, h * 2)


def _draw_usb_icon(painter, base, dark, light):
    """在原点绘制 3D 风格 USB 插头图标（向上为插入口方向）。

    整体约 40x60，居中于原点。
    """
    # 整体位置：以原点为中心，USB 头朝上
    # 尺寸
    head_w = 28   # 金属头宽度
    head_h = 18   # 金属头高度
    body_w = 22   # 塑料身宽度
    body_h = 24   # 塑料身高度

    top_y = -32   # 顶端 y
    head_top = top_y
    head_bottom = top_y + head_h
    body_top = head_bottom
    body_bottom = body_top + body_h

    # ---------- 金属头（梯形，上窄下宽） ----------
    head_path = QPainterPath()
    head_top_w = head_w * 0.75
    head_path.moveTo(-head_top_w / 2, head_top)
    head_path.lineTo(head_top_w / 2, head_top)
    head_path.lineTo(head_w / 2, head_bottom)
    head_path.lineTo(-head_w / 2, head_bottom)
    head_path.closeSubpath()

    # 金属渐变色（银色金属感）
    metal_grad = QLinearGradient(0, head_top, 0, head_bottom)
    metal_grad.setColorAt(0.0, QColor(200, 210, 220))
    metal_grad.setColorAt(0.3, QColor(245, 250, 255))
    metal_grad.setColorAt(0.55, QColor(180, 190, 205))
    metal_grad.setColorAt(1.0, QColor(150, 160, 175))
    painter.setPen(QPen(QColor(120, 130, 145), 1))
    painter.setBrush(metal_grad)
    painter.drawPath(head_path)

    # 金属头内部黑色插槽
    slot_y = head_top + 4
    slot_h = 8
    slot_w_top = head_top_w * 0.6
    slot_w_bot = head_w * 0.65
    slot_path = QPainterPath()
    slot_path.moveTo(-slot_w_top / 2, slot_y)
    slot_path.lineTo(slot_w_top / 2, slot_y)
    slot_path.lineTo(slot_w_bot / 2, slot_y + slot_h)
    slot_path.lineTo(-slot_w_bot / 2, slot_y + slot_h)
    slot_path.closeSubpath()
    painter.setPen(Qt.NoPen)
    slot_grad = QLinearGradient(0, slot_y, 0, slot_y + slot_h)
    slot_grad.setColorAt(0.0, QColor(30, 35, 45))
    slot_grad.setColorAt(1.0, QColor(50, 55, 70))
    painter.setBrush(slot_grad)
    painter.drawPath(slot_path)

    # 插槽内的金属片（两个小点代表触点）
    painter.setBrush(QColor(220, 230, 240))
    for i in [-1, 1]:
        x = i * 4
        painter.drawEllipse(x - 1.5, slot_y + 2.5, 3, 2)

    # 金属头顶部高光
    hl_path = QPainterPath()
    hl_w = head_top_w * 0.4
    hl_path.moveTo(-hl_w / 2, head_top + 1)
    hl_path.lineTo(hl_w / 2, head_top + 1)
    hl_path.lineTo(hl_w / 2 - 1, head_top + 2.5)
    hl_path.lineTo(-hl_w / 2 + 1, head_top + 2.5)
    hl_path.closeSubpath()
    painter.setBrush(QColor(255, 255, 255, 180))
    painter.drawPath(hl_path)

    # ---------- 塑料身（主体色） ----------
    body_grad = QLinearGradient(-body_w / 2, 0, body_w / 2, 0)
    # 左侧高光
    hl = QColor(light)
    body_grad.setColorAt(0.0, dark)
    body_grad.setColorAt(0.3, base)
    body_grad.setColorAt(0.5, hl)
    body_grad.setColorAt(0.7, base)
    body_grad.setColorAt(1.0, dark)

    # 主体矩形，底部圆弧形
    body_path = QPainterPath()
    body_path.moveTo(-body_w / 2, body_top)
    body_path.lineTo(body_w / 2, body_top)
    body_path.lineTo(body_w / 2, body_bottom - 8)
    body_path.quadTo(body_w / 2, body_bottom, body_w / 2 - 8, body_bottom)
    body_path.lineTo(-body_w / 2 + 8, body_bottom)
    body_path.quadTo(-body_w / 2, body_bottom, -body_w / 2, body_bottom - 8)
    body_path.closeSubpath()

    painter.setPen(QPen(dark, 1))
    painter.setBrush(body_grad)
    painter.drawPath(body_path)

    # 塑料身上方连接处阴影
    shadow_grad = QLinearGradient(0, body_top, 0, body_top + 5)
    shadow_grad.setColorAt(0.0, QColor(0, 0, 0, 40))
    shadow_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
    painter.setPen(Qt.NoPen)
    painter.setBrush(shadow_grad)
    rect_top = body_top
    painter.drawRect(QRectF(-body_w / 2 + 1, rect_top, body_w - 2, 5))

    # 塑料身的 USB 标志（三叉戟）
    painter.setPen(QColor(255, 255, 255, 200))
    painter.setBrush(Qt.NoBrush)
    trident_cy = body_top + body_h * 0.55
    trident_size = 7
    # 竖线
    painter.drawLine(0, trident_cy - trident_size, 0, trident_cy + trident_size * 0.3)
    # 三个头（上尖 + 左右横）
    painter.drawLine(-trident_size * 0.7, trident_cy - trident_size * 0.3,
                     trident_size * 0.7, trident_cy - trident_size * 0.3)
    # 箭头点
    dot_r = 1.5
    painter.setBrush(QColor(255, 255, 255, 220))
    painter.setPen(Qt.NoPen)
    for x, y in [
        (0, trident_cy - trident_size - 1),
        (-trident_size * 0.7, trident_cy - trident_size * 0.3),
        (trident_size * 0.7, trident_cy - trident_size * 0.3),
    ]:
        painter.drawEllipse(QRectF(x - dot_r, y - dot_r, dot_r * 2, dot_r * 2))

    # 底部线缆尾
    cable_top = body_bottom
    cable_w = body_w * 0.45
    cable_h = 6
    cable_grad = QLinearGradient(0, cable_top, 0, cable_top + cable_h)
    cable_grad.setColorAt(0.0, dark)
    cable_grad.setColorAt(0.5, base)
    cable_grad.setColorAt(1.0, dark)
    painter.setBrush(cable_grad)
    painter.setPen(QPen(dark, 1))
    painter.drawRoundedRect(
        QRectF(-cable_w / 2, cable_top, cable_w, cable_h), 2, 2
    )

    # 整体右侧高光（增强 3D 感）
    highlight = QLinearGradient(-body_w / 2, 0, body_w / 2, 0)
    highlight.setColorAt(0.0, QColor(255, 255, 255, 0))
    highlight.setColorAt(0.4, QColor(255, 255, 255, 50))
    highlight.setColorAt(0.5, QColor(255, 255, 255, 0))
    highlight.setColorAt(1.0, QColor(0, 0, 0, 0))
    painter.setPen(Qt.NoPen)
    painter.setBrush(highlight)
    painter.drawPath(body_path)
