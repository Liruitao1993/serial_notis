# -*- coding: utf-8 -*-
"""设置对话框：通知行为配置，写回 AppConfig 并立即持久化。"""

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QSpinBox,
    QVBoxLayout,
)


class SettingsDialog(QDialog):
    """通知停留时长 / 自动弹卡 / 拔出提示开关。"""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config
        self.setWindowTitle("设置")
        self.setModal(True)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._lifetime = QSpinBox()
        self._lifetime.setRange(5, 120)
        self._lifetime.setSuffix(" 秒")
        self._lifetime.setValue(max(5, config.notify_lifetime_ms // 1000))
        form.addRow("通知停留时间", self._lifetime)

        self._auto_show = QCheckBox("串口事件时自动弹出卡片")
        self._auto_show.setChecked(config.auto_show_card)
        form.addRow("", self._auto_show)

        self._notify_remove = QCheckBox("拔出串口时也显示通知")
        self._notify_remove.setChecked(config.notify_on_remove)
        form.addRow("", self._notify_remove)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self):
        cfg = self._config
        cfg.set("notify_lifetime_ms", self._lifetime.value() * 1000)
        cfg.set("auto_show_card", self._auto_show.isChecked())
        cfg.set("notify_on_remove", self._notify_remove.isChecked())
        self.accept()
