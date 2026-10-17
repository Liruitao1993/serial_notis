# -*- coding: utf-8 -*-
"""加速球式悬浮球：无边框、置顶、可拖拽，点击切换卡片显示。

同时承担 WM_DEVICECHANGE 原生事件监听，驱动串口监视器刷新。
内置三种 QPainter 动效：呼吸 / 脉冲光环 / 旋转粒子。
"""

import math

from PySide6.QtCore import (
    Property, Qt, QPoint, QPointF, QPropertyAnimation, QTimer,
    QSequentialAnimationGroup, QParallelAnimationGroup,
    QEasingCurve, QAbstractAnimation, QElapsedTimer,
)
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

import themes
from mascots import draw_mascot

BALL_SIZE = 56
MASCOT_SIZE = 96       # 卡通形象画布大小
MASCOT_PADDING = 28    # 泡泡/气泡溢出空间
DRAG_THRESHOLD = 4
# 事件闪烁时长（毫秒）
FLASH_DURATION_MS = 2000
# 动效帧率。30fps 对呼吸/光环/粒子等慢动效已足够流畅，
# 重绘开销比 60fps 减半；跳跃/闪烁走 QPropertyAnimation，不受此帧率影响。
ANIM_FPS = 30
# 呼吸周期（毫秒）
BREATH_PERIOD_MS = 3200
# 脉冲光环周期
PULSE_PERIOD_MS = 2000
# 粒子旋转周期（最快那圈）
PARTICLE_PERIOD_MS = 2600
# 卡片打开时，形象绕卡跳跃的间隔（毫秒）
HOP_INTERVAL_MS = 10000
# 单次跳跃动画时长（毫秒）
HOP_DURATION_MS = 1400


class FloatBall(QWidget):
    """悬浮球本体。"""

    def __init__(self, card, config=None, parent=None):
        super().__init__(parent)
        self._card = card
        self._config = config
        self._menu = None

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        # 动效需要更大画布（光环/粒子会溢出球本体）
        self.setFixedSize(BALL_SIZE + 16, BALL_SIZE + 16)

        self._port_count = 0
        self._pressed = False
        self._dragging = False
        self._press_pos = QPoint()
        self._mascot_name = None
        self._event_type = None       # None / "added" / "removed"
        self._event_age_ms = 99999    # 事件过去多久
        self._hop_offset = 0.0        # 蹦跳偏移（动画驱动）

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

        # 动效时间推进（毫秒，精确计时）
        self._anim_time = 0
        self._anim_elapsed = QElapsedTimer()
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._on_anim_tick)

        # 绕卡跳跃动画（卡片打开时周期性触发）
        self._hop_group = QSequentialAnimationGroup(self)
        self._hop_group.finished.connect(self._on_hop_finished)
        self._hop_timer = QTimer(self)
        self._hop_timer.setInterval(HOP_INTERVAL_MS)
        self._hop_timer.timeout.connect(self._start_hop)

        # 初始位置：屏幕右侧中部
        screen = self.screen().availableGeometry()
        self.move(
            screen.right() - (BALL_SIZE + 16) - 12,
            screen.center().y() - (BALL_SIZE + 16) // 2,
        )
        self.apply_theme()
        self.apply_animation()

    # ---------- 主题 ----------

    @staticmethod
    def _blend(c1, c2, t):
        return QColor(
            int(c1.red() + (c2.red() - c1.red()) * t),
            int(c1.green() + (c2.green() - c1.green()) * t),
            int(c1.blue() + (c2.blue() - c1.blue()) * t),
        )

    def apply_theme(self):
        """按配置应用悬浮球主题（渐变、文字、闪动色），立即重绘。"""
        name = self._config.ball_theme if self._config else "深空蓝"
        t = themes.ball_theme(name)
        top = QColor(t["grad"][0])
        bottom = QColor(t["grad"][1])
        self._ball_stops = (top, self._blend(top, bottom, 0.55), bottom)
        self._ball_text = QColor(t["text"])
        self._flash_added = QColor(t["flash_added"])
        self._flash_removed = QColor(t["flash_removed"])
        self.update()

    def apply_animation(self):
        """按配置启停动效定时器。"""
        name = self._config.ball_animation if self._config else "呼吸"
        mascot = self._mascot_name
        # 卡通形象始终需要动画（呼吸/眨眼），经典球按配置
        need_timer = bool(mascot) or (name and name != "关")
        if need_timer:
            if not self._anim_timer.isActive():
                self._anim_elapsed.start()
                self._anim_timer.start(1000 // ANIM_FPS)
        else:
            if self._anim_timer.isActive():
                self._anim_timer.stop()
            self._anim_time = 0
        self.update()

    def apply_mascot(self, name=None):
        """设置悬浮球形象（「经典球」/ None = 经典球模式），调整画布大小。"""
        old_size = self.width()
        # 经典球不是卡通形象，走经典球绘制
        self._mascot_name = (
            name if name in themes.MASCOTS and name != "经典球" else None
        )
        if self._mascot_name:
            new_w = MASCOT_SIZE + MASCOT_PADDING * 2
        else:
            new_w = BALL_SIZE + 16
        if new_w != old_size:
            # 按中心缩放位置，保持视觉重心不变
            cx = self.x() + old_size // 2
            cy = self.y() + old_size // 2
            self.setFixedSize(new_w, new_w)
            self.move(cx - new_w // 2, cy - new_w // 2)
        self.apply_animation()
        self.update()

    def _animation_name(self):
        if not self._config:
            return "呼吸"
        return self._config.ball_animation or "关"

    def _on_anim_tick(self):
        now = self._anim_elapsed.elapsed()
        dt = now - self._anim_time
        self._anim_time = now
        # 事件气泡年龄按真实时间推进（与帧率无关，30fps 下也不会变慢）
        if self._event_type is not None:
            self._event_age_ms += max(0, dt)
            if self._event_age_ms > 4000:
                self._event_type = None
        self.update()

    # ---------- 闪烁属性 ----------

    def _get_flash(self):
        return self._flash_strength

    def _set_flash(self, value):
        self._flash_strength = value
        self.update()

    flashStrength = Property(float, _get_flash, _set_flash)

    # 蹦跳偏移（px，0=地面，负值=跳起）— 由动画驱动
    def _get_hop(self):
        return self._hop_offset

    def _set_hop(self, value):
        self._hop_offset = value
        self.update()

    hopOffset = Property(float, _get_hop, _set_hop)

    def flash(self, added):
        """串口事件时的红/绿描边呼吸提示（主题色）。"""
        self._flash_color = (
            QColor(self._flash_added) if added else QColor(self._flash_removed)
        )
        self._flash_anim.stop()
        self._flash_anim.start()
        # 记录事件，供卡通形象说话/气泡
        self._event_type = "added" if added else "removed"
        self._event_age_ms = 0
        self.update()

    def set_port_count(self, count):
        self._port_count = count
        self.update()

    # ---------- 绘制 ----------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        cx = self.width() / 2
        cy = self.height() / 2

        # ========== 卡通形象模式 ==========
        if self._mascot_name:
            # 呼吸（mascots 内部用）
            phase = (self._anim_time % BREATH_PERIOD_MS) / BREATH_PERIOD_MS
            t_breath = math.sin(phase * math.pi * 2) * 0.5 + 0.5
            # 眨眼：每 3.5 秒眨一次，持续 0.18 秒
            blink_cycle = self._anim_time % 3500
            blink = 0.0
            if blink_cycle > 3300:
                blink = (blink_cycle - 3300) / 200.0
            # 事件年龄在 _on_anim_tick 中按真实时间推进，此处只读

            state = {
                "port_count": self._port_count,
                "event_type": self._event_type,
                "event_age_ms": self._event_age_ms,
                "blink": min(1.0, blink),
                "breath": t_breath,
                "anim_time": self._anim_time,
                "hop_offset": self._hop_offset,
            }
            draw_mascot(
                painter, self._mascot_name,
                cx, cy + self._hop_offset, MASCOT_SIZE, self._anim_time, state,
            )
            return

        # ========== 经典球模式 ==========
        # 球本体半径
        base_r = BALL_SIZE / 2 - 3

        anim = self._animation_name()
        t_breath = 0.0
        if anim == "呼吸":
            # 0~1 周期，正弦呼吸，1.0 基准，0.92~1.04 之间
            phase = (self._anim_time % BREATH_PERIOD_MS) / BREATH_PERIOD_MS
            t_breath = math.sin(phase * math.pi * 2) * 0.5 + 0.5
            scale = 0.94 + t_breath * 0.10  # 0.94 ~ 1.04
            ball_r = base_r * scale
            alpha_shift = int((t_breath - 0.5) * 20)  # -10 ~ +10
        else:
            ball_r = base_r
            alpha_shift = 0

        # 球体绘制矩形
        ball_rect = _circle_rect(cx, cy, ball_r)

        # ========== 动效底层（在球后面） ==========
        if anim == "脉冲光环":
            self._draw_pulse_rings(painter, cx, cy, base_r)
        elif anim == "旋转粒子":
            self._draw_rotating_particles(painter, cx, cy, base_r)

        # ========== 球体本体 ==========
        top, mid, bottom = self._ball_stops
        top_a = QColor(top)
        top_a.setAlpha(max(0, min(255, 210 + alpha_shift)))
        mid_a = QColor(mid)
        mid_a.setAlpha(max(0, min(255, 190 + alpha_shift)))
        bottom_a = QColor(bottom)
        bottom_a.setAlpha(max(0, min(255, 170 + alpha_shift)))

        gradient = QRadialGradient(
            cx - ball_r * 0.28, cy - ball_r * 0.28, ball_r * 1.8
        )
        gradient.setColorAt(0.0, top_a)
        gradient.setColorAt(0.65, mid_a)
        gradient.setColorAt(1.0, bottom_a)

        # 外发光边（细白边，增强立体感）
        painter.setPen(QPen(QColor(255, 255, 255, 55), 1))
        painter.setBrush(gradient)
        painter.drawEllipse(ball_rect)

        # 高光（左上的小亮斑）
        highlight = QRadialGradient(
            cx - ball_r * 0.35, cy - ball_r * 0.4, ball_r * 0.6
        )
        hl_color = QColor(255, 255, 255, 130)
        hl_color2 = QColor(255, 255, 255, 0)
        highlight.setColorAt(0.0, hl_color)
        highlight.setColorAt(1.0, hl_color2)
        painter.setPen(Qt.NoPen)
        painter.setBrush(highlight)
        painter.drawEllipse(_circle_rect(cx - ball_r * 0.25, cy - ball_r * 0.3, ball_r * 0.5))

        # 事件闪烁描边
        if self._flash_strength > 0.01:
            color = QColor(self._flash_color)
            color.setAlpha(int(235 * self._flash_strength))
            pen = QPen(color, 3)
            # 外发光效果：再画一圈更粗更淡的
            glow = QColor(color)
            glow.setAlpha(int(80 * self._flash_strength))
            painter.setPen(QPen(glow, 6))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(ball_rect)
            painter.setPen(pen)
            painter.drawEllipse(ball_rect)

        # ========== 文字 ==========
        count_color = QColor(self._ball_text)
        count_color.setAlpha(235)
        painter.setPen(count_color)
        font = QFont(self.font())
        font.setPointSize(15)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(
            ball_rect.adjusted(0, -5, 0, -5),
            Qt.AlignCenter,
            str(self._port_count),
        )

        font.setPointSize(6)
        font.setBold(False)
        painter.setFont(font)
        label_color = QColor(self._ball_text)
        label_color.setAlpha(170)
        painter.setPen(label_color)
        painter.drawText(ball_rect.adjusted(0, 16, 0, 0), Qt.AlignCenter, "串口")

    # ----- 动效绘制 -----

    def _draw_pulse_rings(self, painter, cx, cy, base_r):
        """脉冲光环：两圈向外扩散的波纹。"""
        period = PULSE_PERIOD_MS
        phase = (self._anim_time % period) / period  # 0~1
        # 两个环，错开半周期
        for i in range(2):
            p = (phase + i * 0.5) % 1.0
            # 从球表面扩张到 1.6 倍半径
            r = base_r * (1.0 + p * 0.7)
            # 透明度：中间高，两端低
            alpha = int(90 * (1.0 - abs(p - 0.5) * 2))
            if alpha <= 0:
                continue
            # 用主题的深色作环色
            _, _, bottom = self._ball_stops
            ring_color = QColor(bottom)
            ring_color.setAlpha(max(0, alpha))
            pen = QPen(ring_color, 2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(_circle_rect(cx, cy, r))

    def _draw_rotating_particles(self, painter, cx, cy, base_r):
        """旋转粒子：4 个发光点绕球旋转，内外两圈。"""
        period = PARTICLE_PERIOD_MS
        # 4 个粒子：2 个在 1.1r 处慢转，2 个在 0.85r 处快转
        particles = [
            # (半径比例, 角速度倍数, 大小, 起始相位, 颜色用渐变的哪一层)
            (1.12, 1.0, 3.5, 0.0, 0),   # 外1：主色
            (1.12, 1.0, 2.5, 0.5, 2),   # 外2：深色（对面）
            (0.82, -1.6, 2.8, 0.25, 1), # 内1：中间色 反向
            (0.82, -1.6, 2.0, 0.75, 0), # 内2：主色
        ]
        top, mid, bottom = self._ball_stops
        colors = [top, mid, bottom]

        for r_ratio, speed_mult, size, phase_off, color_idx in particles:
            angle = (self._anim_time / period * speed_mult + phase_off) * math.pi * 2
            r = base_r * r_ratio
            px = cx + math.cos(angle) * r
            py = cy + math.sin(angle) * r
            color = QColor(colors[color_idx])
            color.setAlpha(200)
            # 外发光
            glow = QColor(color)
            glow.setAlpha(70)
            painter.setPen(Qt.NoPen)
            painter.setBrush(glow)
            painter.drawEllipse(_circle_rect(px, py, size * 2.2))
            # 核心
            painter.setBrush(color)
            painter.drawEllipse(_circle_rect(px, py, size))

    # ---------- 拖拽 / 点击 ----------

    def showEvent(self, event):
        """每次显示时重新确保置顶，避免被其它窗口压盖。"""
        super().showEvent(event)
        self._ensure_on_top()
        self.apply_animation()

    def hideEvent(self, event):
        """隐藏时暂停动效，省 CPU。"""
        super().hideEvent(event)
        if self._anim_timer.isActive():
            self._anim_timer.stop()

    def _ensure_on_top(self):
        """强制置顶并抬升 Z 序。"""
        flags = self.windowFlags()
        if not (flags & Qt.WindowStaysOnTopHint):
            self.setWindowFlags(flags | Qt.WindowStaysOnTopHint)
            self.show()
        self.raise_()

    def mousePressEvent(self, event):
        if self._hop_group.state() == QAbstractAnimation.State.Running:
            return
        if event.button() == Qt.LeftButton:
            self._pressed = True
            self._dragging = False
            self._press_pos = event.globalPosition().toPoint() - self.pos()
            self._ensure_on_top()

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

    # ---------- 右键菜单 ----------

    def set_context_menu(self, menu):
        """设置右键菜单（与系统托盘共用同一个 QMenu）。"""
        self._menu = menu

    def contextMenuEvent(self, event):
        self.show_context_menu(event.globalPos())

    def show_context_menu(self, global_pos):
        """在指定屏幕坐标弹出菜单；未设置菜单时无操作。"""
        if self._menu is not None:
            self._menu.exec(global_pos)

    # ---------- 卡片 ----------

    def toggle_card(self):
        if self._card.isVisible():
            self._card.hide()
            self._stop_hop_cycle()
        else:
            self._card.auto_shown = False
            self.show_card()

    def show_card(self):
        self._card.show()
        QTimer.singleShot(0, lambda: self._card.move(self._card_pos()))
        # 卡片打开：启动绕卡跳跃循环（仅卡通形象）
        if self._mascot_name:
            self._hop_timer.start()
            self._hop_timer.setInterval(HOP_INTERVAL_MS)

    def hide_card(self):
        """关闭卡片（外部事件自动弹卡后也可能调用）。"""
        self._card.hide()
        self._stop_hop_cycle()

    def _stop_hop_cycle(self):
        self._hop_timer.stop()
        self._hop_group.stop()

    # ---------- 欢快蹦跳 ----------

    def _start_hop(self):
        """欢快蹦跳：窗口整体向上跳，连续 3 次一次比一次高。

        每步并行驱动 pos(向上) + hopOffset(拉伸)，卡片保持不动。
        """
        if not (self._mascot_name and self._card.isVisible()):
            return
        if self._hop_group.state() == QAbstractAnimation.State.Running:
            return

        base_x = self.x()
        base_y = self.y()
        heights = [18, 26, 34]  # 三次跳跃高度（px），递增
        self._hop_group.clear()
        for h in heights:
            # 上升：窗口上跳 + 拉伸 并行
            up = QParallelAnimationGroup(self._hop_group)
            move_up = QPropertyAnimation(self, b"pos", up)
            move_up.setDuration(190)
            move_up.setStartValue(QPoint(base_x, base_y))
            move_up.setEndValue(QPoint(base_x, base_y - h))
            move_up.setEasingCurve(QEasingCurve.OutQuad)
            up.addAnimation(move_up)
            stretch = QPropertyAnimation(self, b"hopOffset", up)
            stretch.setDuration(190)
            stretch.setStartValue(0.0)
            stretch.setEndValue(-h)
            stretch.setEasingCurve(QEasingCurve.OutQuad)
            up.addAnimation(stretch)
            self._hop_group.addAnimation(up)
            # 下降：窗口回位 + 拉伸归零 并行
            down = QParallelAnimationGroup(self._hop_group)
            move_down = QPropertyAnimation(self, b"pos", down)
            move_down.setDuration(190)
            move_down.setStartValue(QPoint(base_x, base_y - h))
            move_down.setEndValue(QPoint(base_x, base_y))
            move_down.setEasingCurve(QEasingCurve.InQuad)
            down.addAnimation(move_down)
            settle = QPropertyAnimation(self, b"hopOffset", down)
            settle.setDuration(190)
            settle.setStartValue(-h)
            settle.setEndValue(0.0)
            settle.setEasingCurve(QEasingCurve.InQuad)
            down.addAnimation(settle)
            self._hop_group.addAnimation(down)
        self._hop_group.start()

    def _on_hop_finished(self):
        """蹦跳结束：复位偏移，卡片跟随（如果还开着）。"""
        self._hop_offset = 0.0
        if self._card.isVisible():
            self._card.move(self._card_pos())

    def _card_pos(self):
        """卡片贴住形象本体，自适应屏幕边缘。"""
        screen = self.screen().availableGeometry()
        card = self._card
        gap = 8
        # 形象本体占窗口中央，边缘按本体计算（去掉 padding）
        if self._mascot_name:
            body = MASCOT_SIZE
            offset = (self.width() - body) // 2
        else:
            body = BALL_SIZE
            offset = (self.width() - body) // 2
        body_left = self.x() + offset
        body_right = body_left + body
        x = body_left - card.width() - gap  # 优先左侧
        if x < screen.left():
            x = body_right + gap  # 放不下改右侧
        y = self.y() + offset  # 跟本体顶对齐
        y = max(screen.top(), min(y, screen.bottom() - card.height()))
        x = max(screen.left(), min(x, screen.right() - card.width()))
        return QPoint(x, y)


def _circle_rect(cx, cy, r):
    """返回圆心 (cx, cy) 半径 r 对应的正方形 QRectF。"""
    from PySide6.QtCore import QRectF
    return QRectF(cx - r, cy - r, r * 2, r * 2)
