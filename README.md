# 串口提示助手

[![Python](https://img.shields.io/badge/Python-3.13-3776AB)](https://www.python.org/)
[![PySide6](https://img.shields.io/badge/PySide6-6.x-41CD52)](https://doc.qt.io/qtforpython-6/)
[![pyserial](https://img.shields.io/badge/pyserial-3.x-0891B2)](https://github.com/pyserial/pyserial)
[![platform](https://img.shields.io/badge/platform-Windows-0078D4)]()

<p align="center">
  <img src="./assets/readme/hero.svg" width="100%" alt="串口提示助手：USB 串口插拔即时提示，悬浮球与亚克力卡片界面示意">
</p>

> Windows 下的 USB 串口插拔监控小工具：设备插入或拔出的瞬间，悬浮球与亚克力卡片即时给出提示，不再需要打开设备管理器反复确认。

## 功能特性

- **秒级感知**：监听 Windows 设备广播（WM_DEVICECHANGE），另配 1s 定时轮询兜底，任何情况都能捕获插拔
- **悬浮球**：常驻桌面的蓝色小球，实时显示当前串口数量；插拔时绿色/红色呼吸闪动
- **提示卡片**：半透明亚克力风格卡片，插入绿色、拔出红色通知条，20 秒自动淡出
- **串口列表 + 备注名**：为常用串口设置备注（如 `COM27 → 主节点`），一眼认出设备
- **系统托盘**：防误关，随时从托盘重新显示悬浮球或退出

## 工作方式

<p align="center">
  <img src="./assets/readme/workflow.svg" width="100%" alt="串口插拔事件流：设备广播到提示卡片更新的五步链路">
</p>

- 设备插拔由悬浮球通过 `nativeEvent` 捕获系统广播，再交给 `SerialMonitor` 延迟 200ms 刷新（等待驱动枚举完成）
- 刷新时对 pyserial 枚举结果做快照比对，差异通过 Qt 信号 `port_added / port_removed` 广播
- 信号在主入口 `main.py` 统一接线，驱动卡片列表、通知条、悬浮球计数与闪动

## 快速开始

**环境要求**：Windows 10/11，Python 3.13

```powershell
pip install -r requirements.txt
python main.py
```

打包为单文件 exe（无控制台窗口）：

```powershell
pip install pyinstaller
pyinstaller 串口提示助手.spec
# 产物：dist/串口提示助手.exe
```

## 使用说明

| 交互 | 效果 |
| --- | --- |
| 单击悬浮球 | 显示 / 隐藏提示卡片 |
| 拖动悬浮球 | 移动位置 |
| 点击卡片中的串口行 | 编辑该串口的备注名 |
| 拖动卡片底部滑条 | 调整卡片背景透明度 |
| 点击卡片「刷新」按钮 | 强制重新枚举串口（修复列表叠影） |
| 托盘图标菜单 | 显示悬浮球 / 退出程序 |

## 数据文件

串口备注名保存在程序旁的 `port_aliases.json`（打包版位于 exe 同目录），格式如下：

```json
{ "COM27": "主节点", "COM64": "从节点" }
```

> [!NOTE]
> 将某个备注编辑为空即删除该条备注；文件在修改时立即写入，下次启动自动加载。

## 项目结构

```text
main.py            入口：对象装配与全部信号接线
card_window.py     提示卡片（串口列表 / 通知条 / 透明度）
float_ball.py      悬浮球（拖动 / 闪动 / 系统事件捕获）
serial_monitor.py  串口枚举与插拔信号
alias_store.py     备注名 JSON 持久化
```

## 兼容性与限制

- 仅支持 Windows：插拔检测依赖 `WM_DEVICECHANGE` 系统广播
- 单实例运行，不提供自动更新
- 界面为模拟亚克力效果（Qt 透明背景 + QSS），兼容性优于依赖系统毛玻璃接口的实现
