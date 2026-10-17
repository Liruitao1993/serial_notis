# -*- coding: utf-8 -*-
"""串口备注名持久化存储。

以 JSON 文件保存 {COM口: 备注名}，程序目录下 port_aliases.json，
修改备注立即写盘，下次启动自动加载。
"""

import json
import logging
from contextlib import contextmanager

from app_paths import data_file

logger = logging.getLogger(__name__)

_ALIAS_FILE = data_file("port_aliases.json")


class AliasStore:
    """串口备注名存储：get / set，set 时立即持久化。"""

    def __init__(self, path=_ALIAS_FILE):
        self._path = path
        self._aliases = self._load()
        self._deferred = False

    def _load(self):
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            logger.exception("读取备注文件失败: %s", self._path)
        return {}

    def _save(self):
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._aliases, f, ensure_ascii=False, indent=2)
        except OSError:
            logger.exception("保存备注文件失败: %s", self._path)

    def get(self, device):
        """取备注名，无则返回空串。"""
        return self._aliases.get(device, "")

    @contextmanager
    def batch(self):
        """批量操作上下文：延迟写盘，退出时一次性保存。"""
        self._deferred = True
        try:
            yield
        finally:
            self._deferred = False
            self._save()

    def set(self, device, alias):
        """设置备注名；传空串则删除该备注。"""
        alias = alias.strip()
        if alias:
            self._aliases[device] = alias
        else:
            self._aliases.pop(device, None)
        if not self._deferred:
            self._save()
