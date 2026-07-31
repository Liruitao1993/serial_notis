# -*- coding: utf-8 -*-
"""打包资源验证：图标有效、spec 引用图标。"""

import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_icon_exists_and_valid():
    ico = ROOT / "assets" / "icon.ico"
    assert ico.is_file(), "assets/icon.ico 缺失（运行 python tools/make_icon.py）"
    data = ico.read_bytes()
    # ICONDIR：保留 0、类型 1（icon）、数量 1
    assert struct.unpack("<HHH", data[:6]) == (0, 1, 1)
    # 尺寸 256x256（0 表示 256）、32bpp、内嵌 PNG
    w, h, colors, reserved, planes, bpp, size, offset = struct.unpack(
        "<BBBBHHII", data[6:22]
    )
    assert (w, h) == (0, 0)
    assert bpp == 32
    assert size == len(data) - offset
    assert data[offset : offset + 8] == b"\x89PNG\r\n\x1a\n"


def test_spec_references_icon():
    spec = (ROOT / "串口提示助手.spec").read_text(encoding="utf-8")
    assert "icon='assets/icon.ico'" in spec
