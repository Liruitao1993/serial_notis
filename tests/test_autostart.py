# -*- coding: utf-8 -*-
"""开机自启注册表值构造测试（纯函数，不触碰真实注册表）。"""

import os
import sys

from autostart import build_run_value


def test_build_run_value_frozen(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    exe = tmp_path / "串口提示助手.exe"
    value = build_run_value(executable=str(exe))
    assert value == f'"{exe}"'


def test_build_run_value_source_prefers_pythonw(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    py = tmp_path / "python.exe"
    (tmp_path / "pythonw.exe").write_bytes(b"")
    value = build_run_value(executable=str(py))
    assert value.startswith(f'"{tmp_path / "pythonw.exe"}"')
    assert value.endswith("main.py\"")
    assert os.path.exists(value.split('"')[1])


def test_build_run_value_source_falls_back_to_python(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    py = tmp_path / "python.exe"
    value = build_run_value(executable=str(py))
    assert value.startswith(f'"{py}"')
    assert "main.py" in value
