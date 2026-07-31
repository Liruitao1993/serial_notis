# -*- coding: utf-8 -*-
"""AliasStore 持久化测试。"""

import json

from alias_store import AliasStore


def test_set_get_roundtrip(tmp_path):
    path = tmp_path / "aliases.json"
    store = AliasStore(path=path)
    store.set("COM27", " 主节点 ")
    assert store.get("COM27") == "主节点"  # 去除首尾空格

    reloaded = AliasStore(path=path)
    assert reloaded.get("COM27") == "主节点"


def test_empty_alias_deletes(tmp_path):
    path = tmp_path / "aliases.json"
    store = AliasStore(path=path)
    store.set("COM27", "主节点")
    store.set("COM27", "")
    assert store.get("COM27") == ""
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == {}


def test_corrupt_file_loads_empty(tmp_path):
    path = tmp_path / "aliases.json"
    path.write_text("not json{{{", encoding="utf-8")
    store = AliasStore(path=path)
    assert store.get("COM1") == ""


def test_missing_file_loads_empty(tmp_path):
    store = AliasStore(path=tmp_path / "nope.json")
    assert store.get("COM1") == ""
