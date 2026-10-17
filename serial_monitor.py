# -*- coding: utf-8 -*-
"""串口插拔监测模块。

通过 pyserial 枚举串口做快照比对，检测机制双保险：
1. 主：_DeviceChangeFilter（QAbstractNativeEventFilter）捕获 WM_DEVICECHANGE
   后调用 schedule_refresh()，由 QApplication.installNativeEventFilter 注册；
2. 兜底：内部 QTimer 每 1 秒轮询一次。

快照内容含 VID/PID/制造商等完整信息（details），供界面 tooltip 展示。
"""

import ctypes
import ctypes.wintypes as wt
import logging
from dataclasses import dataclass

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, QTimer, Signal
from serial.tools import list_ports

# 兜底轮询间隔（毫秒）。
# 正常检测由 WM_DEVICECHANGE 事件驱动（即时），轮询只是事件丢失时的兜底，
# 因此间隔可以放长；且轮询先用廉价预检（QueryDosDevice）判断 COM 口集合，
# 集合不变时跳过昂贵的全量枚举，空闲开销接近 0。
POLL_INTERVAL_MS = 3000
# 收到设备变更广播后延迟刷新，等待驱动完成枚举（毫秒）
DEVICE_CHANGE_DELAY_MS = 200

WM_DEVICECHANGE = 0x0219

logger = logging.getLogger(__name__)


def _cheap_port_names():
    """廉价枚举当前 COM 口名集合（frozenset，如 {'COM3', 'COM5'}）。

    用 QueryDosDeviceW 读取 DOS 设备名表，只取 COM 前缀项。
    比 pyserial 的 SetupAPI 全量枚举（读注册表/设备树/友好名）快约 30 倍，
    足以判断“有无串口增减”。无法读取（非 Windows / 调用失败）时返回 None，
    调用方应回退到全量枚举。
    """
    try:
        kernel32 = ctypes.windll.kernel32
        query_dos = kernel32.QueryDosDeviceW
        query_dos.argtypes = [wt.LPCWSTR, wt.LPWSTR, wt.DWORD]
        query_dos.restype = wt.DWORD
        # 设备名表可能较大，缓冲区不足时 GetLastError=122(ERROR_INSUFFICIENT_BUFFER)
        buf = ctypes.create_unicode_buffer(131072)
        n = query_dos(None, buf, 131072)
        if n == 0:
            return None
        return frozenset(name for name in buf[:n].split(chr(0)) if name.startswith("COM"))
    except Exception:  # noqa: BLE001 - 预检失败不算错误，回退全量枚举即可
        return None


@dataclass
class PortInfo:
    """单个串口的完整信息。"""

    device: str
    description: str = ""
    vid: int | None = None
    pid: int | None = None
    manufacturer: str = ""
    serial_number: str = ""
    hwid: str = ""

    @property
    def vidpid(self) -> str:
        """形如 '1A86:7523'，未知时返回空串。"""
        if self.vid and self.pid:
            return f"{self.vid:04X}:{self.pid:04X}"
        return ""


def _port_info(port) -> PortInfo:
    """从 pyserial ListPortInfo 提取稳定字段（字段缺失时取默认值）。"""
    return PortInfo(
        device=port.device,
        description=port.description or "",
        vid=getattr(port, "vid", None),
        pid=getattr(port, "pid", None),
        manufacturer=getattr(port, "manufacturer", None) or "",
        serial_number=getattr(port, "serial_number", None) or "",
        hwid=getattr(port, "hwid", None) or "",
    )


class _DeviceChangeFilter(QAbstractNativeEventFilter):
    """Windows 设备插拔广播过滤器，转发给 SerialMonitor。

    与 SerialMonitor 组合而非继承：QAbstractNativeEventFilter 不是 QObject，
    多重继承在 PySide6 中存在初始化顺序风险，官方写法是独立子类。
    """

    def __init__(self, monitor):
        super().__init__()
        self._monitor = monitor

    def nativeEventFilter(self, event_type, message) -> bool:
        if event_type == b"windows_generic_MSG":
            msg = ctypes.cast(int(message), ctypes.POINTER(wt.MSG)).contents
            if msg.message == WM_DEVICECHANGE:
                self._monitor.schedule_refresh()
        return False  # 不吞事件


class SerialMonitor(QObject):
    """监测串口插拔，发出 port_added / port_removed 信号。"""

    port_added = Signal(str, str)    # (设备名, 描述)
    port_removed = Signal(str, str)  # (设备名, 描述)

    def __init__(self, parent=None):
        super().__init__(parent)
        # 当前快照 {device: PortInfo}
        self._ports = self._snapshot() or {}
        # 廉价预检签名（COM 口名集合），用于轮询时跳过未变化的全量枚举
        self._cheap_sig = _cheap_port_names()
        # 设备广播过滤器（组合），由外部 installNativeEventFilter 注册
        self.event_filter = _DeviceChangeFilter(self)

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._poll_tick)
        self._poll_timer.start()

        # 事件去抖：WM_DEVICECHANGE 可能连发，单发定时器合并为一次刷新
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(DEVICE_CHANGE_DELAY_MS)
        self._refresh_timer.timeout.connect(self.refresh)

    @staticmethod
    def _snapshot() -> dict[str, PortInfo] | None:
        """枚举全部串口为 {device: PortInfo}。

        枚举失败返回 None（调用方保留旧快照），不抛异常。
        """
        try:
            return {p.device: _port_info(p) for p in list_ports.comports()}
        except Exception:  # noqa: BLE001 - 枚举失败只记日志，绝不影响主流程
            logger.exception("枚举串口失败")
            return None

    @property
    def ports(self) -> dict[str, str]:
        """当前串口快照 {device: description}（供列表/计数使用）。"""
        return {d: i.description for d, i in self._ports.items()}

    @property
    def details(self) -> dict[str, PortInfo]:
        """当前串口完整信息 {device: PortInfo}（供 tooltip 使用）。"""
        return dict(self._ports)

    def schedule_refresh(self):
        """收到设备变更广播时调用：合并去抖后延迟刷新，等待驱动枚举完成。"""
        self._refresh_timer.start()

    def _poll_tick(self):
        """兜底轮询：先用廉价预检判断 COM 口集合，无变化则跳过全量枚举。

        预检不可用（返回 None）时直接全量枚举，保证不漏检。
        """
        sig = _cheap_port_names()
        if sig is not None and sig == self._cheap_sig:
            return
        # 集合变化（或预检不可用）：全量枚举并刷新签名
        self.refresh()

    def refresh(self):
        """做一次快照比对，逐个发出插拔信号。"""
        current = self._snapshot()
        if current is None:
            # 枚举失败：保留旧状态，不误报拔出
            return
        old = self._ports
        # 全量枚举成功后，同步廉价签名，避免下次轮询重复触发
        self._cheap_sig = frozenset(current.keys())
        if current == old:
            return
        self._ports = current
        for device in sorted(current.keys() - old.keys()):
            self.port_added.emit(device, current[device].description)
        for device in sorted(old.keys() - current.keys()):
            self.port_removed.emit(device, old[device].description)
