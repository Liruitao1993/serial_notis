"""串口号管理：清理已失效的“幽灵”串口号 + 给设备固定指定串口号。

背景：Windows 为每个 USB 串口设备按硬件序列号分配过 COM 口号并永久记忆，
长期插拔不同设备后，系统里会残留大量不再在线的 COM 口（幽灵口），
新设备可能被分到 COM20、COM30 等高编号。这些信息保存在注册表：

1. ``HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Ports``
   下的 ``ComDB``（REG_BINARY 位图）：已占用 COM 口号的总表，
   bit n 为 1 表示 COM(n+1) 被占用（含幽灵口）；
2. ``HKLM\\SYSTEM\\CurrentControlSet\\Enum\\...`` 各设备实例键下
   ``Device Parameters\\PortName``（REG_SZ）：该设备被分配的 COM 口。
   设备拔出后键仍保留，成为幽灵口。

写 HKLM 需要管理员权限，因此实际清理/指定操作通过 ShellExecuteEx "runas"
重启本程序为提权进程、以隐藏命令行子任务方式执行，结果经 JSON 文件回传。
改动在设备重新枚举（重新插拔/重启）后生效。
"""

import ctypes
import datetime
import json
import logging
import os
import re
import sys
import tempfile
import time
import winreg
from dataclasses import asdict, dataclass

from serial.tools import list_ports

from app_paths import data_file

logger = logging.getLogger(__name__)

# ComDB 位图所在键与值名
COMDB_KEY = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Ports"
COMDB_VALUE = "ComDB"
# 设备枚举根键
ENUM_KEY = r"SYSTEM\CurrentControlSet\Enum"
# 备份文件名前缀
BACKUP_PREFIX = "com_port_backup"

_COM_RE = re.compile(r"^COM(\d+)$", re.IGNORECASE)


@dataclass
class DeviceCom:
    """一个注册过的串口设备实例信息。"""

    key: str  # 相对 Enum 根键的实例路径，如 USB\VID_1A86&PID_7523\5&1234
    friendly_name: str  # 友好名（如 "USB-SERIAL CH340 (COM12)"）
    port_name: str  # PortName，如 "COM12"（理论上始终存在）
    present: bool  # 当前是否在线（PortName 出现在本次枚举结果中）


# ---------- 纯函数（不碰系统，便于单测） ----------


def com_number(port_name):
    """'COM12' -> 12；非 COM 口返回 None。"""
    m = _COM_RE.match(port_name or "")
    return int(m.group(1)) if m else None


def comdb_to_set(data):
    """ComDB 位图字节 -> 已占用口号集合（{3, 5, ...}，纯数字）。"""
    result = set()
    for byte_index, byte in enumerate(data or b""):
        for bit in range(8):
            if byte & (1 << bit):
                result.add(byte_index * 8 + bit + 1)
    return result


def set_to_comdb(numbers, size):
    """口号集合 -> ComDB 位图字节，长度固定为 size（保留原仲裁范围）。"""
    buf = bytearray(size)
    for n in numbers:
        idx = n - 1
        if 0 <= idx < size * 8:
            buf[idx // 8] |= 1 << (idx % 8)
    return bytes(buf)


def active_port_names():
    """当前在线的 COM 口名集合（frozenset），枚举失败返回 frozenset()。"""
    try:
        return frozenset(p.device for p in list_ports.comports())
    except Exception:  # noqa: BLE001 - 枚举失败按“无在线口”处理
        logger.exception("枚举在线串口失败")
        return frozenset()


# ---------- 注册表读取（reg 可注入假 winreg 以便测试） ----------


def _access(reg, write=False):
    """注册表访问权限：强制 64 位注册表视图（避免 32 位 Python 被 WOW64 重定向）。"""
    base = reg.KEY_SET_VALUE if write else reg.KEY_READ
    return base | getattr(reg, "KEY_WOW64_64KEY", 0)


def read_comdb(reg=None):
    """读取 ComDB 原始字节；不存在/失败返回 b''。reg 可注入以便测试。"""
    if reg is None:
        reg = winreg
    try:
        with reg.OpenKey(reg.HKEY_LOCAL_MACHINE, COMDB_KEY, 0, _access(reg)) as k:
            data, _ = reg.QueryValueEx(k, COMDB_VALUE)
            return data
    except FileNotFoundError:
        return b""
    except OSError:
        logger.exception("读取 ComDB 失败")
        return b""


def write_comdb(data, reg=None):
    """写入 ComDB 位图（REG_BINARY）。需要管理员权限。"""
    if reg is None:
        reg = winreg
    with reg.OpenKey(
        reg.HKEY_LOCAL_MACHINE, COMDB_KEY, 0, _access(reg, write=True)
    ) as k:
        reg.SetValueEx(k, COMDB_VALUE, 0, reg.REG_BINARY, bytes(data))


def list_serial_devices(reg=None):
    """枚举所有注册过的串口设备（含幽灵口）。

    深度遍历 Enum 根键三层（总线\\设备\\实例），读取实例键下的
    PortName，命中 COM 口即收录。present 由当前在线枚举判定。
    reg 可注入假 winreg 以便测试。
    """
    if reg is None:
        reg = winreg
    devices = []
    online = active_port_names()
    try:
        with reg.OpenKey(reg.HKEY_LOCAL_MACHINE, ENUM_KEY, 0, _access(reg)) as root:
            bus_count = reg.QueryInfoKey(root)[0]
            for i in range(bus_count):
                bus_name = reg.EnumKey(root, i)
                try:
                    with reg.OpenKey(root, bus_name, 0, _access(reg)) as bus:
                        dev_count = reg.QueryInfoKey(bus)[0]
                        for j in range(dev_count):
                            dev_name = reg.EnumKey(bus, j)
                            try:
                                with reg.OpenKey(bus, dev_name, 0, _access(reg)) as dev:
                                    inst_count = reg.QueryInfoKey(dev)[0]
                                    for k2 in range(inst_count):
                                        inst_name = reg.EnumKey(dev, k2)
                                        _collect_instance(
                                            reg,
                                            dev,
                                            inst_name,
                                            f"{bus_name}\\{dev_name}\\{inst_name}",
                                            online,
                                            devices,
                                        )
                            except OSError:
                                continue
                except OSError:
                    continue
    except OSError:
        logger.exception("枚举设备注册表失败")
    return devices


# PortName 所在的子键名（相对于设备实例键）
DEVICE_PARAMS_SUBKEY = "Device Parameters"


def _open_device_params(reg, instance_key_path, write=False):
    """打开设备实例键下的 Device Parameters 子键（不存在抛 FileNotFoundError）。

    instance_key_path 为相对 ENUM_KEY 的完整实例路径；
    write=True 时以写权限打开（需管理员）。
    """
    return reg.OpenKey(
        reg.HKEY_LOCAL_MACHINE,
        f"{ENUM_KEY}\\{instance_key_path}\\{DEVICE_PARAMS_SUBKEY}",
        0,
        _access(reg, write=write),
    )


def _collect_instance(reg, dev_key, inst_name, full_key, online, devices):
    """读取单个设备实例键，若 Device Parameters 下含 COM 口 PortName 则收录。"""
    try:
        with reg.OpenKey(dev_key, inst_name, 0, _access(reg)) as inst:
            friendly = ""
            try:
                friendly, _ = reg.QueryValueEx(inst, "FriendlyName")
            except OSError:
                friendly = ""
            try:
                with reg.OpenKey(inst, DEVICE_PARAMS_SUBKEY, 0, _access(reg)) as dp:
                    port_name, _ = reg.QueryValueEx(dp, "PortName")
            except (FileNotFoundError, OSError):
                return
            n = com_number(port_name)
            if n is None:
                return
            devices.append(
                DeviceCom(
                    key=full_key,
                    friendly_name=friendly or "",
                    port_name=port_name,
                    present=port_name in online,
                )
            )
    except OSError:
        return


# ---------- 备份 ----------


def backup_state(reg=None, backup_dir=None):
    """备份当前 ComDB 与所有设备 PortName 到 JSON 文件，返回文件路径。

    任何修改操作前都会自动备份；备份文件在数据目录（exe 旁），
    文件名 com_port_backup-YYYYmmdd-HHMMSS.json。
    reg 可注入假 winreg 以便测试。
    """
    if reg is None:
        reg = winreg
    backup_dir = backup_dir or _default_backup_dir()
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(backup_dir, f"{BACKUP_PREFIX}-{stamp}.json")
    payload = {
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "comdb_hex": read_comdb(reg).hex(),
        "devices": [asdict(d) for d in list_serial_devices(reg)],
    }
    os.makedirs(backup_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    logger.info("串口号状态已备份到 %s", path)
    return path


def _default_backup_dir():
    """备份目录：exe/脚本旁的 com_backups 子目录。"""
    return os.path.join(os.path.dirname(data_file("x")), "com_backups")


def latest_backup(backup_dir=None):
    """返回最新备份文件路径，没有则返回 None。"""
    backup_dir = backup_dir or _default_backup_dir()
    try:
        names = [
            n
            for n in os.listdir(backup_dir)
            if n.startswith(BACKUP_PREFIX) and n.endswith(".json")
        ]
    except OSError:
        return None
    if not names:
        return None
    return os.path.join(backup_dir, sorted(names)[-1])


# ---------- 提权任务（实际写注册表，需管理员） ----------


def execute_task(action, params=None, reg=None, backup_dir=None):
    """执行一个串口号管理任务。仅应在提权进程中调用。reg 可注入以便测试。"""
    if reg is None:
        reg = winreg
    """执行一个串口号管理任务。仅应在提权进程中调用。

    action:
      - "clear"  ：清理幽灵口（删除离线设备 PortName，重建 ComDB 只保留在线口）
      - "assign" ：params={"device_key":..., "port":"COMn"}，给设备固定口号
      - "restore"：params={"path":备份文件}，从备份恢复
    返回 dict：{ok: bool, message: str, backup: 备份路径或None, changed: [..]}
    """
    params = params or {}
    try:
        if action == "clear":
            return _task_clear(reg, backup_dir)
        if action == "assign":
            return _task_assign(reg, params, backup_dir)
        if action == "restore":
            return _task_restore(reg, params, backup_dir)
        return {
            "ok": False,
            "message": f"未知操作：{action}",
            "backup": None,
            "changed": [],
        }
    except PermissionError as e:
        return {
            "ok": False,
            "message": f"权限不足，请以管理员身份运行：{e}",
            "backup": None,
            "changed": [],
        }
    except OSError as e:
        logger.exception("串口号管理任务失败：%s", action)
        return {
            "ok": False,
            "message": f"注册表操作失败：{e}",
            "backup": None,
            "changed": [],
        }


def _task_clear(reg, backup_dir):
    """清理幽灵口：删除离线设备的 PortName，ComDB 只保留在线口号位。"""
    devices = list_serial_devices(reg)
    online = active_port_names()
    old_comdb = read_comdb(reg)
    backup = backup_state(reg, backup_dir)

    removed = []
    for d in devices:
        if d.present:
            continue
        try:
            with _open_device_params(reg, d.key, write=True) as k:
                reg.DeleteValue(k, "PortName")
            removed.append(d.port_name)
            logger.info("已清理幽灵口 %s（%s）", d.port_name, d.friendly_name or d.key)
        except FileNotFoundError:
            continue
        except OSError as e:
            logger.warning("清理 %s 失败：%s", d.port_name, e)

    # ComDB 重建：只保留在线口号，位图长度不变（保留仲裁范围）
    keep = {com_number(n) for n in online}
    keep.discard(None)
    size = max(len(old_comdb), 1)
    write_comdb(set_to_comdb(keep, size), reg)

    msg = (
        f"已清理 {len(removed)} 个幽灵串口"
        f"（{', '.join(sorted(removed)) if removed else '无'}）。\n"
        "重新插拔设备或重启电脑后生效，新设备将从 COM1 起依次分配。"
    )
    return {"ok": True, "message": msg, "backup": backup, "changed": sorted(removed)}


def _task_assign(reg, params, backup_dir):
    """给指定设备固定串口号。"""
    device_key = params.get("device_key", "")
    port = (params.get("port") or "").upper()
    n = com_number(port)
    if not device_key or n is None:
        return {
            "ok": False,
            "message": "参数无效：缺少设备或口号格式错误",
            "backup": None,
            "changed": [],
        }
    if not (1 <= n <= 256):
        return {
            "ok": False,
            "message": "口号需在 COM1 ~ COM256 之间",
            "backup": None,
            "changed": [],
        }

    devices = list_serial_devices(reg)
    target = next((d for d in devices if d.key == device_key), None)
    if target is None:
        return {
            "ok": False,
            "message": "设备注册表项不存在，可能已被移除",
            "backup": None,
            "changed": [],
        }
    if target.port_name.upper() == port:
        return {
            "ok": False,
            "message": f"该设备当前已经是 {port}，无需修改",
            "backup": None,
            "changed": [],
        }

    # 占用检查：口号在 ComDB 中且持有者不是本设备 -> 拒绝
    occupied = comdb_to_set(read_comdb(reg))
    if n in occupied:
        holder = next(
            (
                d
                for d in devices
                if com_number(d.port_name) == n and d.key != device_key
            ),
            None,
        )
        if holder is not None:
            who = holder.friendly_name or holder.key
            state = "在线" if holder.present else "离线（幽灵口）"
            hint = (
                "可先执行“清理幽灵串口”释放该口号"
                if not holder.present
                else "请换一个未被占用的口号"
            )
            return {
                "ok": False,
                "message": f"{port} 已被占用：{who}（{state}）。{hint}。",
                "backup": None,
                "changed": [],
            }

    backup = backup_state(reg, backup_dir)

    # 1) 设备 Device Parameters\PortName
    with _open_device_params(reg, device_key, write=True) as k:
        reg.SetValueEx(k, "PortName", 0, reg.REG_SZ, port)

    # 2) ComDB 置位（保留其它位；位图不够长则扩容）
    bits = comdb_to_set(read_comdb(reg))
    bits.add(n)
    size = max(len(read_comdb(reg)), (n // 8) + 1)
    write_comdb(set_to_comdb(bits, size), reg)

    logger.info("已将 %s 固定为 %s", device_key, port)
    msg = (
        f"已将该设备固定为 {port}。\n"
        "重新插拔该设备（或重启电脑）后生效；此后该设备无论插哪个 USB 口都保持此口号。"
    )
    return {"ok": True, "message": msg, "backup": backup, "changed": [port]}


def _task_restore(reg, params, backup_dir):
    """从备份恢复 ComDB 与设备 PortName。"""
    path = params.get("path") or latest_backup(backup_dir)
    if not path or not os.path.exists(path):
        return {"ok": False, "message": "找不到备份文件", "backup": None, "changed": []}
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)

    restored = []
    errors = []
    for d in payload.get("devices", []):
        try:
            with _open_device_params(reg, d["key"], write=True) as k:
                reg.SetValueEx(k, "PortName", 0, reg.REG_SZ, d["port_name"])
            restored.append(d["port_name"])
        except FileNotFoundError:
            errors.append(f"{d['port_name']}（设备已不存在）")
        except OSError as e:
            errors.append(f"{d['port_name']}（{e}）")

    comdb_hex = payload.get("comdb_hex")
    if comdb_hex:
        try:
            write_comdb(bytes.fromhex(comdb_hex), reg)
        except OSError as e:
            errors.append(f"ComDB（{e}）")

    msg = f"已从备份恢复 {len(restored)} 个设备的口号。"
    if errors:
        msg += "\n未能恢复：" + "、".join(errors[:5])
    msg += "\n重新插拔设备或重启电脑后生效。"
    return {"ok": True, "message": msg, "backup": path, "changed": sorted(restored)}


# ---------- 提权执行通道 ----------


def is_admin():
    """当前进程是否具有管理员权限。"""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001
        return False


def run_elevated(action, params=None, timeout_ms=120000):
    """以管理员权限重启本程序执行串口号任务，阻塞等待并返回结果 dict。

    通过临时 JSON 文件传递任务参数与结果；UAC 被用户拒绝时返回
    ok=False、message 提示已取消。失败（无法提权/超时）也返回 dict。
    """
    task_file, result_file = _task_file_paths()
    try:
        with open(task_file, "w", encoding="utf-8") as f:
            json.dump({"action": action, "params": params or {}}, f, ensure_ascii=False)

        exe = _elevated_command()
        params_str = f'--com-task "{task_file}" "{result_file}"'
        rc = _shell_execute_runas(exe, params_str)
        if rc != 42:  # >32 表示成功；42 无特殊含义，仅判断 >32
            if rc == 1223:
                return {
                    "ok": False,
                    "message": "已取消：未授予管理员权限",
                    "backup": None,
                    "changed": [],
                }
            return {
                "ok": False,
                "message": f"无法启动管理员进程（错误码 {rc}）",
                "backup": None,
                "changed": [],
            }

        # 等待结果文件（提权进程执行期间本进程阻塞）
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            if os.path.exists(result_file):
                try:
                    with open(result_file, encoding="utf-8") as f:
                        return json.load(f)
                except (OSError, ValueError):
                    pass
            time.sleep(0.2)
        return {
            "ok": False,
            "message": "管理员进程执行超时",
            "backup": None,
            "changed": [],
        }
    finally:
        for p in (task_file, result_file):
            try:
                os.remove(p)
            except OSError:
                pass


def _task_file_paths():
    """任务/结果文件路径（临时目录，带 PID 避免多实例冲突）。"""
    tmp = tempfile.gettempdir()
    base = f"serial_assist_comtask_{os.getpid()}"
    return (
        os.path.join(tmp, base + "_task.json"),
        os.path.join(tmp, base + "_result.json"),
    )


def _elevated_command():
    """提权后要运行的程序：打包版为 exe；源码版优先 pythonw.exe（不弹控制台窗）。"""
    if getattr(sys, "frozen", False):
        return f'"{os.path.abspath(sys.executable)}"'
    exe = os.path.abspath(sys.executable)
    pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(pythonw):
        exe = pythonw
    main_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
    return f'"{exe}" "{main_py}"'


def elevated_command_line():
    """暴露给测试：返回提权命令行完整可执行部分（文件 + 参数前半）。"""
    return _elevated_command()


def _shell_execute_runas(exe_cmd, params_str):
    """ShellExecuteExW 以 runas 动词启动并等待进程结束，返回 hInstApp（>32 成功）。"""

    class SHELLEXECUTEINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_ulong),
            ("fMask", ctypes.c_ulong),
            ("hwnd", ctypes.c_void_p),
            ("lpVerb", ctypes.c_wchar_p),
            ("lpFile", ctypes.c_wchar_p),
            ("lpParameters", ctypes.c_wchar_p),
            ("lpDirectory", ctypes.c_wchar_p),
            ("nShow", ctypes.c_int),
            ("hInstApp", ctypes.c_void_p),
            ("lpIDList", ctypes.c_void_p),
            ("lpClass", ctypes.c_wchar_p),
            ("hkeyClass", ctypes.c_void_p),
            ("dwHotKey", ctypes.c_ulong),
            ("hIcon", ctypes.c_void_p),
            ("hProcess", ctypes.c_void_p),
        ]

    SEE_MASK_NOCLOSEPROCESS = 0x00000040
    SEE_MASK_NO_CONSOLE = 0x00008000
    SW_HIDE = 0
    WAIT_INFINITE = 0xFFFFFFFF

    # exe_cmd 形如 '"C:\\path\\app.exe"'，拆出文件与参数
    exe_file = exe_cmd.strip('"')
    info = SHELLEXECUTEINFO()
    info.cbSize = ctypes.sizeof(SHELLEXECUTEINFO)
    info.fMask = SEE_MASK_NOCLOSEPROCESS | SEE_MASK_NO_CONSOLE
    info.lpVerb = "runas"
    info.lpFile = exe_file
    info.lpParameters = params_str
    info.nShow = SW_HIDE
    ok = ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(info))
    if not ok:
        return ctypes.windll.kernel32.GetLastError()
    if info.hProcess:
        ctypes.windll.kernel32.WaitForSingleObject(
            ctypes.c_void_p(info.hProcess), WAIT_INFINITE
        )
        ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(info.hProcess))
    return 42


def try_run_com_task(argv):
    """提权进程入口：检测 --com-task 参数并执行任务。

    在 main() 最早期（QApplication 之前）调用。返回 True 表示
    本进程是提权任务进程、已处理并应退出；False 表示正常启动。
    """
    if "--com-task" not in argv:
        return False
    result_path = None
    try:
        i = argv.index("--com-task")
        task_path = argv[i + 1]
        result_path = argv[i + 2]
        with open(task_path, encoding="utf-8") as f:
            task = json.load(f)
        result = execute_task(task.get("action", ""), task.get("params") or {})
    except Exception as e:  # noqa: BLE001 - 提权进程内任何异常都要回传
        logging.getLogger("app").exception("提权串口号任务失败")
        result = {
            "ok": False,
            "message": f"任务执行失败：{e}",
            "backup": None,
            "changed": [],
        }
    if result_path:
        try:
            with open(result_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False)
        except OSError:
            logging.getLogger("app").exception("无法写入任务结果文件")
    return True
