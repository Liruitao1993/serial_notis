# -*- coding: utf-8 -*-
"""可配置项：通知停留时长、自动弹卡、拔出提示等，config.json 持久化。

读取方式：config = AppConfig(); config.notify_lifetime_ms
写入方式：config.set("notify_lifetime_ms", 15000)  # 立即写盘
"""

import json
import logging

from app_paths import data_file

logger = logging.getLogger(__name__)

DEFAULTS = {
    "notify_lifetime_ms": 20000,  # 通知条停留时长（毫秒）
    "auto_show_card": True,       # 串口事件时自动弹出卡片
    "notify_on_remove": True,     # 拔出串口时也显示通知
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

    def set(self, name, value):
        if name not in DEFAULTS:
            raise KeyError(name)
        self._values[name] = _coerce(name, value)
        self._save()
