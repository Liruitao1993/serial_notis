# -*- coding: utf-8 -*-
"""外观主题注册表：悬浮球主题、卡片主题、卡片风格。

新增主题只需在对应字典加一项，设置对话框与 QSS 生成都从这里取数。
每个主题必须包含全部键（tests/test_themes.py 强制校验完整性）。

颜色约定：
- 表面色用 (r, g, b, a) 四元组（透明度可被样式/滑条调制）
- 文字色用 "#RRGGBB" 十六进制
- 通知条色为 (背景, 边框, 文字色) 三元组
"""

# 悬浮球主题：渐变双色 + 文字色 + 插拔闪动色
BALL_THEMES = {
    "深空蓝": {
        "grad": ("#6EA0FA", "#3A5CDC"),
        "text": "#FFFFFF",
        "flash_added": "#78DC8C",
        "flash_removed": "#E65050",
    },
    "云白": {
        "grad": ("#EAF2FF", "#8FB8FF"),
        "text": "#1F2D3D",
        "flash_added": "#10B981",
        "flash_removed": "#EF4444",
    },
    "极光紫": {
        "grad": ("#C39BFF", "#7C3AED"),
        "text": "#FFFFFF",
        "flash_added": "#34D399",
        "flash_removed": "#F43F5E",
    },
    "薄荷": {
        "grad": ("#7CF5C3", "#10B981"),
        "text": "#FFFFFF",
        "flash_added": "#059669",
        "flash_removed": "#EF4444",
    },
    "黑金": {
        "grad": ("#FFD75E", "#C9960C"),
        "text": "#3A2B00",
        "flash_added": "#34D399",
        "flash_removed": "#F43F5E",
    },
    "珊瑚": {
        "grad": ("#FFB3A7", "#FF6B6B"),
        "text": "#FFFFFF",
        "flash_added": "#10B981",
        "flash_removed": "#DC2626",
    },
}

# 卡片主题：面板 / 边框 / 分隔线 / 文字 / 行态 / 通知条
CARD_THEMES = {
    "深色": {
        "panel": (40, 44, 52),
        "border": (255, 255, 255, 30),
        "line": (255, 255, 255, 40),
        "title": "#FFFFFF",
        "count": (255, 255, 255, 170),
        "text": "#F0F6FC",
        "muted": (255, 255, 255, 130),
        "row_bg": (0, 0, 0, 0),
        "row_border": (0, 0, 0, 0),
        "row_selected_bg": (100, 170, 255, 55),
        "row_selected_border": (130, 200, 255, 100),
        "notify_added": ("rgba(120,220,140,90)", "rgba(120,220,140,140)", "#FFFFFF"),
        "notify_removed": ("rgba(230,80,80,90)", "rgba(230,80,80,150)", "#FFFFFF"),
    },
    "云白": {
        "panel": (245, 247, 250),
        "border": (15, 23, 42, 40),
        "line": (15, 23, 42, 25),
        "title": "#1F2937",
        "count": (31, 41, 55, 140),
        "text": "#374151",
        "muted": (107, 114, 128, 220),
        "row_bg": (0, 0, 0, 0),
        "row_border": (0, 0, 0, 0),
        "row_selected_bg": (59, 130, 246, 40),
        "row_selected_border": (59, 130, 246, 130),
        "notify_added": ("rgba(16,185,129,40)", "rgba(16,185,129,140)", "#065F46"),
        "notify_removed": ("rgba(239,68,68,38)", "rgba(239,68,68,140)", "#991B1B"),
    },
    "极光紫": {
        "panel": (38, 30, 54),
        "border": (196, 140, 255, 70),
        "line": (196, 140, 255, 45),
        "title": "#EDE7FF",
        "count": (237, 231, 255, 150),
        "text": "#E6DFFF",
        "muted": (237, 231, 255, 140),
        "row_bg": (0, 0, 0, 0),
        "row_border": (0, 0, 0, 0),
        "row_selected_bg": (167, 90, 255, 60),
        "row_selected_border": (196, 140, 255, 150),
        "notify_added": ("rgba(52,211,153,50)", "rgba(52,211,153,150)", "#D1FAE5"),
        "notify_removed": ("rgba(244,63,94,50)", "rgba(244,63,94,150)", "#FFE4E6"),
    },
    "薄荷": {
        "panel": (236, 253, 245),
        "border": (16, 185, 129, 80),
        "line": (16, 185, 129, 35),
        "title": "#064E3B",
        "count": (6, 78, 59, 150),
        "text": "#14532D",
        "muted": (6, 95, 70, 200),
        "row_bg": (0, 0, 0, 0),
        "row_border": (0, 0, 0, 0),
        "row_selected_bg": (16, 185, 129, 45),
        "row_selected_border": (16, 185, 129, 140),
        "notify_added": ("rgba(16,185,129,50)", "rgba(16,185,129,150)", "#064E3B"),
        "notify_removed": ("rgba(239,68,68,40)", "rgba(239,68,68,140)", "#7F1D1D"),
    },
    "黑金": {
        "panel": (24, 24, 26),
        "border": (245, 197, 24, 80),
        "line": (245, 197, 24, 45),
        "title": "#FFD75E",
        "count": (245, 197, 24, 180),
        "text": "#F5F5F4",
        "muted": (245, 245, 244, 140),
        "row_bg": (0, 0, 0, 0),
        "row_border": (0, 0, 0, 0),
        "row_selected_bg": (245, 197, 24, 50),
        "row_selected_border": (245, 197, 24, 150),
        "notify_added": ("rgba(52,211,153,50)", "rgba(52,211,153,150)", "#D1FAE5"),
        "notify_removed": ("rgba(244,63,94,50)", "rgba(244,63,94,150)", "#FFE4E6"),
    },
    "珊瑚": {
        "panel": (255, 244, 240),
        "border": (255, 107, 107, 80),
        "line": (255, 107, 107, 40),
        "title": "#9A3412",
        "count": (154, 52, 18, 160),
        "text": "#7C2D12",
        "muted": (154, 52, 18, 170),
        "row_bg": (0, 0, 0, 0),
        "row_border": (0, 0, 0, 0),
        "row_selected_bg": (255, 107, 107, 45),
        "row_selected_border": (255, 107, 107, 140),
        "notify_added": ("rgba(16,185,129,50)", "rgba(16,185,129,150)", "#065F46"),
        "notify_removed": ("rgba(239,68,68,40)", "rgba(239,68,68,140)", "#7F1D1D"),
    },
}

# 卡片风格：对圆角/边框/背景的样式化处理
CARD_STYLES = {
    "卡片": {"radius_bonus": 0, "radius_min": 0, "border_alpha": 1.0, "gradient": None},
    "气泡": {"radius_bonus": 6, "radius_min": 18, "border_alpha": 1.5, "gradient": "light"},
    "极简": {"radius_bonus": -4, "radius_min": 0, "border_alpha": 0.5, "gradient": None},
}

RADIUS_MIN = 0
RADIUS_MAX = 24


def resolve_radius(user_radius, style_name):
    """按风格把用户圆角值解析为最终半径（0=直角）。"""
    try:
        radius = int(user_radius)
    except (TypeError, ValueError):
        radius = 0
    style = CARD_STYLES.get(style_name, CARD_STYLES["卡片"])
    return min(RADIUS_MAX, max(style["radius_min"], radius + style["radius_bonus"]))


def ball_theme(name):
    return BALL_THEMES.get(name, BALL_THEMES["深空蓝"])


def card_theme(name):
    return CARD_THEMES.get(name, CARD_THEMES["深色"])


def card_style(name):
    return CARD_STYLES.get(name, CARD_STYLES["卡片"])
