"""串口号管理核心逻辑测试。

用内存假 winreg（FakeReg）模拟注册表树，不触碰真实注册表；
在线设备枚举通过打桩 serial.tools.list_ports.comports 控制
（com_manager 以 ``from serial.tools import list_ports`` 持有同一模块对象）。
"""

import json
import sys

import pytest

from com_manager import (
    BACKUP_PREFIX,
    COMDB_KEY,
    COMDB_VALUE,
    ENUM_KEY,
    DeviceCom,
    backup_state,
    com_number,
    comdb_to_set,
    elevated_command_line,
    execute_task,
    latest_backup,
    list_serial_devices,
    read_comdb,
    set_to_comdb,
    try_run_com_task,
)

# ---------- 内存假 winreg ----------


class FakeKey:
    """假注册表键：subkeys {name: FakeKey}，values {name: (value, type)}。"""

    def __init__(self):
        self.subkeys = {}
        self.values = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeReg:
    """最小 winreg 替身：支持 OpenKey/EnumKey/QueryInfoKey/值读写/删除。"""

    HKEY_LOCAL_MACHINE = object()
    KEY_READ = 1
    KEY_SET_VALUE = 2
    REG_SZ = 1
    REG_BINARY = 3
    KEY_WOW64_64KEY = 0x0100

    def __init__(self):
        self.root = FakeKey()

    def _key_for_root(self, root):
        assert root is self.HKEY_LOCAL_MACHINE
        return self.root

    def _walk(self, key, sub):
        cur = key
        for part in sub.split("\\"):
            if part not in cur.subkeys:
                raise FileNotFoundError(sub)
            cur = cur.subkeys[part]
        return cur

    def OpenKey(self, root, path, reserved=0, access=KEY_READ):
        # 支持两种用法：OpenKey(HKEY, 完整路径) 与 OpenKey(已打开键, 子键名)
        if isinstance(root, FakeKey):
            return self._walk(root, path)
        return self._walk(self._key_for_root(root), path)

    def CreateKey(self, root, path):
        cur = self._key_for_root(root)
        for part in path.split("\\"):
            cur = cur.subkeys.setdefault(part, FakeKey())
        return cur

    def QueryValueEx(self, key, name):
        if name not in key.values:
            raise FileNotFoundError(name)
        return key.values[name]

    def SetValueEx(self, key, name, reserved, vtype, value):
        key.values[name] = (value, vtype)

    def DeleteValue(self, key, name):
        if name not in key.values:
            raise FileNotFoundError(name)
        del key.values[name]

    def EnumKey(self, key, index):
        return sorted(key.subkeys.keys())[index]

    def QueryInfoKey(self, key):
        return (len(key.subkeys), len(key.values), 0)


def make_reg(devices, comdb_bits=None):
    """构造假注册表。

    devices: [(instance_path, port_name, friendly_name)]，
             instance_path 如 'USB\\VID_1A86&PID_7523\\DEV1'
    comdb_bits: 已占用口号集合（纯数字）
    """
    reg = FakeReg()
    enum = reg.CreateKey(reg.HKEY_LOCAL_MACHINE, ENUM_KEY)
    for path, port, friendly in devices:
        parts = path.split("\\")
        cur = enum
        for p in parts:
            cur = cur.subkeys.setdefault(p, FakeKey())
        # FriendlyName 在实例键；PortName 在实例键下的 Device Parameters 子键
        cur.values["FriendlyName"] = (friendly, reg.REG_SZ)
        dp = cur.subkeys.setdefault("Device Parameters", FakeKey())
        dp.values["PortName"] = (port, reg.REG_SZ)
    ports = reg.CreateKey(reg.HKEY_LOCAL_MACHINE, COMDB_KEY)
    if comdb_bits:
        size = max(comdb_bits) // 8 + 1
        ports.values[COMDB_VALUE] = (set_to_comdb(comdb_bits, size), reg.REG_BINARY)
    return reg


class FakePort:
    def __init__(self, device):
        self.device = device


@pytest.fixture
def stub_online(monkeypatch):
    """返回设置在线口号集合的函数。"""

    def set_online(names):
        online = list(names)
        monkeypatch.setattr(
            "serial.tools.list_ports.comports",
            lambda: [FakePort(n) for n in online],
        )

    return set_online


@pytest.fixture
def stub_reg(monkeypatch):
    """把 com_manager 模块内的 winreg 替换为 FakeReg 实例并返回该实例。

    用字符串形式打桩模块属性，无需在测试里 import 模块本身；
    com_manager 的函数默认 reg=None 时读取模块全局 winreg，因此生效。
    """
    reg = FakeReg()
    monkeypatch.setattr("com_manager.winreg", reg)
    return reg


# ---------- 纯函数 ----------


def test_com_number():
    assert com_number("COM12") == 12
    assert com_number("com3") == 3
    assert com_number("LPT1") is None
    assert com_number("") is None
    assert com_number(None) is None


def test_comdb_roundtrip():
    bits = {1, 3, 8, 9, 16}
    data = set_to_comdb(bits, 4)
    assert len(data) == 4
    assert comdb_to_set(data) == bits


def test_comdb_empty():
    assert comdb_to_set(b"") == set()
    assert set_to_comdb(set(), 2) == b"\x00\x00"


def test_set_to_comdb_clamps_out_of_range():
    # 超过位图容量的口号被忽略，不越界
    data = set_to_comdb({1, 100}, 1)
    assert comdb_to_set(data) == {1}


# ---------- 设备枚举 ----------


def test_list_serial_devices_marks_present(stub_online):
    stub_online(["COM3"])
    reg = make_reg(
        [
            (r"USB\VID_1A86&PID_7523\DEV1", "COM3", "CH340 (COM3)"),
            (r"USB\VID_0403&PID_6001\DEV2", "COM12", "FT232 (COM12)"),
            (r"ACPI\PNP0501\1", "COM1", "主板串口 (COM1)"),
        ],
        comdb_bits={1, 3, 12},
    )
    devs = list_serial_devices(reg)
    by_port = {d.port_name: d for d in devs}
    assert set(by_port) == {"COM1", "COM3", "COM12"}
    assert by_port["COM3"].present is True
    assert by_port["COM12"].present is False
    assert "CH340" in by_port["COM3"].friendly_name
    assert by_port["COM3"].key == r"USB\VID_1A86&PID_7523\DEV1"
    assert isinstance(by_port["COM3"], DeviceCom)


def test_list_serial_devices_skips_non_com_portname(stub_online):
    stub_online([])
    reg = make_reg([(r"USB\VID_0000&PID_0001\DEV1", "LPT1", "并口")])
    assert list_serial_devices(reg) == []


# ---------- 清理幽灵口 ----------


def test_clear_removes_ghosts_and_rebuilds_comdb(stub_online, tmp_path):
    stub_online(["COM3"])
    reg = make_reg(
        [
            (r"USB\VID_1A86&PID_7523\DEV1", "COM3", "在线 CH340"),
            (r"USB\VID_0403&PID_6001\DEV2", "COM12", "幽灵 FT232"),
            (r"USB\VID_1A86&PID_7523\DEV3", "COM20", "幽灵 CH340 旧设备"),
        ],
        comdb_bits={3, 12, 20},
    )
    result = execute_task("clear", reg=reg, backup_dir=str(tmp_path))
    assert result["ok"] is True
    assert set(result["changed"]) == {"COM12", "COM20"}

    # 幽灵设备的 PortName 被删除，在线设备保留
    remaining = list_serial_devices(reg)
    assert {d.port_name for d in remaining} == {"COM3"}

    # ComDB 只保留在线口
    assert comdb_to_set(read_comdb(reg)) == {3}

    # 备份文件已生成
    backups = list(tmp_path.glob("com_port_backup-*.json"))
    assert len(backups) == 1
    assert BACKUP_PREFIX in backups[0].name
    data = json.loads(backups[0].read_text(encoding="utf-8"))
    assert len(data["devices"]) == 3


def test_clear_with_no_ghosts(stub_online, tmp_path):
    stub_online(["COM3"])
    reg = make_reg(
        [(r"USB\VID_1A86&PID_7523\DEV1", "COM3", "在线")],
        comdb_bits={3},
    )
    result = execute_task("clear", reg=reg, backup_dir=str(tmp_path))
    assert result["ok"] is True
    assert result["changed"] == []
    assert comdb_to_set(read_comdb(reg)) == {3}


# ---------- 固定口号 ----------


def test_assign_sets_portname_and_comdb(stub_online, tmp_path):
    stub_online(["COM20"])
    reg = make_reg(
        [(r"USB\VID_1A86&PID_7523\DEV3", "COM20", "高口号 CH340")],
        comdb_bits={20},
    )
    result = execute_task(
        "assign",
        {"device_key": r"USB\VID_1A86&PID_7523\DEV3", "port": "com5"},
        reg=reg,
        backup_dir=str(tmp_path),
    )
    assert result["ok"] is True
    assert result["changed"] == ["COM5"]
    devs = {d.key: d for d in list_serial_devices(reg)}
    assert devs[r"USB\VID_1A86&PID_7523\DEV3"].port_name == "COM5"
    assert comdb_to_set(read_comdb(reg)) == {20, 5}


def test_assign_rejects_occupied_port(stub_online, tmp_path):
    stub_online([])
    reg = make_reg(
        [
            (r"USB\VID_1A86&PID_7523\DEV1", "COM5", "占用者"),
            (r"USB\VID_0403&PID_6001\DEV2", "COM20", "要改的设备"),
        ],
        comdb_bits={5, 20},
    )
    result = execute_task(
        "assign",
        {"device_key": r"USB\VID_0403&PID_6001\DEV2", "port": "COM5"},
        reg=reg,
        backup_dir=str(tmp_path),
    )
    assert result["ok"] is False
    assert "已被占用" in result["message"]
    # 未做任何修改
    assert comdb_to_set(read_comdb(reg)) == {5, 20}


def test_assign_same_port_is_noop(stub_online, tmp_path):
    stub_online(["COM5"])
    reg = make_reg(
        [(r"USB\VID_1A86&PID_7523\DEV1", "COM5", "设备")],
        comdb_bits={5},
    )
    result = execute_task(
        "assign",
        {"device_key": r"USB\VID_1A86&PID_7523\DEV1", "port": "COM5"},
        reg=reg,
        backup_dir=str(tmp_path),
    )
    assert result["ok"] is False
    assert "已经是" in result["message"]


def test_assign_unknown_device(stub_online, tmp_path):
    stub_online([])
    reg = make_reg([], comdb_bits=set())
    result = execute_task(
        "assign",
        {"device_key": r"USB\NOPE\DEV", "port": "COM5"},
        reg=reg,
        backup_dir=str(tmp_path),
    )
    assert result["ok"] is False
    assert "不存在" in result["message"]


def test_assign_invalid_port(stub_online, tmp_path):
    stub_online([])
    reg = make_reg(
        [(r"USB\VID_1A86&PID_7523\DEV1", "COM3", "设备")],
        comdb_bits={3},
    )
    result = execute_task(
        "assign",
        {"device_key": r"USB\VID_1A86&PID_7523\DEV1", "port": "LPT1"},
        reg=reg,
        backup_dir=str(tmp_path),
    )
    assert result["ok"] is False


def test_assign_ghost_holder_suggests_clear(stub_online, tmp_path):
    stub_online([])
    reg = make_reg(
        [
            (r"USB\VID_0000&PID_0001\GHOST", "COM5", "幽灵占用者"),
            (r"USB\VID_1A86&PID_7523\DEV1", "COM20", "要改的设备"),
        ],
        comdb_bits={5, 20},
    )
    result = execute_task(
        "assign",
        {"device_key": r"USB\VID_1A86&PID_7523\DEV1", "port": "COM5"},
        reg=reg,
        backup_dir=str(tmp_path),
    )
    assert result["ok"] is False
    assert "清理幽灵串口" in result["message"]


# ---------- 备份与恢复 ----------


def test_backup_and_restore_roundtrip(stub_online, tmp_path):
    stub_online(["COM20"])
    reg = make_reg(
        [(r"USB\VID_1A86&PID_7523\DEV1", "COM20", "设备")],
        comdb_bits={20},
    )
    # 备份当前状态
    backup = backup_state(reg, backup_dir=str(tmp_path))

    # 改成 COM5
    execute_task(
        "assign",
        {"device_key": r"USB\VID_1A86&PID_7523\DEV1", "port": "COM5"},
        reg=reg,
        backup_dir=str(tmp_path),
    )
    assert comdb_to_set(read_comdb(reg)) == {20, 5}

    # 恢复
    result = execute_task(
        "restore",
        {"path": backup},
        reg=reg,
        backup_dir=str(tmp_path),
    )
    assert result["ok"] is True
    devs = list_serial_devices(reg)
    assert devs[0].port_name == "COM20"
    assert comdb_to_set(read_comdb(reg)) == {20}


def test_latest_backup_none(tmp_path):
    assert latest_backup(backup_dir=str(tmp_path)) is None


def test_latest_backup_picks_newest(tmp_path):
    (tmp_path / "com_port_backup-20260101-010101.json").write_text(
        "{}", encoding="utf-8"
    )
    newest = tmp_path / "com_port_backup-20260901-120000.json"
    newest.write_text("{}", encoding="utf-8")
    assert latest_backup(backup_dir=str(tmp_path)) == str(newest)


# ---------- 提权命令行 ----------


def test_elevated_command_frozen(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    exe = tmp_path / "串口提示助手.exe"
    monkeypatch.setattr(sys, "executable", str(exe))
    assert elevated_command_line() == f'"{exe}"'


def test_elevated_command_source_prefers_pythonw(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    py = tmp_path / "python.exe"
    (tmp_path / "pythonw.exe").write_bytes(b"")
    monkeypatch.setattr(sys, "executable", str(py))
    line = elevated_command_line()
    assert line.startswith(f'"{tmp_path / "pythonw.exe"}"')
    assert "main.py" in line


# ---------- 提权入口 ----------


def test_try_run_com_task_writes_result(tmp_path, stub_online, stub_reg):
    stub_online([])
    # 准备任务：清理一个幽灵设备（winreg 已被 stub_reg 替换为 FakeReg）
    make_reg_into(
        stub_reg,
        [(r"USB\VID_0403&PID_6001\DEV2", "COM12", "幽灵")],
        comdb_bits={12},
    )

    task = tmp_path / "task.json"
    result_file = tmp_path / "result.json"
    task.write_text(json.dumps({"action": "clear", "params": {}}), encoding="utf-8")
    # 提权进程默认备份目录为 exe 旁 com_backups，本测试仅验证任务执行与结果回传；
    # 备份目录不可写不影响清理逻辑（backup_state 失败被外层 OSError 兜住），
    # 因此把备份目录也指到 tmp_path：通过 monkeypatch 不行（execute_task 内部
    # 用默认参数），改为直接调用 execute_task 路径已在其它用例覆盖；
    # 这里 try_run_com_task 走默认路径，只断言结果文件写出。
    handled = try_run_com_task(["prog", "--com-task", str(task), str(result_file)])
    assert handled is True
    assert result_file.exists()
    result = json.loads(result_file.read_text(encoding="utf-8"))
    assert result["ok"] is True


def test_try_run_com_task_not_present():
    assert try_run_com_task(["prog"]) is False
    assert try_run_com_task(["prog", "--other"]) is False


# ---------- 对话框冒烟（offscreen Qt） ----------


def test_dialog_constructs(qapp, stub_online, stub_reg, monkeypatch):
    """对话框能用假注册表正常构建并填充表格。"""
    stub_online(["COM3"])
    make_reg_into(
        stub_reg,
        [
            (r"USB\VID_1A86&PID_7523\DEV1", "COM3", "在线 CH340"),
            (r"USB\VID_0403&PID_6001\DEV2", "COM12", "幽灵 FT232"),
        ],
        comdb_bits={3, 12},
    )
    monkeypatch.setattr("com_manager.latest_backup", lambda backup_dir=None: None)

    from com_manager_dialog import ComManagerDialog

    dlg = ComManagerDialog()
    assert dlg._table.rowCount() == 2
    # 在线设备排在第一行
    assert dlg._table.item(0, 1).text() == "COM3"
    assert "COM1" in dlg._port_combo.itemText(0)
    # 未选中时固定按钮禁用
    assert dlg._assign_btn.isEnabled() is False
    dlg._table.selectRow(1)
    assert dlg._assign_btn.isEnabled() is True
    assert dlg._selected_device().port_name == "COM12"


def test_dialog_selected_port_parsing(qapp, stub_online, stub_reg, monkeypatch):
    stub_online([])
    make_reg_into(stub_reg, [], comdb_bits=set())
    monkeypatch.setattr("com_manager.latest_backup", lambda backup_dir=None: None)

    from com_manager_dialog import ComManagerDialog

    dlg = ComManagerDialog()
    dlg._port_combo.setCurrentText("COM7（已占用）")
    assert dlg._selected_port() == "COM7"


# ---------- 辅助：直接填充一个已存在的 FakeReg（stub_reg 夹具用） ----------


def make_reg_into(reg, devices, comdb_bits=None):
    """与 make_reg 相同的填充逻辑，但写入给定 FakeReg 实例。"""
    enum = reg.CreateKey(reg.HKEY_LOCAL_MACHINE, ENUM_KEY)
    for path, port, friendly in devices:
        cur = enum
        for p in path.split("\\"):
            cur = cur.subkeys.setdefault(p, FakeKey())
        cur.values["FriendlyName"] = (friendly, reg.REG_SZ)
        dp = cur.subkeys.setdefault("Device Parameters", FakeKey())
        dp.values["PortName"] = (port, reg.REG_SZ)
    ports = reg.CreateKey(reg.HKEY_LOCAL_MACHINE, COMDB_KEY)
    if comdb_bits:
        size = max(comdb_bits) // 8 + 1
        ports.values[COMDB_VALUE] = (set_to_comdb(comdb_bits, size), reg.REG_BINARY)
