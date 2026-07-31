# -*- coding: utf-8 -*-
"""设置对话框：外观（主题/风格/圆角）+ 通知行为。

所有控件即时生效：改动立即写入 AppConfig 并触发预览回调，
无需 OK/Cancel（与卡片透明度滑条的交互模式一致）。
"""

import themes
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


def _index_of(keys, name):
    try:
        return list(keys).index(name)
    except ValueError:
        return 0


class SettingsDialog(QDialog):
    """设置对话框：外观 + 通知，改动即时应用。"""

    def __init__(self, config, on_preview=None, parent=None):
        super().__init__(parent)
        self._config = config
        self._on_preview = on_preview or (lambda: None)
        self.setWindowTitle("设置")
        self.setModal(True)
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)
        tabs.addTab(self._build_appearance(), "外观")
        tabs.addTab(self._build_notify(), "通知")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ---------- 外观 ----------

    def _build_appearance(self):
        page = QWidget()
        form = QFormLayout(page)

        self._ball_combo = QComboBox()
        self._ball_combo.addItems(list(themes.BALL_THEMES))
        self._ball_combo.setCurrentIndex(_index_of(themes.BALL_THEMES, self._config.ball_theme))
        self._ball_combo.currentTextChanged.connect(self._on_ball_theme)
        form.addRow("悬浮球主题", self._ball_combo)

        self._card_combo = QComboBox()
        self._card_combo.addItems(list(themes.CARD_THEMES))
        self._card_combo.setCurrentIndex(_index_of(themes.CARD_THEMES, self._config.card_theme))
        self._card_combo.currentTextChanged.connect(self._on_card_theme)
        form.addRow("卡片主题", self._card_combo)

        self._style_combo = QComboBox()
        self._style_combo.addItems(list(themes.CARD_STYLES))
        self._style_combo.setCurrentIndex(_index_of(themes.CARD_STYLES, self._config.card_style))
        self._style_combo.currentTextChanged.connect(self._on_card_style)
        form.addRow("卡片风格", self._style_combo)

        radius_row = QHBoxLayout()
        self._radius_slider = QSlider()
        self._radius_slider.setOrientation(Qt.Horizontal)
        self._radius_slider.setRange(themes.RADIUS_MIN, themes.RADIUS_MAX)
        self._radius_slider.setValue(self._config.card_radius)
        self._radius_slider.valueChanged.connect(self._on_radius)
        self._radius_value = QLabel()
        radius_row.addWidget(self._radius_slider, 1)
        radius_row.addWidget(self._radius_value)
        self._update_radius_label(self._radius_slider.value())
        form.addRow("卡片圆角", radius_row)

        return page

    def _update_radius_label(self, value):
        self._radius_value.setText("直角" if value == 0 else f"{value} px")

    def _on_ball_theme(self, name):
        self._config.set("ball_theme", name)
        self._on_preview()

    def _on_card_theme(self, name):
        self._config.set("card_theme", name)
        self._on_preview()

    def _on_card_style(self, name):
        self._config.set("card_style", name)
        self._on_preview()

    def _on_radius(self, value):
        self._update_radius_label(value)
        self._config.set("card_radius", value)
        self._on_preview()

    # ---------- 通知 ----------

    def _build_notify(self):
        page = QWidget()
        form = QFormLayout(page)

        self._lifetime = QSpinBox()
        self._lifetime.setRange(5, 120)
        self._lifetime.setSuffix(" 秒")
        self._lifetime.setValue(max(5, self._config.notify_lifetime_ms // 1000))
        self._lifetime.valueChanged.connect(
            lambda v: self._config.set("notify_lifetime_ms", v * 1000)
        )
        form.addRow("通知停留时间", self._lifetime)

        self._auto_show = QCheckBox("串口事件时自动弹出卡片")
        self._auto_show.setChecked(self._config.auto_show_card)
        self._auto_show.toggled.connect(
            lambda v: self._config.set("auto_show_card", v)
        )
        form.addRow("", self._auto_show)

        self._notify_remove = QCheckBox("拔出串口时也显示通知")
        self._notify_remove.setChecked(self._config.notify_on_remove)
        self._notify_remove.toggled.connect(
            lambda v: self._config.set("notify_on_remove", v)
        )
        form.addRow("", self._notify_remove)

        return page
