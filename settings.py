# -*- coding: utf-8 -*-
# Global Anki Add-on - Settings
#
# Author: PeaceMonk
# License: GNU AGPLv3

import os
from aqt import mw
from aqt.qt import *
from PyQt6.QtCore import pyqtSignal as Signal, pyqtProperty, QPropertyAnimation, QEasingCurve, QPointF

# --- Custom Widgets (Merged from custom_widgets.py) ---

class SegmentedControl(QWidget):
    """A custom widget that functions like a radio button group but looks like a segmented control."""
    current_changed = Signal(str)

    def __init__(self, options=None, parent=None):
        super().__init__(parent)
        self._options = options if options else []
        self._buttons = []
        self._current_selection = ""

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        # Add spacing between buttons to make them distinct
        layout.setSpacing(10)
        self.setLayout(layout)

        for i, option in enumerate(self._options):
            button = QPushButton(option)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(self._on_button_clicked)
            self._buttons.append(button)
            layout.addWidget(button)
        
        # --- Styling is handled by the main dialog's stylesheet ---

    def _on_button_clicked(self):
        sender = self.sender()
        if sender.isChecked():
            self._current_selection = sender.text()
            for button in self._buttons:
                if button is not sender:
                    button.setChecked(False)
            self.current_changed.emit(self._current_selection)

    def current_text(self):
        return self._current_selection

    def set_current(self, text):
        for button in self._buttons:
            if button.text().lower() == text.lower():
                button.setChecked(True)
                self._current_selection = button.text()
                break

class AnimatedToggleButton(QAbstractButton):
    """ A custom animated toggle switch that uses the palette for theme colors. """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(44, 24)
        
        self._thumb_x_pos = 2.0

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

    def _start_animation(self, checked):
        thumb_size = self.height() - 4
        end_pos = self.width() - thumb_size - 2 if checked else 2
        self.animation.setStartValue(self.thumb_x_pos)
        self.animation.setEndValue(end_pos)
        self.animation.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Using a fixed color from the logo for the 'on' state
        accent_color = QColor("#56B0F8")
        track_color_off = self.palette().color(QPalette.ColorRole.Mid)

        # Determine thumb color based on checked state
        if self.isChecked():
            thumb_color = self.palette().color(QPalette.ColorRole.Button)
        else:
            thumb_color = QColor("#56B0F8")
        
        height = self.height()
        radius = height / 2.0
        
        painter.setPen(Qt.PenStyle.NoPen)
        track_color = accent_color if self.isChecked() else track_color_off
        painter.setBrush(track_color)
        painter.drawRoundedRect(self.rect(), radius, radius)

        thumb_radius = radius - 2
        painter.setBrush(thumb_color)
        
        thumb_y = radius
        thumb_center_x = self._thumb_x_pos + thumb_radius
        
        painter.drawEllipse(QPointF(thumb_center_x, thumb_y), thumb_radius, thumb_radius)

    def _set_initial_pos(self):
        thumb_size = self.height() - 4
        self._thumb_x_pos = self.width() - thumb_size - 2 if self.isChecked() else 2
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self._set_initial_pos()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._set_initial_pos()

class SectionGroup(QWidget):
    """ A simple container widget with a title. """
    def __init__(self, title, parent=None):
        super().__init__(parent)
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(0, 15, 0, 15)

        title_label = QLabel(title)
        # Styling is now handled by the main stylesheet
        main_layout.addWidget(title_label)
        
        self.content_layout = QVBoxLayout()
        self.content_layout.setContentsMargins(0, 5, 0, 0)
        main_layout.addLayout(self.content_layout)

    def add_widget(self, widget):
        self.content_layout.addWidget(widget)

    def add_layout(self, layout):
        self.content_layout.addLayout(layout)


# --- Main Settings Dialog ---

class SettingsDialog(QDialog):
    def __init__(self, parent=None, config=None, addon_name=None):
        super().__init__(parent)
        self.config = config
        self.addon_folder_name = addon_name
        self.setWindowTitle("Global Settings")

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # --- Header with Logo and Buttons ---
        logo_label = QLabel()
        logo_path = os.path.join(mw.addonManager.addonsFolder(), self.addon_folder_name, "global_logo.png")
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path)
            # Scaled to a fixed height to maintain aspect ratio
            logo_label.setPixmap(pixmap.scaledToHeight(50, Qt.TransformationMode.SmoothTransformation))
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(logo_label)

        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 10, 0, 10)
        button_layout.setSpacing(10)
        button_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.donate_button = QPushButton("Donate")
        self.donate_button.setObjectName("LinkButton")
        self.donate_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.donate_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://buymeacoffee.com/peacemonk")))

        self.report_button = QPushButton("Report Bugs")
        self.report_button.setObjectName("LinkButton")
        self.report_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.report_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://github.com/thepeacemonk/Global")))

        button_layout.addStretch()
        button_layout.addWidget(self.donate_button)
        button_layout.addWidget(self.report_button)
        button_layout.addStretch()
        main_layout.addLayout(button_layout)
        
        # Add a separator line
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        main_layout.addWidget(separator)


        # --- View Mode Section ---
        view_section = SectionGroup("View mode")
        self.view_control = SegmentedControl(["Vertical", "Horizontal", "Mini"])
        self.view_control.set_current(self.config.get("view_mode", "vertical"))
        view_section.add_widget(self.view_control)
        main_layout.addWidget(view_section)

        # --- Temperature Unit Section ---
        temp_section = SectionGroup("Temperature unit")
        self.temp_control = SegmentedControl(["Celsius", "Fahrenheit"])
        temp_unit = "fahrenheit" if self.config.get("units") == "imperial" else "celsius"
        self.temp_control.set_current(temp_unit)
        temp_section.add_widget(self.temp_control)
        main_layout.addWidget(temp_section)

        # --- Appearance Section ---
        appearance_section = SectionGroup("Appearance")
        form_layout = QFormLayout()
        form_layout.setSpacing(15)
        form_layout.setContentsMargins(0, 5, 0, 5)

        self.gradient_toggle = AnimatedToggleButton()
        self.gradient_toggle.setChecked(self.config.get("enable_gradients", True))
        form_layout.addRow(QLabel("Gradient"), self.gradient_toggle)

        # Opacity Slider
        opacity_layout = QHBoxLayout()
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(int(self.config.get("card_opacity", 1.0) * 100))
        
        self.opacity_label = QLabel(f"{self.opacity_slider.value()}%")
        self.opacity_label.setMinimumWidth(40)
        self.opacity_slider.valueChanged.connect(lambda val: self.opacity_label.setText(f"{val}%"))
        
        opacity_layout.addWidget(self.opacity_slider)
        opacity_layout.addWidget(self.opacity_label)
        form_layout.addRow(QLabel("Opacity"), opacity_layout)
        
        appearance_section.add_layout(form_layout)
        main_layout.addWidget(appearance_section)
        
        # --- Data Source Section ---
        data_section = SectionGroup("Data Source")
        
        instructions = QLabel(
            "1. Go to open-meteo.com.\n"
            "2. Select your location and desired weather variables.\n"
            "3. Copy the generated API URL and paste it below."
        )
        instructions.setWordWrap(True)
        instructions.setObjectName("InstructionsLabel")
        data_section.add_widget(instructions)

        self.custom_url_input = QLineEdit()
        self.custom_url_input.setText(self.config.get("custom_api_url", ""))
        self.custom_url_input.setPlaceholderText("https://api.open-meteo.com/v1/forecast...")
        data_section.add_widget(self.custom_url_input)

        self.custom_url_check = QCheckBox("Use custom API URL")
        self.custom_url_check.setChecked(self.config.get("use_custom_url", False))
        self.custom_url_check.toggled.connect(self.custom_url_input.setEnabled)
        self.custom_url_input.setEnabled(self.custom_url_check.isChecked())
        data_section.add_widget(self.custom_url_check)

        main_layout.addWidget(data_section)
        main_layout.addStretch()

        # --- Save/Cancel Buttons ---
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.save_settings)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)

        self.setLayout(main_layout)
        self.apply_styles() # Apply the new centralized stylesheet
        self.setMinimumWidth(500)

    def apply_styles(self):
        """Applies a theme-aware stylesheet to the dialog."""
        # Use an object name for titles to allow specific styling
        for group in self.findChildren(SectionGroup):
            group.findChild(QLabel).setObjectName("SectionTitle")

        shared_style = """
            #LinkButton {
                background-color: #56B0F8;
                color: white;
                border: none;
                padding: 8px 16px;
                font-size: 14px;
                border-radius: 8px;
                font-weight: 500;
            }
            #LinkButton:hover {
                background-color: #4AA0E8;
            }
            QLineEdit:focus {
                border-color: #56B0F8;
            }
            QSlider::groove:horizontal {
                border: 1px solid #bbb;
                background: white;
                height: 8px;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #56B0F8;
                border: 1px solid #56B0F8;
                width: 18px;
                margin: -5px 0;
                border-radius: 9px;
            }
            QDialogButtonBox QPushButton {
                padding: 6px 20px;
                font-size: 14px;
                border-radius: 5px;
            }
        """

        if mw.pm.night_mode():
            stylesheet = shared_style + """
                QDialog { background-color: #2F2F2F; color: #E0E0E0; }
                QLabel, QCheckBox { color: #E0E0E0; }
                #SectionTitle { color: #FFFFFF; font-size: 20px; font-weight: 500; }
                #InstructionsLabel { font-size: 13px; color: #b0b0b0; }
                QFrame[frameShape="4"] { border: 1px solid #424242; }
                QLineEdit { 
                    background-color: #424242; color: #E0E0E0; 
                    border: 1px solid #555555; border-radius: 4px; padding: 6px; 
                }
                SegmentedControl QPushButton {
                    padding: 6px 16px; font-size: 14px; border: 1px solid #555555;
                    border-radius: 8px; background-color: #424242; color: #E0E0E0;
                }
                SegmentedControl QPushButton:hover { background-color: #4f4f4f; }
                SegmentedControl QPushButton:checked {
                    background-color: #555555; color: white; border-color: #56B0F8;
                }
                QSlider::groove:horizontal {
                    background: #555;
                    border: 1px solid #555;
                }
                QSlider::sub-page:horizontal {
                    background: #07599D;
                }
                QDialogButtonBox QPushButton { 
                    background-color: #424242; border: 1px solid #555;
                }
                QDialogButtonBox QPushButton:hover { background-color: #4f4f4f; }
                QDialogButtonBox QPushButton:default { 
                    background-color: #56B0F8; color: white; border: none;
                }
            """
        else:
            stylesheet = shared_style + """
                QDialog { background-color: #F5F5F5; }
                QLabel, QCheckBox { color: #212121; }
                #SectionTitle { color: #000000; font-size: 20px; font-weight: 500; }
                #InstructionsLabel { font-size: 13px; color: #555; }
                QFrame[frameShape="4"] { border: 1px solid #E0E0E0; }
                QLineEdit { 
                    background-color: #FFFFFF; color: #212121; 
                    border: 1px solid #C5C5C5; border-radius: 4px; padding: 6px; 
                }
                SegmentedControl QPushButton {
                    background-color: #E0E0E0; color: #555; border: none;
                    padding: 6px 16px; font-size: 14px; border-radius: 8px;
                }
                SegmentedControl QPushButton:hover { background-color: #D5D5D5; }
                SegmentedControl QPushButton:checked {
                    background-color: #FFFFFF; color: #000; 
                    border: 1px solid #56B0F8;
                }
                QSlider::groove:horizontal {
                    background: #E0E0E0;
                    border: 1px solid #E0E0E0;
                }
                QSlider::sub-page:horizontal {
                    background: #07599D;
                }
                QDialogButtonBox QPushButton { 
                    background-color: #E0E0E0; border: none;
                }
                QDialogButtonBox QPushButton:hover { background-color: #D5D5D5; }
                QDialogButtonBox QPushButton:default { 
                    background-color: #56B0F8; color: white; border: none;
                }
            """
        self.setStyleSheet(stylesheet)


    def save_settings(self):
        self.config["view_mode"] = self.view_control.current_text().lower()
        self.config["units"] = "imperial" if self.temp_control.current_text().lower() == "fahrenheit" else "metric"
        self.config["enable_gradients"] = self.gradient_toggle.isChecked()
        self.config["card_opacity"] = self.opacity_slider.value() / 100.0
        self.config["use_custom_url"] = self.custom_url_check.isChecked()
        self.config["custom_api_url"] = self.custom_url_input.text().strip()
        self.config["last_fetch_time"] = 0
        self.config["last_weather_data"] = None

        mw.addonManager.writeConfig(self.addon_folder_name, self.config)
        
        if mw.state == "deckBrowser":
            mw.deckBrowser.refresh()
            
        self.accept()




