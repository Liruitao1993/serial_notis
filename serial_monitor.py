# -*- coding: utf-8 -*-
"""串口插拔监测模块。

通过 pyserial 枚举串口做快照比对，检测机制双保险：
1. 主：外部（悬浮球窗口）捕获 WM_DEVICECHANGE 后调用 schedule_refresh()；
2. 兜底：内部 QTimer 每 1 秒轮询一次。
"""

from PySide6.QtCore import QObject, QTimer, Signal
from serial.tools import list_ports

# 兜底轮询间隔（毫秒）
POLL_INTERVAL_MS = 1000
# 收到设备变更广播后延迟刷新，等待驱动完成枚举（毫秒）
DEVICE_CHANGE_DELAY_MS = 200


class SerialMonitor(QObject):
    """监测串口插拔，发出 port_added / port_removed 信号。"""

    port_added = Signal(str, str)    # (设备名, 描述)
    port_removed = Signal(str, str)  # (设备名, 描述)

    def __init__(self, parent=None):
        super().__init__(parent)
        # 当前快照 {device: description}
        self._ports = self._snapshot()

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self.refresh)
        self._poll_timer.start()

    @staticmethod
    def _snapshot():
        return {p.device: (p.description or "") for p in list_ports.comports()}

    @property
    def ports(self):
        """当前串口快照 {device: description}。"""
        return dict(self._ports)

    def schedule_refresh(self):
        """WM_DEVICECHANGE 到达时调用，延迟刷新等驱动枚举完成。"""
        QTimer.singleShot(DEVICE_CHANGE_DELAY_MS, self.refresh)

    def refresh(self):
        """做一次快照比对，逐个发出插拔信号。"""
        current = self._snapshot()
        old = self._ports
        if current == old:
            return
        self._ports = current
        for device in sorted(current.keys() - old.keys()):
            self.port_added.emit(device, current[device])
        for device in sorted(old.keys() - current.keys()):
            self.port_removed.emit(device, old[device])
