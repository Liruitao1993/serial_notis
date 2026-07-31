# -*- coding: utf-8 -*-
"""Windows 亚克力毛玻璃效果封装。

通过 ctypes 调用未公开的 user32.SetWindowCompositionAttribute，
启用 ACCENT_ENABLE_ACRYLICBLURBEHIND。失败时返回 False，
调用方应降级为纯 QSS 半透明背景。
"""

import ctypes
import sys

# WCA_ACCENT_POLICY
_WCA_ACCENT_POLICY = 19
# ACCENT_ENABLE_ACRYLICBLURBEHIND
_ACCENT_ACRYLIC = 4

# Win11 DWM 属性
_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWA_SYSTEMBACKDROP_TYPE = 38
_DWMWCP_ROUND = 2
_DWMSBT_TRANSIENTWINDOW = 3  # 亚克力


class _Margins(ctypes.Structure):
    _fields_ = [
        ("cxLeftWidth", ctypes.c_int),
        ("cxRightWidth", ctypes.c_int),
        ("cyTopHeight", ctypes.c_int),
        ("cyBottomHeight", ctypes.c_int),
    ]


class _AccentPolicy(ctypes.Structure):
    _fields_ = [
        ("AccentState", ctypes.c_int),
        ("AccentFlags", ctypes.c_int),
        ("GradientColor", ctypes.c_uint),
        ("AnimationId", ctypes.c_int),
    ]


class _WindowCompositionAttribData(ctypes.Structure):
    _fields_ = [
        ("Attribute", ctypes.c_int),
        ("Data", ctypes.c_void_p),
        ("SizeOfData", ctypes.c_size_t),
    ]


def apply_acrylic(hwnd, tint_argb=0xCC2B2B2B):
    """给窗口应用亚克力毛玻璃效果。

    :param hwnd: 窗口句柄（winId）
    :param tint_argb: 着色 0xAARRGGBB（API 需要 ABGR，内部转换）
    :return: 成功 True，失败 False（调用方降级处理）
    """
    if sys.platform != "win32":
        return False
    try:
        set_wca = ctypes.windll.user32.SetWindowCompositionAttribute
    except (OSError, AttributeError):
        return False
    try:
        a = (tint_argb >> 24) & 0xFF
        r = (tint_argb >> 16) & 0xFF
        g = (tint_argb >> 8) & 0xFF
        b = tint_argb & 0xFF
        gradient_abgr = (a << 24) | (b << 16) | (g << 8) | r

        accent = _AccentPolicy()
        accent.AccentState = _ACCENT_ACRYLIC
        accent.AccentFlags = 2  # 绘制到整个窗口
        accent.GradientColor = gradient_abgr
        accent.AnimationId = 0

        data = _WindowCompositionAttribData()
        data.Attribute = _WCA_ACCENT_POLICY
        data.Data = ctypes.cast(ctypes.pointer(accent), ctypes.c_void_p)
        data.SizeOfData = ctypes.sizeof(accent)

        result = set_wca(int(hwnd), ctypes.byref(data))
        return bool(result)
    except Exception:
        return False


def _apply_win11_backdrop(hwnd):
    """Win11 22H2+ 官方系统背景材料（亚克力）+ 圆角 + 深色模式。"""
    try:
        dwm = ctypes.windll.dwmapi
    except (OSError, AttributeError):
        return False
    try:
        hwnd = int(hwnd)
        margins = _Margins(-1, -1, -1, -1)
        if dwm.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins)) != 0:
            return False
        dark = ctypes.c_int(1)
        dwm.DwmSetWindowAttribute(
            hwnd, _DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(dark), 4
        )
        corner = ctypes.c_int(_DWMWCP_ROUND)
        dwm.DwmSetWindowAttribute(
            hwnd, _DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(corner), 4
        )
        backdrop = ctypes.c_int(_DWMSBT_TRANSIENTWINDOW)
        hr = dwm.DwmSetWindowAttribute(
            hwnd, _DWMWA_SYSTEMBACKDROP_TYPE, ctypes.byref(backdrop), 4
        )
        return hr == 0
    except Exception:
        return False


def apply_glass(hwnd, tint_argb=0x80202026):
    """给窗口应用毛玻璃，按优先级尝试。

    :return: "backdrop"（Win11 系统亚克力）/ "accent"（旧接口）/ ""（均失败，降级 QSS）
    """
    if _apply_win11_backdrop(hwnd):
        return "backdrop"
    if apply_acrylic(hwnd, tint_argb):
        return "accent"
    return ""
