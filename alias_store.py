# -*- coding: utf-8 -*-
"""串口备注名持久化存储。

以 JSON 文件保存 {COM口: 备注名}，程序目录下 port_aliases.json，
修改备注立即写盘，下次启动自动加载。
"""

import json
import os
import sys


def _app_dir():
    """数据文件存放目录：打包成 exe 后取 exe 所在目录，否则取脚本目录。

    PyInstaller 单文件模式下 __file__ 指向临时解压目录，重启即丢，
    必须用 sys.executable 定位。
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


_ALIAS_FILE = os.path.join(_app_dir(), "port_aliases.json")


class AliasStore:
    """串口备注名存储：get / set，set 时立即持久化。"""

    def __init__(self, path=_ALIAS_FILE):
        self._path = path
        self._aliases = self._load()

    def _load(self):
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
        except (OSError, ValueError):
            pass
        return {}

    def _save(self):
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._aliases, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def get(self, device):
        """取备注名，无则返回空串。"""
        return self._aliases.get(device, "")

    def set(self, device, alias):
        """设置备注名；传空串则删除该备注。"""
        alias = alias.strip()
        if alias:
            self._aliases[device] = alias
        else:
            self._aliases.pop(device, None)
        self._save()
