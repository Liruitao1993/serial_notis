# -*- coding: utf-8 -*-
"""可配置项：通知停留时长、自动弹卡、拔出提示等，config.json 持久化。

读取方式：config = AppConfig(); config.notify_lifetime_ms
写入方式：config.set("notify_lifetime_ms", 15000)  # 立即写盘
"""

import json
import logging
from contextlib import contextmanager

from app_paths import data_file

logger = logging.getLogger(__name__)

DEFAULTS = {
    "notify_lifetime_ms": 20000,  # 通知条停留时长（毫秒）
    "auto_show_card": True,       # 串口事件时自动弹出卡片
    "notify_on_remove": True,     # 拔出串口时也显示通知
    "ball_theme": "深空蓝",       # 悬浮球主题（themes.BALL_THEMES）
    "ball_mascot": "经典球",      # 悬浮球形象（themes.MASCOTS）
    "ball_animation": "呼吸",     # 悬浮球动效：关/呼吸/脉冲光环/旋转粒子
    "popup_duration_ms": 2500,    # Logo 弹框展示时长（毫秒），500~5000
    "card_theme": "深色",         # 卡片主题（themes.CARD_THEMES）
    "card_style": "卡片",         # 卡片风格（themes.CARD_STYLES）
    "card_radius": 12,            # 卡片圆角 0~24（0=直角）
    "card_width": 320,            # 卡片宽度 240~480
    "font_family": "",            # 字体族（空=跟随系统，设置对话框可选）
    "font_size": 12,              # 正文字号（标题/计数等按比例派生）
    "font_color": "",             # 字体颜色 #RRGGBB（空=跟随主题）
    "panel_alpha": 200,            # 卡片背景透明度 0~255
}

_CONFIG_FILE = data_file("config.json")


def _coerce(name, value):
    default = DEFAULTS[name]
    if isinstance(default, bool):
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return bool(value)
    if isinstance(default, int):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    return value


class AppConfig:
    """应用配置：带默认值、类型强制、立即持久化。"""

    def __init__(self, path=_CONFIG_FILE):
        self._path = path
        values = {k: _coerce(k, v) for k, v in self._load().items()}
        self._values = {**DEFAULTS, **values}
        self._deferred = False

    def _load(self):
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return {k: v for k, v in data.items() if k in DEFAULTS}
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            logger.exception("读取配置文件失败: %s", self._path)
        return {}

    def _save(self):
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._values, f, ensure_ascii=False, indent=2)
        except OSError:
            logger.exception("保存配置文件失败: %s", self._path)

    def __getattr__(self, name):
        if name in DEFAULTS:
            return self._values[name]
        raise AttributeError(name)

    @contextmanager
    def batch(self):
        """批量操作上下文：延迟写盘，退出时一次性保存。"""
        self._deferred = True
        try:
            yield
        finally:
            self._deferred = False
            self._save()

    def set(self, name, value):
        if name not in DEFAULTS:
            raise KeyError(name)
        self._values[name] = _coerce(name, value)
        if not self._deferred:
            self._save()
