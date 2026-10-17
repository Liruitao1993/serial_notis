# -*- coding: utf-8 -*-
"""设置对话框：外观（主题/风格/圆角）+ 通知行为。

所有控件即时生效：改动立即写入 AppConfig 并触发预览回调，
无需 OK/Cancel（与卡片透明度滑条的交互模式一致）。
"""

import perf_profile
import themes
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFontDatabase
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from card_window import FONT_SIZE_MIN, FONT_SIZE_MAX


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

        # 响应档位：同时决定兜底轮询间隔、事件复核延迟与动效帧率
        self._perf_combo = QComboBox()
        self._perf_combo.addItems(list(perf_profile.PROFILE_NAMES))
        self._perf_combo.setCurrentIndex(
            _index_of(perf_profile.PROFILE_NAMES, self._config.perf_profile)
        )
        self._perf_combo.setToolTip(
            "省电：预检 10 秒、动效静止（适合笔记本电池）\n"
            "均衡：预检 1 秒、30fps 动效（推荐）\n"
            "敏捷：预检 0.5 秒、响应最快\n"
            "自动：插电用均衡，电池用省电"
        )
        self._perf_combo.currentTextChanged.connect(self._on_perf_profile)
        form.addRow("响应档位", self._perf_combo)

        self._ball_combo = QComboBox()
        self._ball_combo.addItems(list(themes.BALL_THEMES))
        self._ball_combo.setCurrentIndex(_index_of(themes.BALL_THEMES, self._config.ball_theme))
        self._ball_combo.currentTextChanged.connect(self._on_ball_theme)
        form.addRow("悬浮球主题", self._ball_combo)

        self._mascot_combo = QComboBox()
        self._mascot_combo.addItems(themes.MASCOTS)
        self._mascot_combo.setCurrentIndex(
            _index_of(themes.MASCOTS, self._config.ball_mascot)
        )
        self._mascot_combo.currentTextChanged.connect(self._on_mascot)
        form.addRow("悬浮球形象", self._mascot_combo)

        self._ball_anim_combo = QComboBox()
        self._ball_anim_combo.addItems(themes.BALL_ANIMATIONS)
        idx = themes.BALL_ANIMATIONS.index(self._config.ball_animation) if self._config.ball_animation in themes.BALL_ANIMATIONS else 1
        self._ball_anim_combo.setCurrentIndex(idx)
        self._ball_anim_combo.currentTextChanged.connect(self._on_ball_animation)
        form.addRow("悬浮球动效", self._ball_anim_combo)

        # Logo 弹框时长
        popup_row = QHBoxLayout()
        self._popup_dur_slider = QSlider()
        self._popup_dur_slider.setOrientation(Qt.Horizontal)
        self._popup_dur_slider.setRange(500, 5000)
        self._popup_dur_slider.setSingleStep(100)
        self._popup_dur_slider.setValue(self._config.popup_duration_ms)
        self._popup_dur_slider.valueChanged.connect(self._on_popup_duration)
        self._popup_dur_label = QLabel()
        popup_row.addWidget(self._popup_dur_slider, 1)
        popup_row.addWidget(self._popup_dur_label)
        self._update_popup_dur_label(self._popup_dur_slider.value())
        form.addRow("Logo展示时长", popup_row)

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

        # 字体（可输入任意字体名，跟随系统为空）
        self._font_combo = QComboBox()
        self._font_combo.setEditable(True)
        self._font_combo.addItem("跟随系统", "")
        for fam in QFontDatabase.families():
            self._font_combo.addItem(fam, fam)
        idx = self._font_combo.findData(self._config.font_family)
        self._font_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._font_combo.currentIndexChanged.connect(self._on_font_selected)
        self._font_combo.editTextChanged.connect(self._on_font_edited)
        form.addRow("字体", self._font_combo)

        self._font_size_spin = QSpinBox()
        self._font_size_spin.setRange(FONT_SIZE_MIN, FONT_SIZE_MAX)
        self._font_size_spin.setValue(self._config.font_size)
        self._font_size_spin.valueChanged.connect(
            lambda v: (self._config.set("font_size", v), self._on_preview())
        )
        form.addRow("字号", self._font_size_spin)

        # 字体颜色：选色 + 跟随主题
        color_row = QHBoxLayout()
        self._color_btn = QPushButton()
        self._color_btn.setFixedSize(44, 22)
        self._color_btn.setToolTip("自定义字体颜色")
        self._color_btn.clicked.connect(self._on_pick_color)
        self._color_reset = QPushButton("跟随主题")
        self._color_reset.clicked.connect(self._on_reset_color)
        color_row.addWidget(self._color_btn)
        color_row.addWidget(self._color_reset)
        color_row.addStretch(1)
        self._update_color_swatch()
        form.addRow("字体颜色", color_row)

        # 卡片宽度
        self._width_spin = QSpinBox()
        self._width_spin.setRange(240, 480)
        self._width_spin.setSuffix(" px")
        self._width_spin.setValue(self._config.card_width)
        self._width_spin.valueChanged.connect(
            lambda v: (self._config.set("card_width", v), self._on_preview())
        )
        form.addRow("卡片宽度", self._width_spin)

        return page

    def _update_radius_label(self, value):
        self._radius_value.setText("直角" if value == 0 else f"{value} px")

    def _update_color_swatch(self):
        color = self._config.font_color or themes.card_theme(
            self._config.card_theme
        )["title"]
        self._color_btn.setStyleSheet(
            f"QPushButton {{ background: {color}; border: 1px solid #888; "
            f"border-radius: 3px; }}"
        )
        self._color_btn.setToolTip(
            f"当前字体颜色：{self._config.font_color or '跟随主题'}"
        )
        self._color_reset.setEnabled(bool(self._config.font_color))

    def _on_font_selected(self, index):
        """从列表选择（含「跟随系统」空值）。"""
        data = self._font_combo.itemData(index)
        if data is None:
            return
        self._config.set("font_family", data)
        self._on_preview()

    def _on_font_edited(self, text):
        """手输自定义字体名。"""
        self._config.set("font_family", text.strip())
        self._on_preview()

    def _on_pick_color(self):
        current = self._config.font_color or themes.card_theme(
            self._config.card_theme
        )["title"]
        color = QColorDialog.getColor(QColor(current), self, "选择字体颜色")
        if color.isValid():
            self._config.set("font_color", color.name())
            self._on_preview()
            self._update_color_swatch()

    def _on_reset_color(self):
        self._config.set("font_color", "")
        self._on_preview()
        self._update_color_swatch()

    def _on_perf_profile(self, name):
        """切换响应档位：写入配置并即时生效（由预览回调重设各组件节奏）。"""
        self._config.set("perf_profile", name)
        self._on_preview()

    def _on_ball_theme(self, name):
        self._config.set("ball_theme", name)
        self._on_preview()

    def _on_mascot(self, name):
        self._config.set("ball_mascot", name)
        self._on_preview()

    def _on_ball_animation(self, name):
        self._config.set("ball_animation", name)
        self._on_preview()

    def _update_popup_dur_label(self, value):
        self._popup_dur_label.setText(f"{value / 1000:.1f} 秒")

    def _on_popup_duration(self, value):
        self._config.set("popup_duration_ms", value)
        self._update_popup_dur_label(value)
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
