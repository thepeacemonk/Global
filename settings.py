# -*- coding: utf-8 -*-
import os
import copy
import importlib
from datetime import datetime, timedelta
from aqt import mw
from aqt.qt import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QWidget, QFormLayout,
    QColorDialog, QColor, QSlider, QSpinBox, Qt, QPixmap, QScrollArea, QLineEdit,
    pyqtSignal, QFrame, QButtonGroup, QAbstractButton, QApplication, QCheckBox, QDesktopServices
)
try:
    from PyQt6.QtCore import pyqtProperty, QPropertyAnimation, QEasingCurve, QRectF, QParallelAnimationGroup, QPointF, QUrl, QSize, QTimer
    from PyQt6.QtGui import QPainter, QPen, QColor as QColor2, QPainterPath, QFont, QBrush
    from PyQt6.QtWidgets import QStyleFactory, QSizePolicy
except ImportError:
    from PyQt5.QtCore import pyqtProperty, QPropertyAnimation, QEasingCurve, QRectF, QParallelAnimationGroup, QPointF, QUrl, QSize, QTimer
    from PyQt5.QtGui import QPainter, QPen, QColor as QColor2, QPainterPath, QFont, QBrush
    from PyQt5.QtWidgets import QStyleFactory, QSizePolicy
from aqt.utils import showInfo
from aqt.theme import theme_manager
from aqt.webview import AnkiWebView
from . import bento_integration

# --- Shared UI Components (from Berry design) ---
class AnimatedToggleButton(QAbstractButton):
    def __init__(self, parent=None, accent_color="#56B0F8"):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.accent_color = QColor(accent_color)
        self.track_color_off = QColor("#cccccc") if not theme_manager.night_mode else QColor("#555555")
        self.thumb_color = QColor("#ffffff")
        self.setFixedSize(38, 20)
        self._track_inset = 3.0
        self._thumb_x_pos = self._thumb_position(False)
        self.animation = QPropertyAnimation(self, b"thumb_x_pos", self)
        self.animation.setDuration(150)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.toggled.connect(self._start_animation)

    @pyqtProperty(float)
    def thumb_x_pos(self):
        return self._thumb_x_pos

    @thumb_x_pos.setter
    def thumb_x_pos(self, value):
        self._thumb_x_pos = value
        self.update()

    def _thumb_position(self, checked):
        """Keep the thumb inset identical from either end of the track."""
        return (self.width() - self.height() + self._track_inset) if checked else self._track_inset

    def _start_animation(self, checked):
        end_pos = self._thumb_position(checked)
        self.animation.setStartValue(self.thumb_x_pos)
        self.animation.setEndValue(end_pos)
        self.animation.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        height = self.height()
        radius = height / 2.0
        painter.setPen(Qt.PenStyle.NoPen)
        track_color = self.accent_color if self.isChecked() else self.track_color_off
        painter.setBrush(track_color)
        painter.drawRoundedRect(self.rect(), radius, radius)
        thumb_radius = radius - 3
        painter.setBrush(self.thumb_color)
        thumb_y = radius
        painter.drawEllipse(QPointF(self._thumb_x_pos + thumb_radius, thumb_y), thumb_radius, thumb_radius)

    def showEvent(self, event):
        super().showEvent(event)
        self._thumb_x_pos = self._thumb_position(self.isChecked())
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._thumb_x_pos = self._thumb_position(self.isChecked())
        self.update()

class GooeySegmentedControl(QWidget):
    def __init__(self, accent_color="#56B0F8", parent=None, bg_color="#f2f2f2", border_color="#dcdde1"):
        super().__init__(parent)
        self.setObjectName("themeToggleContainer")
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(0)
        self._accent_color = QColor(accent_color)
        self._bg_color = QColor(bg_color)
        self._border_color = QColor(border_color)
        self._indicator_rect = QRectF(4, 4, 0, 0)
        self.anim_group = QParallelAnimationGroup(self)
        self.anim_x = QPropertyAnimation(self, b"indicator_x")
        self.anim_width = QPropertyAnimation(self, b"indicator_width")
        self.anim_group.addAnimation(self.anim_x)
        self.anim_group.addAnimation(self.anim_width)
        self.anim_x.setEasingCurve(QEasingCurve.Type.InOutBack)
        self.anim_width.setEasingCurve(QEasingCurve.Type.InOutBack)
        self.anim_x.setDuration(400)
        self.anim_width.setDuration(400)
        self.button_group = QButtonGroup(self)
        self.button_group.buttonClicked.connect(self.animate_to)

    @pyqtProperty(float)
    def indicator_x(self):
        return self._indicator_rect.x()

    @indicator_x.setter
    def indicator_x(self, value):
        self._indicator_rect.setX(value)
        self.update()

    @pyqtProperty(float)
    def indicator_width(self):
        return self._indicator_rect.width()

    @indicator_width.setter
    def indicator_width(self, value):
        self._indicator_rect.setWidth(value)
        self.update()

    def add_button(self, btn):
        self._layout.addWidget(btn)
        self.button_group.addButton(btn)

    def animate_to(self, btn):
        if not btn: return
        target_rect = btn.geometry()
        if target_rect.width() == 0: return
        self.anim_x.setStartValue(self.indicator_x)
        self.anim_x.setEndValue(float(target_rect.x()))
        self.anim_width.setStartValue(self.indicator_width)
        self.anim_width.setEndValue(float(target_rect.width()))
        self.anim_group.start()

    def update_indicator_no_animation(self):
        checked_btn = self.button_group.checkedButton()
        if checked_btn and checked_btn.geometry().width() > 0:
            r = checked_btn.geometry()
            self._indicator_rect.setX(r.x())
            self._indicator_rect.setWidth(r.width())
            self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_indicator_no_animation()

    def showEvent(self, event):
        super().showEvent(event)
        try:
            from PyQt6.QtCore import QTimer
        except ImportError:
            from PyQt5.QtCore import QTimer
        QTimer.singleShot(50, self.update_indicator_no_animation)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw the pill track ourselves (radius = actual height / 2) instead of
        # relying on QSS border-radius, which doesn't clamp large values the
        # way CSS does and can render as a barely-rounded rectangle.
        track_radius = self.height() / 2.0
        track_rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        track_path = QPainterPath()
        track_path.addRoundedRect(track_rect, track_radius, track_radius)
        p.setPen(QPen(self._border_color, 1))
        p.setBrush(self._bg_color)
        p.drawPath(track_path)

        if self._indicator_rect.width() > 0:
            # The InOutBack easing on the slide animation overshoots past its
            # target (that's what gives it the "gooey" bounce), which can push
            # the indicator's rounded corner past x=0 mid-animation. Clipping
            # to the track's own rounded path (rather than the widget's plain
            # rectangular bounds) means any overshoot gets bounded by the
            # pill's curve instead of being sliced off into a flat edge.
            p.setClipPath(track_path)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(self._accent_color)
            checked_btn = self.button_group.checkedButton()
            h = checked_btn.geometry().height() if checked_btn else 28
            y = checked_btn.geometry().y() if checked_btn else 4
            rect = QRectF(self._indicator_rect.x(), float(y), self._indicator_rect.width(), float(h))
            radius = h / 2.0
            p.drawRoundedRect(rect, radius, radius)


class PillEffectSlider(QSlider):
    """Rounded, segmented slider styled after Onigiri's background-effect sliders."""

    def __init__(self, accent_color, track_color, border_color, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self._accent_color = QColor(accent_color)
        self._track_color = QColor(track_color)
        self._border_color = QColor(border_color)
        self._handle_color = QColor("#ffffff")
        self.setFixedHeight(30)
        self.setMouseTracking(True)

    def wheelEvent(self, event):
        event.ignore()

    def sizeHint(self):
        hint = super().sizeHint()
        return QSize(max(220, hint.width()), 30)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        paint_pad = 4
        track_height = 22
        handle_radius = (track_height / 2) - 3
        track_left = paint_pad
        track_right = max(track_left + track_height + 1, self.width() - paint_pad)
        track_width = track_right - track_left
        track_top = (self.height() - track_height) / 2
        track_rect = QRectF(track_left, track_top, track_width, track_height)
        handle_min_x = track_rect.left() + (track_height / 2)
        handle_max_x = track_rect.right() - (track_height / 2)

        value_range = max(1, self.maximum() - self.minimum())
        progress = max(0.0, min(1.0, (self.value() - self.minimum()) / value_range))
        handle_x = handle_min_x + (handle_max_x - handle_min_x) * progress

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._track_color))
        painter.drawRoundedRect(track_rect, track_height / 2, track_height / 2)

        if progress <= 0.0:
            active_width = 0.0
        elif progress >= 1.0:
            active_width = track_width
        else:
            active_width = min(track_width, max(0.0, handle_x + handle_radius - track_left))
        if active_width > 0:
            active_rect = QRectF(track_left, track_top, active_width, track_height)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(self._accent_color))
            painter.drawRoundedRect(active_rect, track_height / 2, track_height / 2)

        for step in range(1, 6):
            x = track_left + track_width * step / 6
            if x <= track_left + active_width:
                continue
            mark_color = QColor(self._border_color)
            mark_color.setAlpha(95)
            painter.setPen(QPen(mark_color, 1))
            painter.drawLine(QPointF(x, track_top + 4), QPointF(x, track_top + track_height - 4))

        handle_rect = QRectF(
            handle_x - handle_radius,
            (self.height() / 2) - handle_radius,
            handle_radius * 2,
            handle_radius * 2,
        )
        painter.setBrush(QBrush(self._handle_color))
        painter.setPen(QPen(self._accent_color, 3))
        painter.drawEllipse(handle_rect)


class SectionGroup(QWidget):
    def __init__(self, title="", parent=None, description=""):
        super().__init__(parent)
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(0, 5, 0, 0)
        title_label = QLabel(title)
        title_label.setStyleSheet("font-weight: bold; font-size: 17px; margin-bottom: 2px;")
        main_layout.addWidget(title_label)
        if description:
            desc_label = QLabel(description)
            desc_label.setStyleSheet("font-size: 11px; color: #888; margin-bottom: 5px;")
            desc_label.setWordWrap(True)
            main_layout.addWidget(desc_label)
        self.content_area = QWidget()
        self.content_area.setObjectName("innerGroup")
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(15, 15, 15, 15)
        self.content_layout.setSpacing(10)
        main_layout.addWidget(self.content_area)

    def add_widget(self, widget):
        self.content_layout.addWidget(widget)

    def add_layout(self, layout):
        self.content_layout.addLayout(layout)


# ─── Live Preview ────────────────────────────────────────────────────────────

# How many rows/columns each view mode needs in Onigiri's Bento widget grid.
_GRID_FOOTPRINT = {
    "mini": (2, 2),
    "horizontal": (2, 3),
}


def _preview_opacity_css(config):
    """Apply the card opacity to the whole preview card, including its content.

    ``generate_css()`` uses the setting as an alpha on card backgrounds so
    production cards blend with the menu wallpaper.  The settings preview
    also needs to fade the card contents; otherwise dragging below 100% only
    changes a subtle background layer while text and icons remain opaque.
    """
    try:
        opacity = float((config or {}).get("card_opacity", 1.0))
    except (TypeError, ValueError):
        opacity = 1.0
    opacity = max(0.0, min(1.0, opacity))
    return f"#global-container .global-card {{ opacity: {opacity:.4f} !important; }}"

_PREVIEW_VARIANTS = {
    "sunny": {
        "current_code": 1,
        "code_cycle": [1, 2, 0, 1, 2, 3],
        "daily_codes": [1, 0, 2, 1],
        "daily_max": [24, 19, 21, 26],
        "daily_min": [14, 12, 13, 16],
        "temperature_2m": 21.0,
        "apparent_temperature": 20.0,
        "relative_humidity_2m": 58,
        "hourly_temp_base": 20,
    },
    "rain": {
        "current_code": 61,
        "code_cycle": [61, 63, 80, 61, 65, 63],
        "daily_codes": [61, 63, 80, 65],
        "daily_max": [19, 17, 18, 20],
        "daily_min": [11, 10, 12, 13],
        "temperature_2m": 15.0,
        "apparent_temperature": 13.5,
        "relative_humidity_2m": 82,
        "hourly_temp_base": 15,
    },
}


def _build_preview_weather_data(variant="sunny"):
    """Builds a static sample forecast so the preview never needs a network call."""
    spec = _PREVIEW_VARIANTS.get(variant, _PREVIEW_VARIANTS["sunny"])
    now = datetime.now()
    hours = 12
    hourly_time = [(now + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%S") for i in range(1, hours + 1)]
    hourly_temp = [spec["hourly_temp_base"] + (i % 4) for i in range(hours)]
    hourly_code = [spec["code_cycle"][i % len(spec["code_cycle"])] for i in range(hours)]
    aqi_values = [40 + (i * 3) % 30 for i in range(hours)]

    daily_time = [(now + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(4)]

    return {
        "city": "Sample City",
        "forecast": {
            "current": {
                "temperature_2m": spec["temperature_2m"],
                "relative_humidity_2m": spec["relative_humidity_2m"],
                "is_day": 1 if 6 <= now.hour < 19 else 0,
                "weather_code": spec["current_code"],
                "apparent_temperature": spec["apparent_temperature"],
            },
            "hourly": {"time": hourly_time, "temperature_2m": hourly_temp, "weather_code": hourly_code},
            "daily": {
                "time": daily_time,
                "weather_code": spec["daily_codes"],
                "temperature_2m_max": spec["daily_max"],
                "temperature_2m_min": spec["daily_min"],
            },
        },
        "aqi": {"hourly": {"time": hourly_time, "us_aqi": aqi_values}},
    }


class GlobalPreviewWidget(QWidget):
    """Renders a live HTML preview of the Global weather widget using sample data."""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._variant = "sunny"
        self._weather_data = _build_preview_weather_data(self._variant)

        self.preview_layout = QVBoxLayout(self)
        self.preview_layout.setContentsMargins(0, 0, 0, 0)

        self.webview = None

        # The centering/scale math is baked into the generated HTML from Qt's
        # actual widget size (see refresh()), so it has to be regenerated
        # whenever that size changes rather than trying to adapt in JS.
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self.refresh)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_timer.start(120)

    def cleanup(self):
        """Release the embedded AnkiWebView before this widget is destroyed.

        AnkiWebView wraps a QWebEngineView; if it is left to be torn down
        implicitly during Python interpreter finalization (Anki quitting),
        Qt dereferences already-freed child widgets and segfaults. Cleaning
        it up explicitly on dialog close avoids that.
        """
        if getattr(self, "_resize_timer", None) is not None:
            self._resize_timer.stop()
        if getattr(self, "webview", None) is not None:
            if getattr(self, "webview", None):
                self.webview.cleanup()
            self.webview = None

    def set_variant(self, variant):
        if variant == self._variant:
            return
        self._variant = variant
        self._weather_data = _build_preview_weather_data(variant)
        self.refresh()


    def showEvent(self, event):
        super().showEvent(event)
        if getattr(self, "webview", None) is None:
            self.webview = AnkiWebView(title="global_preview", parent=self)
            self.webview.setMinimumSize(260, 300)
            self.webview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self.webview.disable_zoom()
            # Make the webview background transparent so the dialog bg shows
            # through instead of a gray rectangle.
            page = self.webview.page()
            page.setBackgroundColor(QColor(0, 0, 0, 0))
            self.preview_layout.addWidget(self.webview)
            self.refresh()

    def refresh(self):
        if not getattr(self, "webview", None):
            return
        addon_module = importlib.import_module(__package__)
        is_dark = theme_manager.night_mode

        css = addon_module.generate_css(is_dark, self.config)
        css += _preview_opacity_css(self.config)
        html_content = addon_module.generate_html(self._weather_data, self.config)
        sizing_css = bento_integration.sizing_css(
            "#global-container", "#global-weather-wrapper", self.config,
            default_width=211, default_height=300,
        )
        wrapper_class = "night_mode" if is_dark else ""

        # Behind the widget: Onigiri's actual deck-browser wallpaper when the
        # integration is active, otherwise the same flat color as this dialog.
        settings_bg = "#181818" if is_dark else "#f7f7f7"
        wallpaper = None
        if bento_integration.is_onigiri_detected():
            wallpaper = bento_integration.main_menu_wallpaper(is_dark)
        if not wallpaper:
            wallpaper = {"kind": "color", "color": settings_bg}

        if wallpaper["kind"] == "image":
            bg_layer_css = f"""
                background-color: {wallpaper['color']};
                background-image: url('{wallpaper['url']}');
                background-size: cover; background-position: center; background-repeat: no-repeat;
                filter: blur({wallpaper['blur_px']}px);
                opacity: {wallpaper['opacity']};
            """
        else:
            bg_layer_css = f"background-color: {wallpaper['color']}; opacity: 1;"

        # Fit-to-panel is computed entirely here in Python and baked into the
        # CSS below as literal numbers — no runtime JS measurement of the page
        # (scrollWidth/window.innerWidth/etc.) is involved. That measurement
        # was the unreliable part in earlier attempts; removing it removes the
        # failure mode instead of chasing its timing.
        #
        # Natural (unscaled) size per view mode, with a small safety margin.
        # Measured directly (via an offscreen unscaled DOM clone), not the CSS
        # max-width/height declarations — the horizontal grid's fr-sized
        # columns settle well under the 600px cap (376px measured).
        natural_sizes = {"horizontal": (376, 212), "mini": (211, 260)}
        natural_w, natural_h = natural_sizes.get(self.config.get("view_mode", "mini"), (211, 260))

        panel_w = self.webview.width()
        panel_h = self.webview.height()
        if panel_w < 100 or panel_h < 100:
            panel_w, panel_h = 320, 400

        avail_w = panel_w - 40
        avail_h = panel_h - 40
        factor = min(1.0, avail_w / natural_w, avail_h / natural_h) * 0.94
        # +2px so sub-pixel rendering of the scaled content (fractional
        # `transform: scale()` output) can never end up a hair taller/wider
        # than the box it's clipped to.
        final_w = natural_w * factor + 2
        final_h = natural_h * factor + 2

        full_html = f"""
        <html><head><style>
            html, body {{ margin: 0; padding: 0; height: 100%; overflow: hidden; background: transparent; }}
            body {{
                position: relative;
                display: flex; align-items: center; justify-content: center;
                background: transparent;
            }}
            #onigiri-bg-container {{
                position: absolute; inset: 10px; z-index: 0;
                border-radius: 20px; overflow: hidden;
                transform: translateZ(0);
            }}
            #onigiri-bg-layer {{
                position: absolute; inset: -50px;
                {bg_layer_css}
            }}
            /* Only the box's own size (final_w/final_h) comes from Python;
               centering it is left entirely to flexbox on <body> above,
               rather than computing left/top ourselves — one less place
               for a stale/mismatched panel size to throw off the result.
               No overflow:hidden here: if the estimate falls a hair short,
               the card should spill slightly into the margin rather than
               have its rounded bottom edge sliced flat. */
            #scale-wrapper {{
                position: relative; z-index: 1;
                width: {final_w}px; height: {final_h}px;
                flex-shrink: 0;
            }}
            #global-container {{
                position: absolute; top: 0; left: 0;
                transform: scale({factor}); transform-origin: top left;
            }}
        </style></head>
        <body>
            <div id="onigiri-bg-container">
                <div id="onigiri-bg-layer"></div>
            </div>
            <div id="scale-wrapper">
                <div id="global-container" class="{wrapper_class}">
                    <style>{css}{sizing_css}</style>
                    <div id="global-weather-wrapper">{html_content}</div>
                </div>
            </div>
        </body></html>
        """
        self.webview.setHtml(full_html)


# ─── Flat-color pickers (shown when Gradient is off) ────────────────────────

def _parse_color(color_str):
    """Parse a hex or rgba color string into a QColor."""
    if not color_str:
        return QColor("#000000")
    if "rgba" in color_str:
        try:
            parts = color_str.replace("rgba(", "").replace(")", "").split(",")
            r, g, b = int(parts[0].strip()), int(parts[1].strip()), int(parts[2].strip())
            a = int(float(parts[3].strip()) * 255)
            return QColor(r, g, b, a)
        except (ValueError, IndexError):
            return QColor("#000000")
    c = QColor(color_str)
    return c if c.isValid() else QColor("#000000")


def _contrast_text_color(hex_color: str) -> str:
    c = hex_color.lstrip('#')
    r, g, b = tuple(int(c[i:i + 2], 16) for i in (0, 2, 4)) if len(c) in (6, 8) else (255, 255, 255)
    luminance = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0
    return "#111111" if luminance > 0.56 else "#ffffff"


def create_color_button(initial_color: str, parent: QWidget) -> QPushButton:
    button = QPushButton(parent)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setObjectName("colorSwatchButton")
    _apply_swatch_style(button, initial_color)
    return button


def _apply_swatch_style(button, color_str):
    text_color = _contrast_text_color(color_str)
    button.setText(color_str.upper())
    button.setStyleSheet(
        f"QPushButton#colorSwatchButton {{"
        f"  background-color: {color_str};"
        f"  color: {text_color};"
        f"  font-weight: bold;"
        f"  font-size: 13px;"
        f"  border: 1px solid rgba(0,0,0,0.15);"
        f"  border-radius: 12px;"
        f"  padding: 6px 16px;"
        f"}}"
        f"QPushButton#colorSwatchButton:hover {{"
        f"  border: 1px solid rgba(0,0,0,0.35);"
        f"}}"
    )


class SettingsDialog(QDialog):
    def __init__(self, parent=None, config=None, addon_name=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowTitle("Global Settings")
        
        screen = QApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            width, height = int(avail.width() * 0.5), int(avail.height() * 0.55)
            self.setGeometry(
                avail.x() + (avail.width() - width) // 2,
                avail.y() + (avail.height() - height) // 2,
                width,
                height
            )
        else:
            self.resize(820, 600)
        self.setMinimumSize(760, 500)

        self.addon_folder_name = addon_name
        self.source_config = config
        self.config = copy.deepcopy(config)
        self._ensure_default_colors()

        self.setup_ui()
        self.load_settings()

        # Tear down the embedded AnkiWebView and schedule the dialog for
        # deletion when it closes, so it does not linger as a child of the
        # main window with a live QWebEngineView (which segfaults during
        # interpreter shutdown). deleteLater() is used instead of
        # WA_DeleteOnClose because this dialog is shown with exec(): a
        # WA_DeleteOnClose delete happens inside the modal loop and frees the
        # dialog while exec() is still unwinding, which itself crashes.
        self.finished.connect(self._cleanup_on_close)

    def _cleanup_on_close(self, *args):
        preview = getattr(self, "preview_widget", None)
        if preview is not None:
            preview.cleanup()
        self.deleteLater()

    def _ensure_default_colors(self):
        colors = self.config.setdefault("colors", {})
        colors.setdefault("light", {}).setdefault("card_background", "#FFFFFF")
        colors.setdefault("dark", {}).setdefault("card_background", "#2C2F33")

    def _theme_tokens(self):
        is_dark = theme_manager.night_mode
        accent = "#56B0F8" # Global accent
        if is_dark:
            return {"bg": "#181818", "panel": "#242424", "surface": "#303030", "fg": "#f4f4f5", "muted": "#c4c4c4", "border": "#454545", "accent": accent}
        return {"bg": "#f7f7f7", "panel": "#ffffff", "surface": "#f2f2f2", "fg": "#202124", "muted": "#6f7177", "border": "#dcdde1", "accent": accent}

    def setup_ui(self):
        tokens = self._theme_tokens()
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Main controls container
        controls_outer = QWidget()
        controls_outer.setObjectName("controlsOuter")
        controls_outer_layout = QVBoxLayout(controls_outer)
        controls_outer_layout.setContentsMargins(8, 10, 8, 0)
        controls_outer_layout.setSpacing(0)

        controls_container = QFrame()
        controls_container.setObjectName("controlsContainer")
        controls_container.setFrameShape(QFrame.Shape.NoFrame)
        controls_container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        controls_container_layout = QVBoxLayout(controls_container)
        controls_container_layout.setContentsMargins(0, 0, 0, 0)
        controls_container_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setObjectName("controlsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Force the app's own (Fusion) style on the scrollbar so it honors our QSS
        # instead of falling back to the OS's native/overlay scrollbar rendering.
        self._scrollbar_style = QStyleFactory.create("Fusion")
        if self._scrollbar_style:
            scroll.verticalScrollBar().setStyle(self._scrollbar_style)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(28, 24, 28, 20)
        scroll_layout.setSpacing(20)
        scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # View Mode
        view_group = SectionGroup("View mode", self)
        self.view_toggle = GooeySegmentedControl(tokens["accent"], self, bg_color=tokens["surface"], border_color=tokens["border"])
        self.radio_horizontal = QPushButton("Pro")
        self.radio_mini = QPushButton("Mini")
        for btn in [self.radio_mini, self.radio_horizontal]:
            btn.setCheckable(True)
            btn.setObjectName("themeToggleButton")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(28)
            self.view_toggle.add_button(btn)
        self.view_toggle.button_group.buttonClicked.connect(self._on_view_changed)
        view_group.add_widget(self.view_toggle)
        scroll_layout.addWidget(view_group)

        # Temp Unit
        temp_group = SectionGroup("Temperature unit", self)
        self.temp_toggle = GooeySegmentedControl(tokens["accent"], self, bg_color=tokens["surface"], border_color=tokens["border"])
        self.radio_celsius = QPushButton("Celsius")
        self.radio_fahrenheit = QPushButton("Fahrenheit")
        for btn in [self.radio_celsius, self.radio_fahrenheit]:
            btn.setCheckable(True)
            btn.setObjectName("themeToggleButton")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(28)
            self.temp_toggle.add_button(btn)
        self.temp_toggle.button_group.buttonClicked.connect(self._on_temp_changed)
        temp_group.add_widget(self.temp_toggle)
        scroll_layout.addWidget(temp_group)

        # Appearance
        appearance_group = SectionGroup("Appearance", self)
        gradient_row = QWidget()
        gradient_layout = QHBoxLayout(gradient_row)
        gradient_layout.setContentsMargins(0, 0, 0, 0)
        gradient_layout.addWidget(QLabel("Gradient"))
        gradient_layout.addStretch()
        self.gradient_toggle = AnimatedToggleButton(accent_color=tokens["accent"])
        self.gradient_toggle.toggled.connect(self._on_gradient_changed)
        gradient_layout.addWidget(self.gradient_toggle)
        appearance_group.add_widget(gradient_row)

        opacity_row = QWidget()
        opacity_layout = QHBoxLayout(opacity_row)
        opacity_layout.setContentsMargins(0, 0, 0, 0)
        opacity_layout.addWidget(QLabel("Opacity"))
        self.opacity_slider = PillEffectSlider(tokens["accent"], tokens["surface"], tokens["border"])
        self.opacity_slider.setRange(0, 100)
        self.opacity_value_label = QLabel("100%")
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        opacity_layout.addWidget(self.opacity_slider, 1)
        opacity_layout.addWidget(self.opacity_value_label)
        appearance_group.add_widget(opacity_row)

        # Flat card colors, only relevant once the gradient is switched off
        self.colors_section = QWidget()
        colors_section_layout = QVBoxLayout(self.colors_section)
        colors_section_layout.setContentsMargins(0, 4, 0, 0)
        colors_section_layout.setSpacing(10)

        colors_header = QLabel("Card Color")
        colors_header.setStyleSheet(f"font-weight: 600; font-size: 13px; color: {tokens['muted']};")
        colors_section_layout.addWidget(colors_header)

        self.color_buttons = {}
        for mode_key, mode_label in (("light", "Light Theme"), ("dark", "Dark Theme")):
            row = self._create_color_row(mode_label, self.config["colors"][mode_key]["card_background"], mode_key)
            colors_section_layout.addWidget(row)

        appearance_group.add_widget(self.colors_section)
        scroll_layout.addWidget(appearance_group)

        integration_group, self.bento_width_spin, self.bento_height_spin = bento_integration.create_settings_group(
            self.config, default_width=211, default_height=300
        )
        self.bento_width_spin.valueChanged.connect(self._on_manual_size_changed)
        self.bento_height_spin.valueChanged.connect(self._on_manual_size_changed)
        scroll_layout.addWidget(integration_group)

        # Data Source
        data_group = SectionGroup("Data Source", self)
        instructions = QLabel(
            "1. Go to open-meteo.com.\n"
            "2. Select your location and desired weather variables.\n"
            "3. Copy the generated API URL and paste it below."
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet(f"font-size: 13px; color: {tokens['muted']};")
        data_group.add_widget(instructions)
        self.custom_url_input = QLineEdit()
        self.custom_url_input.setObjectName("CustomURLEdit")
        self.custom_url_input.setPlaceholderText("https://api.open-meteo.com/v1/forecast...")
        data_group.add_widget(self.custom_url_input)
        
        self.custom_url_check = QCheckBox("Use custom API URL")
        self.custom_url_check.toggled.connect(self.custom_url_input.setEnabled)
        data_group.add_widget(self.custom_url_check)
        scroll_layout.addWidget(data_group)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        # QScrollArea forces autoFillBackground on its viewport, which paints
        # an opaque gray regardless of QSS.  Disable it programmatically.
        scroll.viewport().setAutoFillBackground(False)
        scroll_content.setAutoFillBackground(False)
        controls_container.setAutoFillBackground(False)
        controls_container_layout.addWidget(scroll)
        controls_outer_layout.addWidget(controls_container)

        # ── Right: Preview panel ─────────────────────────────────────────
        preview_wrapper = QWidget()
        preview_wrapper.setObjectName("previewWrapper")
        preview_wrapper_layout = QVBoxLayout(preview_wrapper)
        preview_wrapper_layout.setContentsMargins(10, 24, 20, 20)
        preview_wrapper_layout.setSpacing(12)

        preview_header_row = QWidget()
        preview_header_layout = QHBoxLayout(preview_header_row)
        preview_header_layout.setContentsMargins(0, 0, 0, 0)

        preview_title = QLabel("Preview")
        preview_title.setStyleSheet(f"font-size: 12px; font-weight: 700; letter-spacing: 0.6px; color: {tokens['muted']};")
        preview_header_layout.addWidget(preview_title)
        preview_header_layout.addStretch()

        self.preview_variant_toggle = GooeySegmentedControl(tokens["accent"], self, bg_color=tokens["surface"], border_color=tokens["border"])
        self.radio_preview_sunny = QPushButton("Sunny")
        self.radio_preview_rain = QPushButton("Rain")
        for btn in [self.radio_preview_sunny, self.radio_preview_rain]:
            btn.setCheckable(True)
            btn.setObjectName("themeToggleButton")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(22)
            self.preview_variant_toggle.add_button(btn)
        self.radio_preview_sunny.setChecked(True)
        self.preview_variant_toggle.button_group.buttonClicked.connect(self._on_preview_variant_changed)
        preview_header_layout.addWidget(self.preview_variant_toggle)

        preview_wrapper_layout.addWidget(preview_header_row)

        self.preview_widget = GlobalPreviewWidget(self.config, self)
        preview_wrapper_layout.addWidget(self.preview_widget, 1)

        self.grid_info_label = QLabel("")
        self.grid_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.grid_info_label.setStyleSheet(f"font-size: 11px; color: {tokens['muted']};")
        preview_wrapper_layout.addWidget(self.grid_info_label)

        content_h_layout = QHBoxLayout()
        content_h_layout.setSpacing(0)
        content_h_layout.setContentsMargins(0, 0, 0, 0)
        content_h_layout.addWidget(controls_outer, 1)
        content_h_layout.addWidget(preview_wrapper, 1)
        root_layout.addLayout(content_h_layout, 1)

        # Bottom Pill Bar
        bottom_container = QWidget()
        bottom_container.setObjectName("bottomContainer")
        bottom_container_layout = QVBoxLayout(bottom_container)
        bottom_container_layout.setContentsMargins(20, 8, 20, 20)
        
        bottom_bar = QWidget()
        bottom_bar.setObjectName("bottomPillBar")
        bottom_bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        bottom_bar_layout = QHBoxLayout(bottom_bar)
        bottom_bar_layout.setContentsMargins(10, 10, 10, 10)
        bottom_bar_layout.setSpacing(8)

        logo_label = QLabel()
        logo_path = os.path.join(mw.addonManager.addonsFolder(), self.addon_folder_name, "global_logo.svg")
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path)
            scaled_pixmap = pixmap.scaled(200, 36, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            logo_label.setPixmap(scaled_pixmap)
            logo_label.setFixedSize(scaled_pixmap.size())
            logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            bottom_bar_layout.addWidget(logo_label)

        bottom_bar_layout.addSpacing(8)
        self.donate_button = QPushButton("Donate")
        self.donate_button.setObjectName("cancelButton")
        self.donate_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.report_button = QPushButton("Report Bug")
        self.report_button.setObjectName("cancelButton")
        self.report_button.setCursor(Qt.CursorShape.PointingHandCursor)
        bottom_bar_layout.addWidget(self.donate_button)
        bottom_bar_layout.addWidget(self.report_button)
        
        self.donate_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://buymeacoffee.com/peacemonk")))
        self.report_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://github.com/thepeacemonk/Global")))

        bottom_bar_layout.addStretch()
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("cancelButton")
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.clicked.connect(self.reject)
        self.save_button = QPushButton("Save")
        self.save_button.setObjectName("saveButton")
        self.save_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_button.clicked.connect(self.save_settings)
        
        bottom_bar_layout.addWidget(self.cancel_button)
        bottom_bar_layout.addWidget(self.save_button)

        bottom_container_layout.addWidget(bottom_bar)
        root_layout.addWidget(bottom_container)

        self._apply_stylesheet()

    def load_settings(self):
        current_view = self.config.get("view_mode", "mini")
        if current_view not in {"mini", "horizontal"}:
            current_view = "mini"
            self.config["view_mode"] = current_view
        if current_view == "horizontal": self.radio_horizontal.setChecked(True)
        else: self.radio_mini.setChecked(True)

        current_unit = "fahrenheit" if self.config.get("units") == "imperial" else "celsius"
        if current_unit == "fahrenheit": self.radio_fahrenheit.setChecked(True)
        else: self.radio_celsius.setChecked(True)

        self.gradient_toggle.setChecked(self.config.get("enable_gradients", True))
        
        initial_opacity = int(self.config.get("card_opacity", 1.0) * 100)
        self.opacity_slider.setValue(initial_opacity)
        self.opacity_value_label.setText(f"{initial_opacity}%")

        self.custom_url_input.setText(self.config.get("custom_api_url", ""))
        self.custom_url_check.setChecked(self.config.get("use_custom_url", False))
        self.custom_url_input.setEnabled(self.custom_url_check.isChecked())

        self._refresh_preview()

    def _refresh_preview(self):
        self.preview_widget.config = self.config
        self.preview_widget.refresh()

        if bento_integration.is_onigiri_detected():
            rows, cols = _GRID_FOOTPRINT.get(self.config.get("view_mode", "mini"), (2, 2))
            self.grid_info_label.setText(f"Needs {rows} rows / {cols} columns in Onigiri's widget grid")
        else:
            self.grid_info_label.setText("")

    def _on_view_changed(self, btn):
        if btn is self.radio_horizontal: self.config["view_mode"] = "horizontal"
        else: self.config["view_mode"] = "mini"
        self._refresh_preview()

    def _on_temp_changed(self, btn):
        self.config["units"] = "imperial" if btn is self.radio_fahrenheit else "metric"
        self._refresh_preview()

    def _on_gradient_changed(self, checked):
        self.config["enable_gradients"] = checked
        self.colors_section.setVisible(not checked)
        self._refresh_preview()

    def _on_opacity_changed(self, value):
        self.opacity_value_label.setText(f"{value}%")
        self.config["card_opacity"] = value / 100.0
        self._refresh_preview()

    def _on_manual_size_changed(self, _value):
        self.config[bento_integration.WIDTH_KEY] = int(self.bento_width_spin.value())
        self.config[bento_integration.HEIGHT_KEY] = int(self.bento_height_spin.value())
        self._refresh_preview()

    def _on_preview_variant_changed(self, btn):
        self.preview_widget.set_variant("rain" if btn is self.radio_preview_rain else "sunny")

    def _create_color_row(self, label_text, initial_color, mode_key):
        row = QFrame()
        row.setObjectName("colorRow")

        is_dark = theme_manager.night_mode
        bg_color = "#242424" if is_dark else "#FFFFFF"
        border_color = "#454545" if is_dark else "#DCDDE1"
        text_color = "#f4f4f5" if is_dark else "#1d1d1f"

        row.setStyleSheet(f"""
            QFrame#colorRow {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 12px;
            }}
        """)

        layout = QHBoxLayout(row)
        layout.setContentsMargins(16, 10, 16, 10)

        label = QLabel(label_text)
        label.setStyleSheet(
            f"font-weight: 700; font-size: 14px; border: none; "
            f"background: transparent; color: {text_color};"
        )
        layout.addWidget(label)
        layout.addStretch()

        btn = create_color_button(initial_color, self)
        btn.clicked.connect(lambda: self.pick_color(btn, mode_key))
        self.color_buttons[mode_key] = btn
        layout.addWidget(btn)

        return row

    def pick_color(self, button, mode_key):
        current_color_str = self.config["colors"][mode_key]["card_background"]

        try:
            onigiri_color_picker = importlib.import_module("1011095603.onigiri_color_picker")
            OnigiriColorDialog = onigiri_color_picker.OnigiriColorDialog
            new_color_hex, ok = OnigiriColorDialog.getColor(current_color_str, self, anchor=button)
            if ok:
                self.config["colors"][mode_key]["card_background"] = new_color_hex
                _apply_swatch_style(button, new_color_hex)
                self._refresh_preview()
            return
        except Exception as e:
            print(f"[Global] Failed to load OnigiriColorDialog: {e}")

        color = QColorDialog.getColor(_parse_color(current_color_str), self, f"Choose {mode_key.title()} Card Color")
        if color.isValid():
            new_color_str = color.name().upper()
            self.config["colors"][mode_key]["card_background"] = new_color_str
            _apply_swatch_style(button, new_color_str)
            self._refresh_preview()

    def save_settings(self):
        if self.radio_horizontal.isChecked(): self.config["view_mode"] = "horizontal"
        else: self.config["view_mode"] = "mini"

        if self.radio_fahrenheit.isChecked(): self.config["units"] = "imperial"
        else: self.config["units"] = "metric"
        
        self.config["enable_gradients"] = self.gradient_toggle.isChecked()
        self.config["card_opacity"] = self.opacity_slider.value() / 100.0
        self.config["use_custom_url"] = self.custom_url_check.isChecked()
        self.config["custom_api_url"] = self.custom_url_input.text().strip()
        
        bento_integration.save_settings_group(self.config, self.bento_width_spin, self.bento_height_spin)
        self.config["last_fetch_time"] = 0
        self.config["last_weather_data"] = None

        self.source_config.clear()
        self.source_config.update(self.config)
        mw.addonManager.writeConfig(self.addon_folder_name, self.source_config)
        if mw.state == "deckBrowser":
            mw.deckBrowser.refresh()
        self.accept()

    def _apply_stylesheet(self):
        t = self._theme_tokens()
        bg, panel, fg, muted, surface, border, accent = t["bg"], t["panel"], t["fg"], t["muted"], t["surface"], t["border"], t["accent"]
        accent_hex = accent.lstrip("#")
        accent_rgb = tuple(int(accent_hex[i:i+2], 16) for i in (0, 2, 4))
        scrollbar_thumb = f"rgba({accent_rgb[0]}, {accent_rgb[1]}, {accent_rgb[2]}, 0.45)"
        scrollbar_thumb_hover = f"rgba({accent_rgb[0]}, {accent_rgb[1]}, {accent_rgb[2]}, 0.75)"

        self.setStyleSheet(f"""
            QDialog {{ background-color: {bg}; color: {fg}; }}
            QFrame#controlsContainer {{
                background-color: transparent; border: none !important;
                border-top-left-radius: 28px; border-top-right-radius: 28px;
            }}
            QWidget#controlsOuter {{ background-color: transparent; border: none !important; }}
            QWidget#previewWrapper {{ background-color: transparent; border: none !important; }}
            QScrollArea#controlsScroll, QScrollArea#controlsScroll > QWidget {{
                background: transparent; border: none !important;
            }}
            AnkiWebView, QWebEngineView, GlobalPreviewWidget {{ border: none !important; }}
            QWidget#innerGroup {{
                background-color: transparent; border: none; border-radius: 12px;
            }}
            QLabel, QCheckBox {{ color: {fg}; font-size: 13px; }}
            #themeToggleButton {{
                background-color: transparent; border: none; border-radius: 14px;
                padding: 4px 16px; font-size: 13px; font-weight: 600; color: {muted};
            }}
            #themeToggleButton:checked {{ color: #ffffff; }}
            #themeToggleButton:hover:!checked {{ color: {fg}; }}
            QLineEdit#CustomURLEdit {{
                border: 1px solid {border}; background-color: {surface}; color: {fg};
                border-radius: 6px; padding: 6px; font-size: 13px;
            }}
            QPushButton {{
                background-color: {surface}; color: {fg}; border: 1px solid {border};
                padding: 6px 12px; border-radius: 14px;
            }}
            QPushButton:hover {{ background-color: {border}; }}
            QPushButton#saveButton {{
                background-color: {accent}; color: #ffffff; border: none;
                border-radius: 18px; min-height: 36px; max-height: 36px;
                padding: 0px 14px; font-size: 13px; font-weight: bold;
            }}
            QPushButton#saveButton:hover {{ background-color: {accent}; opacity: 0.9; }}
            QPushButton#cancelButton {{
                background-color: {surface}; color: {fg}; border: 1px solid {border};
                border-radius: 18px; min-height: 36px; max-height: 36px;
                padding: 0px 14px; font-size: 13px; font-weight: bold;
            }}
            QPushButton#cancelButton:hover {{ background-color: {border}; }}
            QWidget#bottomContainer {{ background-color: transparent; }}
            QWidget#bottomPillBar {{
                background-color: {panel}; border-radius: 28px; border: 1px solid {border};
            }}
            QSpinBox {{
                background-color: {panel}; color: {fg}; border: 1px solid {border};
                border-radius: 4px; padding: 5px;
            }}
            QScrollArea#controlsScroll QScrollBar:vertical {{
                background: {surface};
                width: 8px;
                margin: 0px;
                border: none;
            }}
            QScrollArea#controlsScroll QScrollBar::handle:vertical {{
                background: {scrollbar_thumb};
                min-height: 24px;
                border-radius: 4px;
            }}
            QScrollArea#controlsScroll QScrollBar::handle:vertical:hover {{
                background: {scrollbar_thumb_hover};
            }}
            QScrollArea#controlsScroll QScrollBar::add-line:vertical,
            QScrollArea#controlsScroll QScrollBar::sub-line:vertical {{
                height: 0px;
                background: none;
                border: none;
            }}
            QScrollArea#controlsScroll QScrollBar::add-page:vertical,
            QScrollArea#controlsScroll QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """)
# ── Bento WebUI settings -----------------------------------------------------
try:
    if getattr(mw, "onigiri_api", {}).get("id") != "1011095603":
        raise ImportError("Onigiri Bento API is not active")
    _bws = importlib.import_module("1011095603.api.widget_settings")
except Exception:
    _bws = None

if _bws is not None:
    class SettingsDialog(_bws.BentoSettingsDialog):
        def __init__(self, parent=None, config=None, addon_name=None):
            package = mw.addonManager.addonFromModule(addon_name or __name__)
            source = config if isinstance(config, dict) else (mw.addonManager.getConfig(package) or {})
            if source.get("view_mode") not in {None, "mini", "horizontal"}:
                source["view_mode"] = "mini"
            defaults = {
                "view_mode": "mini", "units": "metric", "enable_gradients": True,
                "card_opacity": 1.0, "colors": {"light": {"card_background": "#FFFFFF"}, "dark": {"card_background": "#2C2F33"}},
                "use_custom_url": False, "custom_api_url": "", "manual_widget_width": 211,
                "manual_widget_height": 300, "last_fetch_time": 0, "last_weather_data": None,
            }

            def save(updated):
                updated["last_fetch_time"] = 0
                updated["last_weather_data"] = None
                source.clear(); source.update(copy.deepcopy(updated))
                mw.addonManager.writeConfig(package, source)
                addon = importlib.import_module(__package__)
                addon.CONFIG.clear(); addon.CONFIG.update(copy.deepcopy(updated))
                if hasattr(addon, "reset_weather_cache"):
                    addon.reset_weather_cache()

            def preview(updated, variant, theme):
                addon = importlib.import_module(__package__)
                dark = theme == "dark"
                data = _build_preview_weather_data(variant)
                css = addon.generate_css(dark, updated)
                css += _preview_opacity_css(updated)
                css += bento_integration.sizing_css("#global-container", "#global-weather-wrapper", updated, default_width=211, default_height=300)
                body = f'<div id="global-container" class="{"night_mode" if dark else ""}"><div id="global-weather-wrapper">{addon.generate_html(data, updated)}</div></div>'
                return _bws.preview_document(body, css, dark=dark, wallpaper=bento_integration.main_menu_wallpaper(dark))

            pages = [
                _bws.page("forecast", "Forecast", [
                    _bws.section("Display", [
                        _bws.field("view_mode", "View mode", "select", default="mini", options=[
                            {"value": "mini", "label": "Mini"},
                            {"value": "horizontal", "label": "Pro"},
                        ]),
                        _bws.field("units", "Temperature unit", "select", default="metric", options=[
                            {"value": "metric", "label": "Celsius"}, {"value": "imperial", "label": "Fahrenheit"},
                        ]),
                    ]),
                    _bws.section("Data source", [
                        _bws.field("use_custom_url", "Use custom API URL", "bool", default=False),
                        _bws.field("custom_api_url", "Open-Meteo URL", default="", placeholder="https://api.open-meteo.com/v1/forecast…", show_if={"use_custom_url": True}),
                    ]),
                ], "Forecast layout, units, and data source.", "G"),
                _bws.page("appearance", "Appearance", [
                    _bws.section("Card", [
                        _bws.field("enable_gradients", "Weather gradients", "bool", default=True),
                        _bws.field("card_opacity", "Card opacity", "range", default=100, minimum=0, maximum=100, unit="%", scale=.01),
                        _bws.field("colors.light.card_background", "Light card color", "color", default="#FFFFFF", show_if={"enable_gradients": False}),
                        _bws.field("colors.dark.card_background", "Dark card color", "color", default="#2C2F33", show_if={"enable_gradients": False}),
                    ]),
                ], "Customize the production weather cards.", "◐"),
            ]
            super().__init__(
                parent, title="Global", subtitle="Weather on your Anki menu", accent="#56B0F8",
                pages=pages, config=source, defaults=defaults, save_callback=save,
                logo_path=os.path.join(os.path.dirname(__file__), "global_logo.svg"),
                mini_logo_path=os.path.join(os.path.dirname(__file__), "global_mini_logo.svg"),
                preview_callback=preview, preview_variants=[
                    {"value": "sunny", "label": "Sunny"}, {"value": "rain", "label": "Rain"},
                ], bugs_url="https://github.com/thepeacemonk/Global",
            )
