# -*- coding: utf-8 -*-
"""卡通形象绘制：小奶龙、大白。

每个形象都是纯 QPainter 绘制，接收时间参数做呼吸/眨眼动画。
对外接口：
    draw_mascot(painter, mascot_name, cx, cy, size, anim_time_ms, state)
    state = {
        "port_count": int,    当前串口数
        "event_type": None | "added" | "removed",  最近事件
        "event_age_ms": int,  事件过去多久（0=刚发生）
        "blink": float,       眨眼 0.0~1.0（1=闭眼）
        "breath": float,      呼吸 0.0~1.0
    }
"""

import math
import os

from PySide6.QtCore import QRectF, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QRadialGradient, QLinearGradient, QPainterPath, QFont, QPixmap, Qt


# ---------- 图片形象 ----------

MASCOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "mascots")

_pixmap_cache = {}


def _load_pixmap(name):
    """按形象名加载 assets/mascots/{name}.png，带缓存。"""
    if name not in _pixmap_cache:
        path = os.path.join(MASCOT_DIR, f"{name}.png")
        pm = QPixmap(path)
        if pm.isNull():
            _pixmap_cache[name] = None
        else:
            _pixmap_cache[name] = pm
    return _pixmap_cache[name]


def has_image(name):
    """该形象是否有真实图片（assets/mascots/{name}.png）。"""
    return _load_pixmap(name) is not None


# ---------- 对外接口 ----------

def draw_mascot(painter, name, cx, cy, size, anim_time_ms, state):
    """在 (cx, cy) 绘制指定卡通形象，size 为整体直径。

    优先绘制真实图片（assets/mascots/{name}.png），无图时回退手绘。
    """
    pm = _load_pixmap(name)
    if pm is not None:
        _draw_image_mascot(painter, pm, cx, cy, size, anim_time_ms, state)
        # 对话气泡
        _draw_speech_bubble(painter, cx, cy, size, state)
        return

    painter.save()
    painter.translate(cx, cy)

    breath = state.get("breath", 0.5)
    # 呼吸轻微缩放
    scale = 0.97 + breath * 0.06
    painter.scale(scale, scale)

    if name == "小奶龙":
        _draw_baby_dragon(painter, size, state)
    elif name == "大白":
        _draw_baymax(painter, size, state)
    else:
        painter.restore()
        return

    painter.restore()

    # 对话气泡（不参与身体缩放，独立处理）
    _draw_speech_bubble(painter, cx, cy, size, state)


def _draw_image_mascot(painter, pm, cx, cy, size, anim_time_ms, state):
    """绘制图片形象：呼吸缩放 + 上下浮动 + 事件时说话缩放 + 蹦跳拉伸。"""
    breath = state.get("breath", 0.5)
    event_type = state.get("event_type")
    event_age = state.get("event_age_ms", 999999)
    hop_offset = state.get("hop_offset", 0.0)

    # 呼吸缩放（0.96~1.04）
    scale = 0.97 + breath * 0.06
    # 上下浮动（微幅）
    bob = math.sin(anim_time_ms / 800.0) * size * 0.02

    # 蹦跳压缩拉伸：跳起时竖向拉伸，落地时压扁
    squash_x, squash_y = 1.0, 1.0
    hop_scale = 1.0 + abs(hop_offset) / 60.0  # 越高拉伸越多
    if abs(hop_offset) < 1e-3:
        # 落地瞬间微压缩（如果刚跳完）
        squash_x, squash_y = 1.0, 1.0
    else:
        # 在空中：纵向拉伸，横向略收
        squash_x = 1.0 - (hop_scale - 1.0) * 0.5
        squash_y = hop_scale

    # 说话：张嘴时轻微缩放弹动（模拟说话）
    talk_scale = 1.0
    if event_type and event_age < 1200:
        talk_scale = 1.0 + 0.04 * math.sin(event_age / 90)

    painter.save()
    painter.translate(cx, cy + bob)
    painter.scale(scale * talk_scale * squash_x, scale * talk_scale * squash_y)

    # 按长宽比缩放，保持比例
    target = size * 0.95
    ratio = pm.width() / max(1, pm.height())
    if ratio >= 1.0:
        w, h = target, target / ratio
    else:
        w, h = target * ratio, target
    rect = QRectF(-w / 2, -h / 2, w, h)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    painter.drawPixmap(rect, pm, QRectF(0, 0, pm.width(), pm.height()))

    # 底部小阴影（贴地感）
    shadow_r = size * 0.28
    shadow_alpha = int(35 * (1.0 - abs(breath - 0.5) * 2))
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setBrush(QColor(0, 0, 0, max(10, shadow_alpha)))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(QRectF(-shadow_r, size * 0.42, shadow_r * 2, size * 0.08))

    painter.restore()


# ---------- 小奶龙 ----------

def _draw_baby_dragon(painter, size, state):
    """Q 版奶绿小奶龙：圆身体、小翅膀、犄角、大眼、微微笑。"""
    r = size * 0.42  # 身体半径

    blink = state.get("blink", 0.0)
    event_type = state.get("event_type")
    event_age = state.get("event_age_ms", 999999)
    talking = event_type and event_age < 1200

    # 身体颜色：奶绿渐变
    body_light = QColor(180, 230, 160)
    body_mid = QColor(120, 200, 120)
    body_dark = QColor(80, 160, 90)
    belly = QColor(220, 245, 200)

    # ---- 小翅膀（身体后面，先画） ----
    wing_color = QColor(140, 210, 140)
    wing_dark = QColor(90, 170, 100)
    # 左翅
    path = QPainterPath()
    path.moveTo(-r * 0.7, -r * 0.1)
    path.quadTo(-r * 1.4, -r * 0.7, -r * 1.2, r * 0.2)
    path.quadTo(-r * 0.9, r * 0.05, -r * 0.65, r * 0.15)
    path.closeSubpath()
    painter.setPen(QPen(wing_dark, 1.2))
    painter.setBrush(wing_color)
    painter.drawPath(path)
    # 右翅
    path = QPainterPath()
    path.moveTo(r * 0.7, -r * 0.1)
    path.quadTo(r * 1.4, -r * 0.7, r * 1.2, r * 0.2)
    path.quadTo(r * 0.9, r * 0.05, r * 0.65, r * 0.15)
    path.closeSubpath()
    painter.drawPath(path)

    # ---- 身体（椭圆，上圆下稍宽） ----
    body_rect = QRectF(-r * 1.0, -r * 0.95, r * 2.0, r * 2.0)
    body_grad = QRadialGradient(-r * 0.3, -r * 0.4, r * 1.5)
    body_grad.setColorAt(0.0, body_light)
    body_grad.setColorAt(0.5, body_mid)
    body_grad.setColorAt(1.0, body_dark)
    painter.setPen(QPen(body_dark, 1.5))
    painter.setBrush(body_grad)
    painter.drawEllipse(body_rect)

    # ---- 肚皮（浅色椭圆） ----
    belly_rect = QRectF(-r * 0.55, r * 0.05, r * 1.1, r * 0.8)
    belly_grad = QRadialGradient(0, r * 0.3, r * 0.7)
    belly_grad.setColorAt(0.0, belly)
    belly_grad.setColorAt(1.0, QColor(190, 225, 180))
    painter.setPen(Qt.NoPen)
    painter.setBrush(belly_grad)
    painter.drawEllipse(belly_rect)

    # ---- 犄角（两只小犄角） ----
    horn_color = QColor(250, 230, 180)
    horn_dark = QColor(200, 170, 120)
    painter.setPen(QPen(horn_dark, 1))
    painter.setBrush(horn_color)
    # 左犄角
    horn_path = QPainterPath()
    horn_path.moveTo(-r * 0.45, -r * 0.85)
    horn_path.lineTo(-r * 0.55, -r * 1.25)
    horn_path.lineTo(-r * 0.3, -r * 0.95)
    horn_path.closeSubpath()
    painter.drawPath(horn_path)
    # 右犄角
    horn_path = QPainterPath()
    horn_path.moveTo(r * 0.45, -r * 0.85)
    horn_path.lineTo(r * 0.55, -r * 1.25)
    horn_path.lineTo(r * 0.3, -r * 0.95)
    horn_path.closeSubpath()
    painter.drawPath(horn_path)

    # ---- 小耳朵 ----
    ear_color = QColor(130, 190, 130)
    painter.setBrush(ear_color)
    painter.setPen(QPen(body_dark, 1))
    # 左耳
    path = QPainterPath()
    path.moveTo(-r * 0.85, -r * 0.5)
    path.quadTo(-r * 1.1, -r * 0.85, -r * 0.8, -r * 0.2)
    path.closeSubpath()
    painter.drawPath(path)
    # 右耳
    path = QPainterPath()
    path.moveTo(r * 0.85, -r * 0.5)
    path.quadTo(r * 1.1, -r * 0.85, r * 0.8, -r * 0.2)
    path.closeSubpath()
    painter.drawPath(path)

    # ---- 眼睛（大而圆） ----
    eye_y = -r * 0.25
    eye_r = r * 0.22
    eye_offset = r * 0.32

    if blink > 0.9:
        # 闭眼：一条弧线
        painter.setPen(QPen(QColor(40, 60, 40), 2))
        painter.setBrush(Qt.NoBrush)
        # 左眼
        path = QPainterPath()
        path.arcMoveTo(QRectF(-eye_offset - eye_r, eye_y - eye_r * 0.3, eye_r * 2, eye_r * 0.6), 180)
        path.arcTo(QRectF(-eye_offset - eye_r, eye_y - eye_r * 0.3, eye_r * 2, eye_r * 0.6), 180, 180)
        painter.drawPath(path)
        # 右眼
        path = QPainterPath()
        path.arcMoveTo(QRectF(eye_offset - eye_r, eye_y - eye_r * 0.3, eye_r * 2, eye_r * 0.6), 180)
        path.arcTo(QRectF(eye_offset - eye_r, eye_y - eye_r * 0.3, eye_r * 2, eye_r * 0.6), 180, 180)
        painter.drawPath(path)
    else:
        eye_h_scale = 1.0 - blink * 0.7  # 半闭眼
        # 眼白
        white = QColor(255, 255, 255)
        painter.setPen(QPen(QColor(60, 80, 60), 1.5))
        painter.setBrush(white)
        # 左眼
        _draw_ellipse(painter, -eye_offset, eye_y, eye_r, eye_r * eye_h_scale)
        # 右眼
        _draw_ellipse(painter, eye_offset, eye_y, eye_r, eye_r * eye_h_scale)
        # 黑眼珠（带高光）
        pupil_r = eye_r * 0.55
        pupil_color = QColor(30, 50, 35)
        painter.setPen(Qt.NoPen)
        painter.setBrush(pupil_color)
        _draw_ellipse(painter, -eye_offset + eye_r * 0.1, eye_y + eye_r * 0.05, pupil_r, pupil_r * eye_h_scale)
        _draw_ellipse(painter, eye_offset + eye_r * 0.1, eye_y + eye_r * 0.05, pupil_r, pupil_r * eye_h_scale)
        # 高光点
        hl = QColor(255, 255, 255)
        painter.setBrush(hl)
        hl_r = eye_r * 0.2
        _draw_ellipse(painter, -eye_offset - eye_r * 0.15, eye_y - eye_r * 0.2, hl_r, hl_r * eye_h_scale)
        _draw_ellipse(painter, eye_offset - eye_r * 0.15, eye_y - eye_r * 0.2, hl_r, hl_r * eye_h_scale)

    # ---- 腮红（萌萌哒） ----
    blush = QColor(255, 150, 160, 90)
    painter.setBrush(blush)
    painter.setPen(Qt.NoPen)
    _draw_ellipse(painter, -r * 0.55, r * 0.1, r * 0.18, r * 0.1)
    _draw_ellipse(painter, r * 0.55, r * 0.1, r * 0.18, r * 0.1)

    # ---- 鼻子（两个小点） ----
    nose_color = QColor(60, 80, 60)
    painter.setBrush(nose_color)
    _draw_ellipse(painter, -r * 0.08, r * 0.02, r * 0.05, r * 0.04)
    _draw_ellipse(painter, r * 0.08, r * 0.02, r * 0.05, r * 0.04)

    # ---- 嘴巴 ----
    mouth_y = r * 0.22
    painter.setPen(QPen(QColor(60, 80, 60), 1.8))
    painter.setBrush(Qt.NoBrush)
    if talking:
        # 张嘴说话：O 形
        mouth_open = min(1.0, event_age / 300) if event_age < 300 else (
            0.5 + 0.5 * math.sin(event_age / 80)
        )
        mh = r * 0.12 * mouth_open
        path = QPainterPath()
        path.addEllipse(QRectF(-r * 0.1, mouth_y - mh * 0.5, r * 0.2, mh * 2))
        painter.setBrush(QColor(200, 80, 100))
        painter.drawPath(path)
    else:
        # 微笑：弯弯的线
        path = QPainterPath()
        path.moveTo(-r * 0.15, mouth_y)
        path.quadTo(0, mouth_y + r * 0.1, r * 0.15, mouth_y)
        painter.drawPath(path)

    # ---- 小手（短手） ----
    hand_color = QColor(130, 190, 130)
    painter.setPen(QPen(body_dark, 1.2))
    painter.setBrush(hand_color)
    # 左手
    _draw_ellipse(painter, -r * 0.95, r * 0.35, r * 0.18, r * 0.22)
    # 右手
    _draw_ellipse(painter, r * 0.95, r * 0.35, r * 0.18, r * 0.22)

    # ---- 小脚 ----
    foot_color = QColor(250, 220, 150)
    painter.setPen(QPen(horn_dark, 1))
    painter.setBrush(foot_color)
    # 左脚
    _draw_ellipse(painter, -r * 0.4, r * 0.92, r * 0.28, r * 0.12)
    # 右脚
    _draw_ellipse(painter, r * 0.4, r * 0.92, r * 0.28, r * 0.12)

    # ---- 尾巴（小卷） ----
    tail_color = QColor(120, 200, 120)
    painter.setPen(QPen(body_dark, 1.2))
    painter.setBrush(tail_color)
    path = QPainterPath()
    path.moveTo(r * 0.85, r * 0.6)
    path.quadTo(r * 1.3, r * 0.4, r * 1.2, r * 0.1)
    path.quadTo(r * 1.1, r * 0.25, r * 0.95, r * 0.5)
    path.closeSubpath()
    painter.drawPath(path)


# ---------- 大白 ----------

def _draw_baymax(painter, size, state):
    """大白：白色圆胖充气机器人，椭圆形身体，细黑眼睛线。"""
    r = size * 0.42

    blink = state.get("blink", 0.0)
    event_type = state.get("event_type")
    event_age = state.get("event_age_ms", 999999)
    talking = event_type and event_age < 1200

    # 颜色
    body_white = QColor(252, 252, 252)
    body_mid = QColor(235, 238, 242)
    body_shadow = QColor(200, 208, 218)
    line_black = QColor(40, 45, 55)

    # ---- 身体（大椭圆，竖椭圆） ----
    body_rect = QRectF(-r * 0.95, -r * 0.85, r * 1.9, r * 1.95)
    body_grad = QRadialGradient(-r * 0.3, -r * 0.4, r * 1.5)
    body_grad.setColorAt(0.0, body_white)
    body_grad.setColorAt(0.55, body_mid)
    body_grad.setColorAt(1.0, body_shadow)
    painter.setPen(QPen(QColor(180, 190, 205), 1.5))
    painter.setBrush(body_grad)
    painter.drawEllipse(body_rect)

    # ---- 头（稍小的圆，与身体融合） ----
    head_r = r * 0.6
    head_cy = -r * 0.7
    head_rect = QRectF(-head_r, head_cy - head_r, head_r * 2, head_r * 2)
    head_grad = QRadialGradient(-head_r * 0.3, head_cy - head_r * 0.3, head_r * 1.3)
    head_grad.setColorAt(0.0, body_white)
    head_grad.setColorAt(0.7, body_mid)
    head_grad.setColorAt(1.0, QColor(210, 218, 228))
    painter.setPen(QPen(QColor(190, 200, 215), 1.2))
    painter.setBrush(head_grad)
    painter.drawEllipse(head_rect)

    # ---- 眼睛（经典大白：两个小圆点 + 一条横线连接） ----
    eye_y = head_cy - head_r * 0.05
    eye_r = head_r * 0.13
    eye_dist = head_r * 0.45

    if blink > 0.9:
        # 闭眼：两道短横线
        painter.setPen(QPen(line_black, 2.5))
        painter.drawLine(QPointF(-eye_dist - eye_r, eye_y), QPointF(-eye_dist + eye_r, eye_y))
        painter.drawLine(QPointF(eye_dist - eye_r, eye_y), QPointF(eye_dist + eye_r, eye_y))
    else:
        eye_h_scale = 1.0 - blink * 0.6
        # 连接线（中间细细的）
        path = QPainterPath()
        path.moveTo(-eye_dist + eye_r * 0.8, eye_y)
        path.cubicTo(
            -eye_dist * 0.3, eye_y - eye_r * 0.3,
            eye_dist * 0.3, eye_y - eye_r * 0.3,
            eye_dist - eye_r * 0.8, eye_y
        )
        painter.setPen(QPen(line_black, 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
        # 左眼
        painter.setPen(Qt.NoPen)
        painter.setBrush(line_black)
        _draw_ellipse(painter, -eye_dist, eye_y, eye_r, eye_r * eye_h_scale)
        # 右眼
        _draw_ellipse(painter, eye_dist, eye_y, eye_r, eye_r * eye_h_scale)

    # ---- 胸口圆形标志 ----
    chest_y = r * 0.05
    chest_r = r * 0.15
    chest_grad = QRadialGradient(-chest_r * 0.3, chest_y - chest_r * 0.3, chest_r * 1.2)
    chest_grad.setColorAt(0.0, QColor(180, 220, 255))
    chest_grad.setColorAt(0.6, QColor(120, 180, 240))
    chest_grad.setColorAt(1.0, QColor(60, 120, 200))
    painter.setBrush(chest_grad)
    painter.setPen(QPen(QColor(80, 140, 210), 1.2))
    _draw_ellipse(painter, 0, chest_y, chest_r, chest_r)
    # 标志里的小心形（简化成两个小圆+三角）
    heart_color = QColor(255, 255, 255, 200)
    painter.setBrush(heart_color)
    painter.setPen(Qt.NoPen)
    hr = chest_r * 0.4
    hy = chest_y - hr * 0.1
    _draw_ellipse(painter, -hr * 0.5, hy, hr * 0.55, hr * 0.5)
    _draw_ellipse(painter, hr * 0.5, hy, hr * 0.55, hr * 0.5)
    path = QPainterPath()
    path.moveTo(-hr * 0.95, hy + hr * 0.1)
    path.lineTo(0, hy + hr * 0.7)
    path.lineTo(hr * 0.95, hy + hr * 0.1)
    path.closeSubpath()
    painter.drawPath(path)

    # ---- 手臂（短短粗粗） ----
    arm_color = body_mid
    arm_shadow = body_shadow
    painter.setPen(QPen(QColor(190, 200, 215), 1.2))
    arm_grad = QLinearGradient(0, 0, r * 0.25, 0)
    arm_grad.setColorAt(0.0, body_white)
    arm_grad.setColorAt(1.0, arm_shadow)
    painter.setBrush(arm_grad)
    # 左手臂
    _draw_ellipse(painter, -r * 1.05, r * 0.15, r * 0.2, r * 0.45)
    # 右手臂
    _draw_ellipse(painter, r * 1.05, r * 0.15, r * 0.2, r * 0.45)

    # ---- 腿（短短的） ----
    leg_grad = QLinearGradient(0, r * 0.5, 0, r * 1.0)
    leg_grad.setColorAt(0.0, body_mid)
    leg_grad.setColorAt(1.0, body_shadow)
    painter.setBrush(leg_grad)
    painter.setPen(QPen(QColor(190, 200, 215), 1.2))
    _draw_ellipse(painter, -r * 0.35, r * 0.85, r * 0.22, r * 0.18)
    _draw_ellipse(painter, r * 0.35, r * 0.85, r * 0.22, r * 0.18)

    # ---- 嘴巴 ----
    mouth_y = head_cy + head_r * 0.35
    painter.setPen(QPen(line_black, 1.5))
    painter.setBrush(Qt.NoBrush)
    if talking:
        mouth_open = 0.5 + 0.5 * math.sin(event_age / 80)
        mh = head_r * 0.1 * mouth_open
        path = QPainterPath()
        path.addEllipse(QRectF(-head_r * 0.06, mouth_y - mh * 0.5, head_r * 0.12, mh * 2))
        painter.setBrush(QColor(150, 160, 175))
        painter.drawPath(path)
    else:
        # 大白是一条直线嘴（极简）
        painter.drawLine(QPointF(-head_r * 0.08, mouth_y), QPointF(head_r * 0.08, mouth_y))


# ---------- 对话气泡 ----------

def _draw_speech_bubble(painter, cx, cy, size, state):
    """画对话气泡 + 周期吐泡泡。

    事件刚发生：右上角弹事件气泡（+1 新串口 / -1 已拔出）。
    平时：小奶龙周期性从嘴里吐大泡泡，泡泡里显示串口数量。
    """
    event_type = state.get("event_type")
    event_age = state.get("event_age_ms", 999999)
    port_count = state.get("port_count", 0)
    anim_time = state.get("anim_time", 0)

    # 事件刚发生：弹事件气泡
    if event_type and event_age < 1500:
        # 弹入动画
        if event_age < 200:
            scale = event_age / 200
        elif event_age > 1200:
            scale = max(0, 1.0 - (event_age - 1200) / 300)
        else:
            scale = 1.0
        if scale <= 0:
            return

        if event_type == "added":
            text = "+1"
            sub = "新串口"
            color = QColor(46, 204, 113)
        else:
            text = "-1"
            sub = "已拔出"
            color = QColor(231, 76, 60)

        _draw_bubble(painter, cx + size * 0.3, cy - size * 0.45,
                     size * 0.38, size * 0.32,
                     text, sub, color, scale)
        return

    # 平时：周期性吐泡泡（每 3 秒一个，从嘴里吐出，上升 + 放大 + 淡出）
    bubble_cycle_ms = 3000
    t = (anim_time % bubble_cycle_ms) / bubble_cycle_ms  # 0~1
    if t > 0.05:  # 延迟一点开始（像从嘴里酝酿）
        # 上升进度
        rise = (t - 0.05) / 0.95
        # 嘴巴位置（形象下部偏中）
        mouth_x = cx + size * 0.06
        mouth_y = cy + size * 0.24
        # 泡泡从嘴向上浮出
        bx = mouth_x + rise * size * 0.1
        by = mouth_y - rise * size * 0.6
        # 尺寸：快速放大到最大再保持（大泡泡）
        grow = min(1.0, rise * 3.0)
        bubble_w = size * 0.44 * (0.3 + 0.7 * grow)   # 椭圆宽
        bubble_h = size * 0.30 * (0.3 + 0.7 * grow)   # 椭圆高
        # 透明度：淡入淡出
        alpha = min(1.0, rise * 4.0) * max(0.0, 1.0 - rise * 1.2)
        if alpha > 0.05 and bubble_w > 4:
            _draw_mouth_bubble(painter, bx, by, bubble_w, bubble_h,
                               port_count, alpha, mouth_x, mouth_y)


def _draw_mouth_bubble(painter, bx, by, bw, bh, port_count, alpha,
                       tip_x, tip_y):
    """从嘴里吐出的椭圆气泡：白色实心 + 深蓝描边 + 底部尖角 + 深蓝粗体大数字。

    高对比度：白底深蓝字，任何背景上都清晰。
    """
    painter.save()
    painter.setOpacity(alpha)

    # 气泡本体：白色实心椭圆
    rect = QRectF(bx - bw / 2, by - bh / 2, bw, bh)
    painter.setBrush(QColor(255, 255, 255, 250))
    painter.setPen(QPen(QColor(30, 70, 140), 2.5))
    painter.drawEllipse(rect)

    # 底部尖角（指向嘴巴）
    path = QPainterPath()
    # 尖角底部贴到嘴位置
    tip_h = bh * 0.35
    tip = QPointF(tip_x, tip_y)
    # 计算椭圆底部中心
    base = QPointF(bx, by + bh / 2)
    path.moveTo(base.x() - bw * 0.18, base.y() - 1)
    path.lineTo(tip.x(), tip.y())
    path.lineTo(base.x() + bw * 0.18, base.y() - 1)
    path.closeSubpath()
    painter.setBrush(QColor(255, 255, 255, 250))
    painter.setPen(QPen(QColor(30, 70, 140), 2.5))
    painter.drawPath(path)
    # 尖角底边补白线盖住边框
    painter.setPen(QPen(QColor(255, 255, 255, 250), 3))
    painter.drawLine(QPointF(base.x() - bw * 0.17, base.y() - 0.5),
                     QPointF(base.x() + bw * 0.17, base.y() - 0.5))

    # 数字：深蓝粗体大字，加白色描边增强对比
    font = QFont()
    font.setBold(True)
    font.setPointSize(max(10, int(bh * 0.62)))
    painter.setFont(font)

    # 白色描边（8 方向外扩）
    _draw_text_outline(painter, bx, by, str(port_count), font)

    # 主文字：深蓝
    painter.setPen(QColor(20, 50, 110))
    painter.setFont(font)
    painter.drawText(QRectF(rect.left(), rect.top(), rect.width(), rect.height()),
                     Qt.AlignCenter, str(port_count))

    # 小高光点（左上）
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(200, 225, 255, 120))
    painter.drawEllipse(
        QRectF(rect.left() + bw * 0.12, rect.top() + bh * 0.12,
               bw * 0.10, bh * 0.12)
    )

    painter.restore()


def _draw_text_outline(painter, bx, by, text, font):
    """给文字画一圈白色描边（8 方向偏移），增强对比。"""
    painter.save()
    painter.setPen(QPen(QColor(255, 255, 255), max(2.5, font.pointSize() * 0.15)))
    painter.setFont(font)
    fm = painter.fontMetrics()
    tw = fm.horizontalAdvance(text)
    th = fm.height()
    x = bx - tw / 2
    y = by - th / 2 + fm.ascent()
    for dx, dy in [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(1,-1),(-1,1),(1,1)]:
        painter.drawText(QPointF(x + dx, y + dy), text)
    painter.restore()


def _draw_bubble(painter, bx, by, bw, bh, text, sub, color, scale):
    """画一个圆角对话气泡，带小尖角指向左下角。"""
    painter.save()
    painter.translate(bx, by)
    painter.scale(scale, scale)

    # 圆角矩形
    rect = QRectF(-bw / 2, -bh / 2, bw, bh)
    radius = bh * 0.35

    # 阴影
    painter.setPen(Qt.NoPen)
    shadow = QColor(0, 0, 0, 30)
    painter.setBrush(shadow)
    painter.drawRoundedRect(rect.adjusted(1, 2, 1, 2), radius, radius)

    # 气泡主体（白底 + 主题色边框）
    painter.setBrush(QColor(255, 255, 255, 245))
    painter.setPen(QPen(color, 2))
    painter.drawRoundedRect(rect, radius, radius)

    # 小尖角（指向左下）
    path = QPainterPath()
    tip_w = bh * 0.25
    path.moveTo(-bw * 0.3, bh / 2)
    path.lineTo(-bw * 0.3 - tip_w, bh / 2 + tip_w * 0.8)
    path.lineTo(-bw * 0.15, bh / 2)
    path.closeSubpath()
    painter.setBrush(QColor(255, 255, 255, 245))
    painter.setPen(QPen(color, 2))
    painter.drawPath(path)
    # 尖角底部补一条白线覆盖边框
    painter.setPen(QPen(QColor(255, 255, 255, 245), 2.5))
    painter.drawLine(QPointF(-bw * 0.29, bh / 2 + 0.5), QPointF(-bw * 0.16, bh / 2 + 0.5))

    # 文字：大字 + 小字
    painter.setPen(color)
    font = QFont()
    font.setBold(True)
    font.setPointSize(max(7, int(bh * 0.35)))
    painter.setFont(font)
    painter.drawText(
        QRectF(rect.left(), rect.top() + bh * 0.05, rect.width(), bh * 0.5),
        Qt.AlignCenter,
        text,
    )
    font.setBold(False)
    font.setPointSize(max(5, int(bh * 0.18)))
    painter.setFont(font)
    sub_color = QColor(color)
    sub_color.setAlpha(200)
    painter.setPen(sub_color)
    painter.drawText(
        QRectF(rect.left(), rect.top() + bh * 0.5, rect.width(), bh * 0.4),
        Qt.AlignCenter,
        sub,
    )

    painter.restore()


# ---------- 工具 ----------

def _draw_ellipse(painter, cx, cy, rx, ry):
    painter.drawEllipse(QRectF(cx - rx, cy - ry, rx * 2, ry * 2))
