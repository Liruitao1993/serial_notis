# -*- coding: utf-8 -*-
"""亚克力毛玻璃卡片窗口：当前串口列表 + 插拔通知条。"""

from datetime import datetime

from PySide6.QtCore import (
    Qt,
    QPropertyAnimation,
    QEasingCurve,
    QTimer,
    Signal,
)
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

import themes

# 通知条存活时间（毫秒）
NOTIFY_LIFETIME_MS = 20000
# 淡入 / 淡出时长（毫秒）
FADE_IN_MS = 120
FADE_OUT_MS = 400

# 插拔事件历史记录最大条数
EVENT_LOG_MAX = 10

CARD_WIDTH = 320
# 字号可调范围
FONT_SIZE_MIN = 8
FONT_SIZE_MAX = 18

# 卡片背景透明度（alpha）可调范围与默认值
ALPHA_MIN = 50
ALPHA_MAX = 235
ALPHA_DEFAULT = 160


class NotificationItem(QFrame):
    """单条插拔通知：插入浅绿、拔出红色，到点后自动淡出销毁。"""

    closed = Signal(object)  # 携带自身，供卡片收缩/自动隐藏

    # 默认配色（与深色主题一致），主题色由 colors 参数注入
    _DEFAULT_COLORS = {
        "added": ("rgba(120,220,140,90)", "rgba(120,220,140,140)", "#FFFFFF"),
        "removed": ("rgba(230,80,80,90)", "rgba(230,80,80,150)", "#FFFFFF"),
    }

    def __init__(
        self,
        device,
        desc,
        added,
        alias="",
        lifetime_ms=NOTIFY_LIFETIME_MS,
        parent=None,
        colors=None,
        font_size=12,
    ):
        super().__init__(parent)
        self.setObjectName("notifyItem")
        pal = colors or {}
        if added:
            bg, border, text_color = pal.get("notify_added", self._DEFAULT_COLORS["added"])
            title = "新增串口"
            icon = "\u2795"  # ＋
        else:
            bg, border, text_color = pal.get("notify_removed", self._DEFAULT_COLORS["removed"])
            title = "已拔出"
            icon = "\u2716"  # ✖
        self.setStyleSheet(
            f"""
            QFrame#notifyItem {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 8px;
            }}
            QLabel {{ background: transparent; border: none; color: {text_color}; }}
            """
        )
        self._font_size = font_size

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)

        icon_label = QLabel(icon)
        icon_label.setStyleSheet(f"font-size: {self._font_size + 2}px;")
        layout.addWidget(icon_label)

        # 有备注名优先显示备注，让用户一眼知道是什么设备
        text = f"{title}：{device}（{alias}）" if alias else f"{title}：{device}"
        if desc:
            # 描述里通常带 "(COMx)"，去掉避免重复
            clean = desc.replace(f"({device})", "").strip()
            if clean:
                text += f"  ({clean})"
        text_label = QLabel(text)
        text_label.setWordWrap(True)
        text_label.setStyleSheet(f"font-size: {self._font_size}px;")
        layout.addWidget(text_label, 1)

        # 淡入
        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0)
        self.setGraphicsEffect(self._effect)
        self._fade_in = QPropertyAnimation(self._effect, b"opacity", self)
        self._fade_in.setDuration(FADE_IN_MS)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.start()
        self._fade_out = None

        # 20 秒后淡出销毁（时长可配置）
        QTimer.singleShot(lifetime_ms, self._fade_out_and_close)

    def _fade_out_and_close(self):
        # 安全重置：先停止旧动画，避免竞态
        if self._fade_out is not None:
            self._fade_out.stop()
        self._fade_out = QPropertyAnimation(self._effect, b"opacity", self)
        self._fade_out.setDuration(FADE_OUT_MS)
        self._fade_out.setStartValue(self._effect.opacity())
        self._fade_out.setEndValue(0.0)
        self._fade_out.setEasingCurve(QEasingCurve.OutQuad)
        self._fade_out.finished.connect(self._close)
        self._fade_out.start()

    def _close(self):
        self.closed.emit(self)
        self.setParent(None)
        self.deleteLater()


class PortRow(QFrame):
    """串口列表行：COM 口 + 备注/描述 + 编辑备注按钮，点击选中高亮。"""

    edit_requested = Signal(str)  # 携带 device
    clicked = Signal(str)         # 点击行，携带 device

    _STYLE_NORMAL = """
        QFrame#portRow { background: transparent; border: 1px solid transparent;
                         border-radius: 6px; }
        QLabel { background: transparent; border: none; }
    """
    _STYLE_SELECTED = """
        QFrame#portRow { background: rgba(100, 170, 255, 55);
                         border: 1px solid rgba(130, 200, 255, 100);
                         border-radius: 6px; }
        QLabel { background: transparent; border: none; }
    """

    def __init__(
        self,
        device,
        desc,
        alias,
        info=None,
        parent=None,
        style_normal=None,
        style_selected=None,
        font_size=12,
    ):
        super().__init__(parent)
        self.device = device
        self._selected = False
        self.setObjectName("portRow")
        self._style_normal = style_normal or self._STYLE_NORMAL
        self._style_selected = style_selected or self._STYLE_SELECTED
        self.setStyleSheet(self._style_normal)
        self._font_size = font_size
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 2, 2)
        layout.setSpacing(6)

        dev_label = QLabel(f"\u25cf  {device}")
        dev_label.setStyleSheet(
            f"font-size: {self._font_size}px; color: rgba(255,255,255,230);"
        )
        layout.addWidget(dev_label)

        if alias:
            info_label = QLabel(alias)
            info_label.setStyleSheet(
                f"font-size: {self._font_size}px; color: rgba(130, 200, 255, 230);"
            )
        else:
            info_label = QLabel(desc)
            info_label.setStyleSheet(
                f"font-size: {max(7, self._font_size - 1)}px; color: rgba(255,255,255,130);"
            )
        info_label.setWordWrap(False)
        layout.addWidget(info_label, 1)
        # 完整信息放 tooltip（含 VID/PID 与制造商，帮助区分 CH340/FTDI/CP210x）
        lines = [f"{device}  {desc}" if desc else device]
        if alias:
            lines.append(f"备注：{alias}")
        if info is not None:
            parts = []
            if info.vidpid:
                parts.append(f"VID:PID {info.vidpid}")
            if info.manufacturer:
                parts.append(f"制造商：{info.manufacturer}")
            if parts:
                lines.append(" · ".join(parts))
        self.setToolTip("\n".join(lines))

        edit_btn = QPushButton("\u270e")  # ✎
        edit_btn.setFixedSize(20, 20)
        edit_btn.setCursor(Qt.PointingHandCursor)
        edit_btn.setToolTip("编辑备注名称")
        edit_btn.setStyleSheet(
            f"""
            QPushButton {{ background: transparent; border: none;
                          color: rgba(255,255,255,140); font-size: {self._font_size + 1}px; }}
            QPushButton:hover {{ color: white; background: rgba(255,255,255,40);
                                border-radius: 4px; }}
            """
        )
        edit_btn.clicked.connect(lambda: self.edit_requested.emit(device))
        layout.addWidget(edit_btn)

    def set_selected(self, selected):
        # 状态没变化就不重设样式，避免无谓的重绘
        if selected == self._selected:
            return
        self._selected = selected
        self.setStyleSheet(self._style_selected if selected else self._style_normal)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.device)
        super().mousePressEvent(event)


class EventLogItem(QFrame):
    """单条插拔事件记录：时间 + 图标 + 设备描述，静态展示无动画。"""

    # 复用 NotificationItem 的配色键，alpha 降低使历史条目更柔和
    _DEFAULT_COLORS = {
        "added": ("rgba(120,220,140,45)", "rgba(120,220,140,80)", "#FFFFFF"),
        "removed": ("rgba(230,80,80,45)", "rgba(230,80,80,80)", "#FFFFFF"),
    }

    def __init__(self, device, desc, added, alias, timestamp, parent=None, colors=None, font_size=12):
        super().__init__(parent)
        self.setObjectName("eventLogItem")
        pal = colors or {}
        if added:
            bg, border, text_color = pal.get("notify_added", self._DEFAULT_COLORS["added"])
            icon = "\u2795"  # ➕
        else:
            bg, border, text_color = pal.get("notify_removed", self._DEFAULT_COLORS["removed"])
            icon = "\u2716"  # ✖

        self.setStyleSheet(
            f"QFrame#eventLogItem {{ background: {bg}; border: 1px solid {border}; border-radius: 6px; }}"
            f"QLabel {{ background: transparent; border: none; color: {text_color}; }}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(6)

        time_label = QLabel(timestamp.strftime("%H:%M:%S"))
        time_label.setStyleSheet(f"font-size: {font_size - 1}px; opacity: 180;")
        layout.addWidget(time_label)

        icon_label = QLabel(icon)
        icon_label.setStyleSheet(f"font-size: {font_size}px;")
        layout.addWidget(icon_label)

        # 设备名（备注优先）+ 描述
        name = f"{device}（{alias}）" if alias else device
        clean = desc.replace(f"({device})", "").strip() if desc else ""
        text = f"{name}  {clean}" if clean else name
        text_label = QLabel(text)
        text_label.setStyleSheet(f"font-size: {font_size}px;")
        layout.addWidget(text_label, 1)


class CardWindow(QWidget):
    """无边框置顶亚克力卡片。"""

    refresh_requested = Signal()  # 点击刷新按钮，由外部重新枚举串口
    log_event_requested = Signal(str, str, bool)  # device, desc, added

    def __init__(self, alias_store, config=None, parent=None):
        super().__init__(parent)
        self._alias_store = alias_store
        self._config = config
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        # 必须在原生窗口创建前设置，否则窗口按不透明白底创建，
        # 后续局部重绘（悬停/点击）会先清成白色再叠半透明内容，表现为“变白”
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(CARD_WIDTH)
        self._card_width = CARD_WIDTH
        self._font_size = 12
        # 是否因串口事件自动弹出（通知清空后自动收回）
        self.auto_shown = False
        # 当前串口快照缓存（编辑备注后原地刷新用）
        self._last_ports = {}
        self._last_details = {}
        # 主题化行样式 / 通知条配色（apply_theme 时更新）
        self._row_normal_qss = ""
        self._row_selected_qss = ""
        self._notify_colors = {}
        # 备注编辑对话框打开期间禁止自动收回卡片
        self._editing = False
        # 卡片背景透明度（AppConfig 持久化）
        if self._config is not None:
            self._panel_alpha = int(self._config.panel_alpha)
        else:
            self._panel_alpha = ALPHA_DEFAULT
        self._panel_alpha = max(ALPHA_MIN, min(ALPHA_MAX, self._panel_alpha))
        # 当前选中的串口（点击行高亮）
        self._selected_device = None
        self._rows = []
        # 列表内容指纹：串口+描述+备注都没变化时跳过重建，避免无谓重绘白闪
        self._ports_signature = None
        # 插拔事件历史记录（会话级，重启清空）
        self._event_log = []
        self._history_visible = False
        # _shrink 合并标志：避免同一事件循环内多次排版
        self._shrink_pending = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self._panel = QFrame(self)
        self._panel.setObjectName("cardPanel")
        root.addWidget(self._panel)

        panel_layout = QVBoxLayout(self._panel)
        panel_layout.setContentsMargins(14, 12, 14, 12)
        panel_layout.setSpacing(8)

        # 标题栏
        header = QHBoxLayout()
        title = QLabel("串口助手")
        title.setObjectName("cardTitle")
        header.addWidget(title)

        # 透明度调节滑条（标题右侧）
        self._alpha_slider = QSlider(Qt.Horizontal)
        self._alpha_slider.setRange(ALPHA_MIN, ALPHA_MAX)
        self._alpha_slider.setValue(self._panel_alpha)
        self._alpha_slider.setFixedWidth(90)
        self._alpha_slider.setCursor(Qt.PointingHandCursor)
        self._alpha_slider.setToolTip("调节卡片透明度")
        self._alpha_slider.valueChanged.connect(self._on_alpha_changed)
        header.addSpacing(10)
        header.addWidget(self._alpha_slider)

        header.addStretch(1)
        self._count_label = QLabel("0 个串口")
        self._count_label.setObjectName("cardCount")
        header.addWidget(self._count_label)

        refresh_btn = QPushButton("\u27f3")  # ⟳
        refresh_btn.setFixedSize(22, 22)
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.setToolTip("刷新串口列表")
        refresh_btn.setStyleSheet(
            """
            QPushButton { background: transparent; border: none;
                          color: rgba(255,255,255,170); font-size: 15px; }
            QPushButton:hover { color: white; background: rgba(255,255,255,40);
                                border-radius: 4px; }
            """
        )
        refresh_btn.clicked.connect(self.refresh_requested)
        header.addWidget(refresh_btn)

        history_btn = QPushButton("\U0001f550")  # 🕐
        history_btn.setFixedSize(22, 22)
        history_btn.setCursor(Qt.PointingHandCursor)
        history_btn.setToolTip("查看插拔事件记录")
        history_btn.setObjectName("historyBtn")
        history_btn.clicked.connect(self._on_history_clicked)
        header.addWidget(history_btn)
        self._history_btn = history_btn

        panel_layout.addLayout(header)

        # 分隔线
        line = QFrame()
        line.setObjectName("cardLine")
        line.setFixedHeight(1)
        panel_layout.addWidget(line)

        # 当前串口列表
        self._port_list_layout = QVBoxLayout()
        self._port_list_layout.setSpacing(3)
        panel_layout.addLayout(self._port_list_layout)

        self._empty_label = QLabel("暂无串口设备")
        self._empty_label.setObjectName("emptyLabel")
        self._port_list_layout.addWidget(self._empty_label)

        # 插拔事件记录面板
        self._history_panel = QWidget()
        self._history_panel.setObjectName("historyPanel")
        self._history_panel.hide()  # 默认隐藏
        self._history_layout = QVBoxLayout(self._history_panel)
        self._history_layout.setContentsMargins(0, 0, 0, 0)
        self._history_layout.setSpacing(4)
        panel_layout.addWidget(self._history_panel)

        # 通知区
        self._notify_layout = QVBoxLayout()
        self._notify_layout.setSpacing(6)
        panel_layout.addLayout(self._notify_layout)

        self.apply_theme()

    # ---------- 外观（主题） ----------

    def _theme(self):
        if self._config:
            return themes.card_theme(self._config.card_theme)
        return themes.CARD_THEMES["深色"]

    def _style(self):
        if self._config:
            return themes.card_style(self._config.card_style)
        return themes.CARD_STYLES["卡片"]

    def apply_theme(self):
        """按配置重建外观：面板 QSS、行样式、通知条配色、字体与宽度。"""
        self._apply_typography()
        self._apply_width()
        self._apply_panel_qss()
        self._apply_row_styles()
        self._apply_history_style()

        # 主题/圆角变化需重建现有行（避免旧样式残留）
        if self._last_ports:
            self.update_ports(self._last_ports, self._last_details, force=True)
        else:
            self._shrink()

        # 如果历史面板当前可见，重建条目以应用新主题
        if self._history_visible:
            self._rebuild_history()

    # ---------- 主题子方法 ----------

    def _apply_typography(self):
        """字号钳制 + 字体族设置。"""
        cfg = self._config
        try:
            fs = int(cfg.font_size) if cfg else 12
        except (TypeError, ValueError):
            fs = 12
        self._font_size = max(FONT_SIZE_MIN, min(FONT_SIZE_MAX, fs))
        family = cfg.font_family if cfg else ""
        self.setFont(QFont(family, self._font_size))

    def _apply_width(self):
        """卡片宽度钳制。"""
        cfg = self._config
        try:
            width = int(cfg.card_width) if cfg else CARD_WIDTH
        except (TypeError, ValueError):
            width = CARD_WIDTH
        self._card_width = max(240, min(480, width))
        self.setFixedWidth(self._card_width)

    def _apply_panel_qss(self):
        """面板背景 + 通用控件 QSS。"""
        t = self._theme()
        s = self._style()
        cfg = self._config
        radius = themes.resolve_radius(
            self._config.card_radius, self._config.card_style
        ) if cfg else themes.resolve_radius(12, "卡片")

        def rgba(rgb):
            return f"rgba({rgb[0]},{rgb[1]},{rgb[2]},{rgb[3]})"

        def scaled(rgb, factor):
            a = min(255, int(rgb[3] * factor))
            return f"rgba({rgb[0]},{rgb[1]},{rgb[2]},{a})"

        border = scaled(t["border"], s["border_alpha"])
        line = rgba(t["line"])
        count = rgba(t["count"])
        muted = rgba(t["muted"])

        panel_rgb = t["panel"]
        panel_a = self._panel_alpha
        if s["gradient"] == "light":
            lighter = tuple(min(255, int(c + (255 - c) * 0.18)) for c in panel_rgb)
            panel_bg = (
                f"qlineargradient(x1:0, y1:0, x2:0, y2:1, "
                f"stop:0 rgba({lighter[0]},{lighter[1]},{lighter[2]},{panel_a}), "
                f"stop:1 rgba({panel_rgb[0]},{panel_rgb[1]},{panel_rgb[2]},{panel_a}))"
            )
        else:
            panel_bg = f"rgba({panel_rgb[0]},{panel_rgb[1]},{panel_rgb[2]},{panel_a})"

        accent = rgba(t["row_selected_border"])
        fs = self._font_size
        color_override = cfg.font_color if cfg else ""
        title_color = color_override or t["title"]
        text_color = color_override or t["text"]
        count_color = color_override or rgba(t["count"])
        muted_color = color_override or rgba(t["muted"])
        common = f"""
            QLabel {{ color: {text_color}; background: transparent; border: none; }}
            QLabel#cardTitle {{ font-size: {fs + 2}px; font-weight: bold; color: {title_color}; }}
            QLabel#cardCount {{ font-size: {fs - 1}px; color: {count_color}; }}
            QLabel#emptyLabel {{ font-size: {fs}px; color: {muted_color}; }}
            QLabel.portItem {{ font-size: {fs}px; color: {text_color}; }}
            QFrame#cardLine {{ background: {line}; border: none; }}
            QFrame#eventLogItem {{ background: rgba(255,255,255,15);
                border: 1px solid rgba(255,255,255,25); border-radius: 6px; }}
            QSlider {{ background: transparent; }}
            QSlider::groove:horizontal {{
                height: 4px; background: {line}; border-radius: 2px;
            }}
            QSlider::sub-page:horizontal {{
                background: {accent}; border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                width: 10px; height: 10px; margin: -3px 0;
                background: {count_color}; border-radius: 5px;
            }}
        """
        self.setStyleSheet(
            f"QFrame#cardPanel {{ background: {panel_bg}; border-radius: {radius}px; "
            f"border: 1px solid {border}; }}"
            + common
        )

    def _apply_row_styles(self):
        """行选中/未选中样式 + 通知配色缓存。"""
        t = self._theme()
        radius = themes.resolve_radius(
            self._config.card_radius, self._config.card_style
        ) if self._config else themes.resolve_radius(12, "卡片")

        def rgba(rgb):
            return f"rgba({rgb[0]},{rgb[1]},{rgb[2]},{rgb[3]})"

        row_radius = max(4, radius - 4)
        row_selected_bg = rgba(t["row_selected_bg"])
        row_selected_border = rgba(t["row_selected_border"])
        self._row_normal_qss = (
            f"QFrame#portRow {{ background: transparent; border: 1px solid transparent; "
            f"border-radius: {row_radius}px; }} QLabel {{ background: transparent; border: none; }}"
        )
        self._row_selected_qss = (
            f"QFrame#portRow {{ background: {row_selected_bg}; "
            f"border: 1px solid {row_selected_border}; border-radius: {row_radius}px; }} "
            f"QLabel {{ background: transparent; border: none; }}"
        )
        self._notify_colors = t

    def _apply_history_style(self):
        """历史按钮样式。"""
        history_qss = (
            "QPushButton#historyBtn { background: transparent; border: none; "
            "color: rgba(255,255,255,170); font-size: 15px; }"
            "QPushButton#historyBtn:hover { color: white; background: rgba(255,255,255,40); "
            "border-radius: 4px; }"
        )
        self._history_btn.setStyleSheet(history_qss)

    def _on_alpha_changed(self, value):
        """滑条拖动：实时更新背景透明度并持久化。"""
        self._panel_alpha = value
        self.apply_theme()
        if self._config is not None:
            self._config.set("panel_alpha", value)

    # ---------- 串口列表 ----------

    def update_ports(self, ports, details=None, force=False):
        """刷新当前串口列表。ports: {device: description}；details 可选完整信息。

        force=True 时跳过内容指纹缓存强制重建（修复界面叠影）。
        """
        signature = tuple(
            sorted((d, ports[d], self._alias_store.get(d)) for d in ports)
        )
        if not force and signature == self._ports_signature:
            # 内容完全一致，不重建不重绘
            return
        self._ports_signature = signature
        self._last_ports = dict(ports)
        self._last_details = dict(details) if details else {}
        self._rows = []
        while self._port_list_layout.count():
            item = self._port_list_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                # 先隐藏再销毁，避免 deleteLater 生效前旧行残留叠在新行上
                w.hide()
                w.setParent(None)
                w.deleteLater()
        if not ports:
            self._empty_label = QLabel("暂无串口设备")
            self._empty_label.setObjectName("emptyLabel")
            self._port_list_layout.addWidget(self._empty_label)
            self._selected_device = None
        else:
            # 选中的串口已拔出则清除选中态
            if self._selected_device not in ports:
                self._selected_device = None
            for device in sorted(ports, key=self._port_sort_key):
                desc = ports[device].replace(f"({device})", "").strip()
                row = PortRow(
                    device,
                    desc,
                    self._alias_store.get(device),
                    info=(details or {}).get(device),
                    parent=self._panel,
                    style_normal=self._row_normal_qss,
                    style_selected=self._row_selected_qss,
                    font_size=self._font_size,
                )
                row.edit_requested.connect(self._edit_alias)
                row.clicked.connect(self._on_row_clicked)
                row.set_selected(device == self._selected_device)
                self._port_list_layout.addWidget(row)
                self._rows.append(row)
        self._count_label.setText(f"{len(ports)} 个串口")
        self._shrink()

    def _on_row_clicked(self, device):
        # 再次点击已选中行则取消选中
        self._selected_device = None if device == self._selected_device else device
        for row in self._rows:
            row.set_selected(row.device == self._selected_device)

    # ---------- 插拔事件历史 ----------

    def log_event(self, device, desc, added):
        """记录一条插拔事件，超过上限时淘汰最旧条目。"""
        self._event_log.append({
            "device": device, "desc": desc, "added": added,
            "timestamp": datetime.now(),
        })
        if len(self._event_log) > EVENT_LOG_MAX:
            self._event_log = self._event_log[-EVENT_LOG_MAX:]
        if self._history_visible:
            self._rebuild_history()

    def _on_history_clicked(self):
        self._history_visible = not self._history_visible
        if self._history_visible:
            self._rebuild_history()
            self._history_panel.show()
        else:
            self._history_panel.hide()
        self._shrink()

    def _rebuild_history(self):
        """清空并重建历史面板内容。"""
        while self._history_layout.count():
            item = self._history_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        if not self._event_log:
            lbl = QLabel("暂无记录")
            lbl.setObjectName("emptyLabel")
            self._history_layout.addWidget(lbl)
            return
        # 最新在上
        for entry in reversed(self._event_log):
            alias = self._alias_store.get(entry["device"])
            item = EventLogItem(
                entry["device"], entry["desc"], entry["added"],
                alias, entry["timestamp"],
                parent=self._history_panel,
                colors=self._notify_colors,
                font_size=self._font_size,
            )
            self._history_layout.addWidget(item)

    def _edit_alias(self, device):
        """弹出输入框编辑备注名，保存后立即刷新并持久化。"""
        self._editing = True
        try:
            text, ok = QInputDialog.getText(
                self,
                "编辑串口备注",
                f"{device} 对应的设备名称（留空则清除备注）：",
                QLineEdit.Normal,
                self._alias_store.get(device),
            )
        finally:
            self._editing = False
        if ok:
            self._alias_store.set(device, text)
            self.update_ports(self._last_ports)

    @staticmethod
    def _port_sort_key(device):
        # COM10 排在 COM2 之后
        digits = "".join(ch for ch in device if ch.isdigit())
        return (device.rstrip("0123456789"), int(digits) if digits else 0)

    # ---------- 通知 ----------

    def add_notification(self, device, desc, added, lifetime_ms=NOTIFY_LIFETIME_MS):
        alias = self._alias_store.get(device)
        item = NotificationItem(
            device,
            desc,
            added,
            alias,
            lifetime_ms,
            self._panel,
            colors=self._notify_colors,
            font_size=self._font_size,
        )
        item.closed.connect(self._on_notification_closed)
        self._notify_layout.addWidget(item)
        self._shrink()

    def has_notifications(self):
        return self._notify_layout.count() > 0

    def _on_notification_closed(self, _item):
        # deleteLater 尚未生效，用 singleShot 等布局稳定后再收缩
        QTimer.singleShot(0, self._after_notification_closed)

    def _after_notification_closed(self):
        self._shrink()
        if self.auto_shown and not self.has_notifications() and not self._editing:
            self.auto_shown = False
            self.hide()

    def _shrink(self):
        """内容变化后延迟排版并收缩高度（合并多次调用）。"""
        if not self._shrink_pending:
            self._shrink_pending = True
            QTimer.singleShot(0, self._do_shrink)

    def _do_shrink(self):
        self._shrink_pending = False
        # 强制重新排版；高度没变化就不 resize，亚克力窗口 resize 会白闪
        self._panel.layout().activate()
        self.layout().activate()
        target = self.sizeHint().height()
        if self.height() != target:
            self.resize(self._card_width, target)
