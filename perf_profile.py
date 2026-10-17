# -*- coding: utf-8 -*-
"""响应档位：把「兜底轮询间隔 / 事件复核延迟 / 动效帧率」打包成预设档位。

为什么要分档：全量枚举（pyserial / SetupAPI，会读设备树与注册表）实测约 12.6ms
一次，而廉价预检（QueryDosDevice 查 DOS 设备名表，不读盘）只要约 0.12ms，相差
百余倍。所以「扫描频率」本身几乎不构成 CPU 开销，真正影响体验的是两件事：

1. 事件到达后固定等多久才复核（等得越久，提示越迟钝）；
2. 每秒重绘次数（唤醒频率，影响笔记本电池下的 CPU 深度休眠）。

档位（括号内为本机 7 个串口下实测的 CPU 占用参考）：
- 省电（约 0.001%）：预检 10s、事件复核 400ms、动效冻结
- 均衡（约 0.012%）：预检 1s、事件复核 200ms、30fps 动效（默认）
- 敏捷（约 0.024%）：预检 0.5s、事件复核 100ms、30fps 动效
- 自动：插电 = 均衡，电池 = 省电
"""

import ctypes
import logging

logger = logging.getLogger(__name__)

# 档位参数表。anim_fps 低于 float_ball.STATIC_FPS_MAX 时动效相位被冻结（静态显示），
# 定时器仍以该帧率运行，用于推进事件气泡年龄与清理过期状态。
PROFILES = {
    "省电": {"poll_ms": 10000, "event_delay_ms": 400, "anim_fps": 5},
    "均衡": {"poll_ms": 1000, "event_delay_ms": 200, "anim_fps": 30},
    "敏捷": {"poll_ms": 500, "event_delay_ms": 100, "anim_fps": 30},
}
# 可选档位（含「自动」），顺序即设置对话框下拉框顺序
PROFILE_NAMES = ("自动", "省电", "均衡", "敏捷")
# 「自动」档在插电 / 电池下分别落到哪个档位
AUTO_ON_AC = "均衡"
AUTO_ON_BATTERY = "省电"
DEFAULT_PROFILE = "自动"


class _PowerStatus(ctypes.Structure):
    """Win32 SYSTEM_POWER_STATUS 结构（只用 ACLineStatus 字段）。"""

    _fields_ = [
        ("ACLineStatus", ctypes.c_ubyte),
        ("BatteryFlag", ctypes.c_ubyte),
        ("BatteryLifePercent", ctypes.c_ubyte),
        ("SystemStatusFlag", ctypes.c_ubyte),
        ("BatteryLifeTime", ctypes.c_ulong),
        ("BatteryFullLifeTime", ctypes.c_ulong),
    ]


def on_battery():
    """当前是否靠电池供电（ACLineStatus == 0 表示离线供电）。

    非 Windows、调用失败或状态未知时一律返回 False（按「插电」处理，
    宁可响应快一点，也不因为读不到电源状态而误判成省电档）。
    """
    try:
        status = _PowerStatus()
        if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
            return False
        return status.ACLineStatus == 0
    except Exception:  # noqa: BLE001 - 电源状态只用于选档，读不到就按插电
        logger.debug("读取电源状态失败，按插电处理", exc_info=True)
        return False


def resolve(name, battery=None):
    """把档位名解析为 (参数字典, 实际生效的档位名)。

    未知档位回退到默认（「自动」）；battery 仅在为 None 时才去读系统电源状态，
    便于测试注入。返回的是参数副本，调用方修改不会污染 PROFILES。
    """
    if name not in PROFILE_NAMES:
        name = DEFAULT_PROFILE
    if name == "自动":
        if battery is None:
            battery = on_battery()
        name = AUTO_ON_BATTERY if battery else AUTO_ON_AC
    return dict(PROFILES[name]), name
