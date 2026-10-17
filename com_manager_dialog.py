"""串口号管理对话框：清理幽灵串口号 + 给设备固定指定串口号。

列表展示系统中所有注册过的串口设备（含已拔出的幽灵口），
读注册表不需要管理员；执行修改时通过 UAC 提权子任务完成，
操作前自动备份到 exe 旁 com_backups 目录，可一键恢复。
"""

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

import com_manager


class ComManagerDialog(QDialog):
    """串口号管理：设备列表 + 清理幽灵口 + 固定口号 + 备份恢复。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("串口号管理")
        self.setModal(True)
        self.setMinimumWidth(560)
        self._devices = []

        layout = QVBoxLayout(self)

        tip = QLabel(
            "Windows 会记住每个插过的串口设备的口号，长期使用后会残留大量\n"
            "“幽灵串口”（设备已拔出但口号仍被占用），导致新设备分到很高的口号。\n"
            "在此可清理幽灵口号，或给需要固定口号的设备指定特定 COM 口号。\n"
            "修改需管理员授权（会弹出 UAC 确认），操作前自动备份，重新插拔后生效。"
        )
        tip.setStyleSheet("color: #666;")
        layout.addWidget(tip)

        # 设备表
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["状态", "串口号", "设备"])
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeToContents
        )
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setSelectionMode(QTableWidget.SingleSelection)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.itemSelectionChanged.connect(self._update_actions)
        layout.addWidget(self._table, 1)

        # 固定口号行
        assign_row = QHBoxLayout()
        assign_row.addWidget(QLabel("固定选中设备为"))
        self._port_combo = QComboBox()
        self._port_combo.setEditable(True)
        assign_row.addWidget(self._port_combo)
        self._assign_btn = QPushButton("固定口号…")
        self._assign_btn.clicked.connect(self._on_assign)
        assign_row.addWidget(self._assign_btn)
        assign_row.addStretch(1)
        layout.addLayout(assign_row)

        # 操作按钮行
        btn_row = QHBoxLayout()
        self._refresh_btn = QPushButton("刷新列表")
        self._refresh_btn.clicked.connect(self.reload)
        btn_row.addWidget(self._refresh_btn)
        self._clear_btn = QPushButton("一键清理幽灵串口")
        self._clear_btn.setStyleSheet("font-weight: bold;")
        self._clear_btn.clicked.connect(self._on_clear)
        btn_row.addWidget(self._clear_btn)
        self._restore_btn = QPushButton("恢复上次备份")
        self._restore_btn.clicked.connect(self._on_restore)
        btn_row.addWidget(self._restore_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self._backup_label = QLabel()
        self._backup_label.setStyleSheet("color: #888;")
        self._backup_label.setWordWrap(True)
        layout.addWidget(self._backup_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.reload()

    # ---------- 数据加载 ----------

    def reload(self):
        """重新枚举设备并刷新表格与口号下拉。"""
        self._devices = com_manager.list_serial_devices()
        self._devices.sort(
            key=lambda d: (not d.present, com_manager.com_number(d.port_name) or 9999)
        )
        self._table.setRowCount(len(self._devices))
        used = set()
        for row, d in enumerate(self._devices):
            n = com_manager.com_number(d.port_name)
            if n:
                used.add(n)
            status = QTableWidgetItem("● 在线" if d.present else "○ 幽灵")
            if not d.present:
                status.setForeground(QColor("gray"))
            port_item = QTableWidgetItem(d.port_name)
            name = d.friendly_name or d.key
            dev_item = QTableWidgetItem(name)
            if not d.present:
                dev_item.setForeground(QColor("gray"))
            self._table.setItem(row, 0, status)
            self._table.setItem(row, 1, port_item)
            self._table.setItem(row, 2, dev_item)

        # 口号下拉：COM1~COM30，占用的标注出来
        self._port_combo.clear()
        for n in range(1, 31):
            tag = "（已占用）" if n in used else ""
            self._port_combo.addItem(f"COM{n}{tag}")
        self._port_combo.setCurrentIndex(0)

        backup = com_manager.latest_backup()
        if backup:
            self._backup_label.setText(f"最近备份：{backup}")
            self._restore_btn.setEnabled(True)
        else:
            self._backup_label.setText("暂无备份（执行修改操作时会自动备份）")
            self._restore_btn.setEnabled(False)
        self._update_actions()

    def _selected_device(self):
        """返回当前选中行对应的 DeviceCom，无选择返回 None。"""
        row = self._table.currentRow()
        if 0 <= row < len(self._devices):
            return self._devices[row]
        return None

    def _update_actions(self):
        self._assign_btn.setEnabled(self._selected_device() is not None)

    # ---------- 提权操作 ----------

    def _selected_port(self):
        """从下拉框解析目标口号（'COM5（已占用）' -> 'COM5'），非法返回 None。"""
        text = self._port_combo.currentText().strip()
        n = com_manager.com_number(text.split("（")[0])
        return f"COM{n}" if n else None

    def _run_elevated(self, action, params, confirm_text):
        """确认后发起提权任务，弹窗展示结果并刷新列表。"""
        box = QMessageBox(self)
        box.setWindowTitle("串口号管理")
        box.setText(confirm_text)
        box.setInformativeText("将请求管理员权限（UAC），请在弹窗中选择“是”。")
        box.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        box.setDefaultButton(QMessageBox.Cancel)
        if box.exec() != QMessageBox.Ok:
            return
        result = com_manager.run_elevated(action, params)
        self.reload()
        if result.get("ok"):
            QMessageBox.information(
                self, "串口号管理", result.get("message", "操作完成")
            )
        else:
            QMessageBox.warning(self, "串口号管理", result.get("message", "操作失败"))

    def _on_clear(self):
        ghosts = [d for d in self._devices if not d.present]
        if not ghosts:
            QMessageBox.information(
                self, "串口号管理", "当前没有幽灵串口（所有注册过的设备都在线）。"
            )
            return
        names = "、".join(
            d.port_name
            for d in sorted(
                ghosts, key=lambda d: com_manager.com_number(d.port_name) or 9999
            )
        )
        self._run_elevated(
            "clear",
            {},
            f"将清理 {len(ghosts)} 个幽灵串口（{names}），\n"
            "并把口号占用表重置为只包含当前在线设备。\n"
            "在线设备不受影响。建议操作后重启电脑。",
        )

    def _on_assign(self):
        dev = self._selected_device()
        port = self._selected_port()
        if not dev or not port:
            QMessageBox.warning(
                self, "串口号管理", "请先选择设备并输入有效的口号（如 COM5）。"
            )
            return
        if dev.port_name.upper() == port.upper():
            QMessageBox.information(self, "串口号管理", f"该设备当前已经是 {port}。")
            return
        state = "在线" if dev.present else "当前未插入（幽灵设备）"
        self._run_elevated(
            "assign",
            {"device_key": dev.key, "port": port},
            f"将设备「{dev.friendly_name or dev.key}」（{state}）\n"
            f"的串口号固定为 {port}。\n"
            f"若该口号被幽灵设备占用，建议先“一键清理幽灵串口”。\n"
            "完成后重新插拔该设备生效。",
        )

    def _on_restore(self):
        backup = com_manager.latest_backup()
        if not backup:
            QMessageBox.information(self, "串口号管理", "没有可恢复的备份。")
            return
        self._run_elevated(
            "restore",
            {"path": backup},
            f"将从最近的备份恢复串口号分配：\n{backup}",
        )
