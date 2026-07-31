# -*- coding: utf-8 -*-
"""应用数据目录定位：打包版取 exe 目录，源码版取脚本目录。"""

import os
import sys


def data_dir():
    """数据文件存放目录：打包成 exe 后取 exe 所在目录，否则取脚本目录。

    PyInstaller 单文件模式下 __file__ 指向临时解压目录，重启即丢，
    必须用 sys.executable 定位。
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def data_file(name):
    """返回数据目录下的文件路径。"""
    return os.path.join(data_dir(), name)
