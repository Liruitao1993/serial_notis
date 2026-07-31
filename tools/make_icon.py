# -*- coding: utf-8 -*-
"""生成 assets/icon.ico（悬浮球图标，ICO 内嵌 PNG，Vista+ 支持）。

运行：python tools/make_icon.py
产物：assets/icon.ico（256x256，被 PyInstaller spec 引用）
"""

import struct
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QImage,
    QPainter,
    QRadialGradient,
)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "icon.ico"
SIZE = 256


def render_png(size=SIZE) -> bytes:
    """画蓝色渐变悬浮球 + 白色「串」字，输出 PNG 字节。

    drawText 需要 QGuiApplication（Qt6 无应用实例时文本引擎崩溃）。
    """
    QGuiApplication.instance() or QGuiApplication([])
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)

    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    grad = QRadialGradient(size / 2, size / 2, size * 0.55)
    grad.setColorAt(0.0, QColor(110, 160, 250))
    grad.setColorAt(1.0, QColor(58, 92, 220))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(grad)
    p.drawEllipse(QRectF(0, 0, size, size))

    font = QFont("Microsoft YaHei")
    font.setBold(True)
    font.setPixelSize(int(size * 0.55))
    p.setFont(font)
    p.setPen(QColor("white"))
    p.drawText(img.rect(), Qt.AlignmentFlag.AlignCenter, "串")
    p.end()

    buf = QByteArray()
    out = QBuffer(buf)
    out.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(out, "PNG")
    return bytes(buf)


def ico_bytes(png: bytes) -> bytes:
    """封装 ICO 容器：ICONDIR + ICONDIRENTRY + 内嵌 PNG。"""
    header = struct.pack("<HHH", 0, 1, 1)
    # 宽高 0 表示 256；BITMAPINFOHEADER 尺寸 22（PNG 内嵌格式）
    entry = struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(png), 22)
    return header + entry + png


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    png = render_png()
    OUT.write_bytes(ico_bytes(png))
    print(f"written: {OUT} ({len(png)} bytes png, {OUT.stat().st_size} bytes ico)")


if __name__ == "__main__":
    main()
