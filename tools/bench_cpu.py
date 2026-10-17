# -*- coding: utf-8 -*-
"""CPU 基准：量化轮询枚举与悬浮球动效重绘的开销（offscreen，纯 CPU 侧）。"""
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ctypes
import tempfile
from serial.tools import list_ports

# 把数据目录指到临时目录，避免污染仓库里的 config.json
import app_paths
_tmp = tempfile.mkdtemp(prefix="serialbench_")
app_paths.data_dir = lambda: _tmp
app_paths.data_file = lambda name: os.path.join(_tmp, name)

# ---- A. comports() 枚举开销 ----
t0 = time.perf_counter()
N = 20
for _ in range(N):
    ports = list_ports.comports()
dt = time.perf_counter() - t0
print(f"[A] list_ports.comports() 平均耗时: {dt / N * 1000:.1f} ms/次 (共 {len(ports)} 个口)")
print(f"    1s 轮询 => 每秒约 {dt / N * 1000:.1f} ms CPU, 占单核 {dt / N * 100:.2f}%")
print(f"    3s 轮询 => 占单核 {dt / N / 3 * 100:.2f}%")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

app = QApplication(sys.argv)

from app_config import AppConfig
from alias_store import AliasStore
from card_window import CardWindow
from float_ball import FloatBall, ANIM_FPS

config = AppConfig()
aliases = AliasStore()
card = CardWindow(aliases, config)

paint_count = 0
orig_paint = FloatBall.paintEvent
def counting_paint(self, event):
    global paint_count
    paint_count += 1
    orig_paint(self, event)
FloatBall.paintEvent = counting_paint

ball = FloatBall(card, config)

# 进程 CPU 时间（Windows：GetProcessTimes 更准）
class FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", ctypes.c_uint32), ("dwHighDateTime", ctypes.c_uint32)]

def proc_cpu_s():
    # os.times() 在 Windows 上返回 (user, system, ...)，均为当前进程 CPU 秒
    t = os.times()
    return t.user + t.system

def measure(label, seconds=6.0):
    global paint_count
    ball.show()          # 上一轮 app.quit() 会触发 hideEvent 停动画，重新 show
    ball.raise_()
    paint_count = 0
    t0 = time.perf_counter()
    c0 = proc_cpu_s()
    QTimer.singleShot(int(seconds * 1000), app.quit)
    app.exec()
    wall = time.perf_counter() - t0
    cpu = proc_cpu_s() - c0
    print(f"[{label}] {wall:.1f}s 墙钟, CPU {cpu:.2f}s => 单核占用 {cpu / wall * 100:.1f}%, "
          f"paintEvent {paint_count} 次 ({paint_count / wall:.0f}/s)")
    return cpu / wall

ball.show()

# B1: 默认（呼吸动效 60fps）
config.set("ball_animation", "呼吸")
ball.apply_mascot(None)
ball.apply_animation()
measure("B1 经典球+呼吸动效 60fps")

# B2: 动效关
config.set("ball_animation", "关")
ball.apply_mascot(None)
ball.apply_animation()
measure("B2 经典球+动效关")

# B3: 卡通形象模式（152x152 画布，60fps）
config.set("ball_animation", "关")  # 卡通形象无视动效开关，始终动画
ball.apply_mascot("小奶龙")
ball.apply_animation()
measure("B3 卡通形象(小奶龙) 60fps")

# C: 30fps / 15fps 下的开销
ball.apply_mascot(None)
config.set("ball_animation", "呼吸")
ball.apply_animation()
ball._anim_timer.setInterval(1000 // 30)
measure("B4 经典球+呼吸 30fps")

ball._anim_timer.setInterval(1000 // 15)
measure("B5 经典球+呼吸 15fps(仅改间隔,参考)")

# D: 真实空闲场景 —— SerialMonitor 3s 廉价预检轮询 + 30fps 呼吸动效，一起跑
from serial_monitor import SerialMonitor
monitor = SerialMonitor()
app.installNativeEventFilter(monitor.event_filter)

ball.apply_mascot(None)
config.set("ball_animation", "呼吸")
ball.apply_animation()

enum_calls = {"n": 0}
orig_snap = SerialMonitor._snapshot
def counting_snap():
    enum_calls["n"] += 1
    return orig_snap()
SerialMonitor._snapshot = staticmethod(counting_snap)

paint_count = 0
wall0 = time.perf_counter()
c0 = proc_cpu_s()
ball.show()
QTimer.singleShot(10000, app.quit)
app.exec()
wall = time.perf_counter() - wall0
cpu = proc_cpu_s() - c0
print(f"[D 真实空闲 10s] CPU {cpu:.2f}s => 单核占用 {cpu / wall * 100:.2f}%  "
      f"(全量枚举 {enum_calls['n']} 次, 重绘 ~{paint_count} 次)")
