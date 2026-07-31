# -*- coding: utf-8 -*-
"""单实例锁（QLockFile）语义测试。"""

from PySide6.QtCore import QLockFile


def test_lock_exclusive(tmp_path):
    path = str(tmp_path / "app.lock")
    first = QLockFile(path)
    assert first.tryLock(0) is True

    second = QLockFile(path)
    assert second.tryLock(0) is False  # 第二实例拿不到锁

    first.unlock()
    third = QLockFile(path)
    assert third.tryLock(0) is True
