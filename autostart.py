# -*- coding: utf-8 -*-
r"""开机自启：HKCU\Software\Microsoft\Windows\CurrentVersion\Run 注册表项。

打包版写入 exe 路径；源码版写入 pythonw.exe + main.py，避免弹出控制台。
"""

import logging
import os
import sys
import winreg

logger = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "串口提示助手"


def build_run_value(executable=None):
    """构造 Run 注册表值。executable 可注入以便测试。"""
    if getattr(sys, "frozen", False):
        return f'"{os.path.abspath(executable or sys.executable)}"'
    exe = os.path.abspath(executable or sys.executable)
    pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(pythonw):
        exe = pythonw
    main_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
    return f'"{exe}" "{main_py}"'


class Autostart:
    """开机自启开关（当前用户）。"""

    def __init__(self, name=APP_NAME):
        self._name = name

    @property
    def enabled(self):
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ
            ) as key:
                winreg.QueryValueEx(key, self._name)
                return True
        except FileNotFoundError:
            return False
        except OSError:
            logger.exception("读取开机自启配置失败")
            return False

    def set_enabled(self, enabled):
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
            ) as key:
                if enabled:
                    winreg.SetValueEx(
                        key, self._name, 0, winreg.REG_SZ, build_run_value()
                    )
                else:
                    winreg.DeleteValue(key, self._name)
            logger.info("开机自启：%s", "开启" if enabled else "关闭")
        except OSError:
            logger.exception("写入开机自启配置失败")
