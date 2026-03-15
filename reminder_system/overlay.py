"""Overlay window for displaying reminders."""

from pathlib import Path
from typing import Optional, TYPE_CHECKING

from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, pyqtSignal
from PyQt6.QtGui import QPixmap, QColor, QPainter, QBrush, QPen, QGuiApplication
from PyQt6.QtWidgets import (
    QWidget,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QGraphicsOpacityEffect,
    QSizePolicy,
)

if TYPE_CHECKING:
    from .config import GeneralConfig, ReminderConfig


class CircleButton(QPushButton):
    """A circular button with a single glyph icon."""

    def __init__(self, icon_text: str, color: str, hover_color: str, parent=None):
        """Initialise the button with fixed colours and glyph text."""
        super().__init__(parent)
        self.icon_text = icon_text
        self.base_color = color
        self.hover_color = hover_color
        self.current_color = color

        self.setFixedSize(60, 60)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("background: transparent; border: none;")

    def paintEvent(self, event):
        """Paint the circular button and centre its glyph."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.setBrush(QBrush(QColor(self.current_color)))
        painter.setPen(QPen(QColor(self.current_color).darker(120), 2))
        painter.drawEllipse(5, 5, 50, 50)

        painter.setPen(QPen(QColor("white")))
        font = painter.font()
        font.setPointSize(24)
        font.setBold(True)
        painter.setFont(font)

        tight_rect = painter.fontMetrics().tightBoundingRect(self.icon_text)
        circle_center_x = 30
        circle_center_y = 30
        x = circle_center_x - tight_rect.width() // 2 - tight_rect.x()
        y = circle_center_y - tight_rect.height() // 2 - tight_rect.y()
        painter.drawText(x, y, self.icon_text)

    def enterEvent(self, event):
        """Swap to the hover colour when the pointer enters the button."""
        super().enterEvent(event)
        self.current_color = self.hover_color
        self.update()

    def leaveEvent(self, event):
        """Restore the base colour when the pointer leaves the button."""
        super().leaveEvent(event)
        self.current_color = self.base_color
        self.update()


class ReminderOverlay(QWidget):
    """Transparent full-screen overlay used to display reminders."""

    completed = pyqtSignal(str)
    snoozed = pyqtSignal(str, int)

    DEFAULT_FADE_IN_DURATION = 2000
    DEFAULT_FADE_OUT_DURATION = 500
    BACKGROUND_FADE_DELAY = 1000

    DEFAULT_TEXT_FONT = "Sans Serif"
    DEFAULT_TEXT_SIZE = 24
    DEFAULT_ICON_SCALE = 1.0
    DEFAULT_MAX_OPACITY = 0.85

    def __init__(self, parent=None, general_config: Optional["GeneralConfig"] = None):
        """Create the overlay and apply the initial general settings."""
        super().__init__(parent)

        self.reminder_name: str = ""
        self.snooze_duration: int = 300
        self.background_opacity: float = 0.0
        self.is_interactive: bool = False
        self.reminder_text: Optional[str] = None
        self._current_icon_path: Optional[Path] = None
        self._dismissing: bool = False

        self.text_font = self.DEFAULT_TEXT_FONT
        self.text_size = self.DEFAULT_TEXT_SIZE
        self.icon_scale = self.DEFAULT_ICON_SCALE
        self.max_opacity = self.DEFAULT_MAX_OPACITY
        self.fade_in_duration = self.DEFAULT_FADE_IN_DURATION
        self.fade_out_duration = self.DEFAULT_FADE_OUT_DURATION

        self._setup_window()
        self._setup_ui()
        self._setup_animations()

        if general_config is not None:
            self.apply_general_config(general_config)

    def apply_general_config(self, general_config: "GeneralConfig") -> None:
        """Apply general display settings to the existing overlay instance."""
        self.text_font = general_config.text_font
        self.text_size = general_config.text_size
        self.icon_scale = general_config.icon_scale
        self.max_opacity = general_config.max_opacity
        self.fade_in_duration = general_config.fade_in_duration
        self.fade_out_duration = general_config.fade_out_duration

        self._update_text_label_style()
        self.container_fade_anim.setDuration(self.fade_in_duration)
        if hasattr(self, "_fade_out_container"):
            self._fade_out_container.setDuration(self.fade_out_duration)

        if self.reminder_name:
            self._render_current_reminder()
        self.update()

    def update_active_reminder(self, config: "ReminderConfig") -> None:
        """Refresh the displayed reminder content without replaying animations."""
        self.reminder_name = config.name
        self.snooze_duration = config.snooze_duration
        self.reminder_text = config.text
        self._current_icon_path = config.icon_path
        self._render_current_reminder()

    def _setup_window(self):
        """Configure the full-screen transparent overlay window."""
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        screen = QGuiApplication.primaryScreen()
        if screen:
            self.setGeometry(screen.geometry())

    def _setup_ui(self):
        """Create the reminder icon, text, and action buttons."""
        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.container = QWidget()
        self.container.setStyleSheet("background: transparent;")
        container_layout = QVBoxLayout(self.container)
        container_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        container_layout.setSpacing(0)

        self.container_opacity = QGraphicsOpacityEffect()
        self.container_opacity.setOpacity(0.0)
        self.container.setGraphicsEffect(self.container_opacity)

        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setStyleSheet("background: transparent;")
        container_layout.addWidget(self.icon_label)

        container_layout.addSpacing(25)

        self.text_label = QLabel()
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text_label.setWordWrap(True)
        self.text_label.setMaximumWidth(600)
        self.text_label.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Minimum,
        )
        self._update_text_label_style()
        self.text_label.hide()
        container_layout.addWidget(self.text_label)

        container_layout.addSpacing(25)

        self.buttons_container = QWidget()
        self.buttons_container.setStyleSheet("background: transparent;")
        buttons_layout = QHBoxLayout(self.buttons_container)
        buttons_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        buttons_layout.setSpacing(40)

        self.complete_btn = CircleButton("✔", "#4CAF50", "#66BB6A")
        self.complete_btn.setToolTip("Mark as complete")
        self.complete_btn.clicked.connect(self._on_complete)

        self.snooze_btn = CircleButton("⏳", "#757575", "#9E9E9E")
        self.snooze_btn.setToolTip("Snooze")
        self.snooze_btn.clicked.connect(self._on_snooze)

        buttons_layout.addWidget(self.complete_btn)
        buttons_layout.addWidget(self.snooze_btn)
        container_layout.addWidget(self.buttons_container)

        main_layout.addWidget(self.container)

    def _update_text_label_style(self):
        """Refresh the text label stylesheet from the current settings."""
        self.text_label.setStyleSheet(
            f"""
            background: transparent;
            color: white;
            font-family: \"{self.text_font}\";
            font-size: {self.text_size}px;
        """
        )

    def _setup_animations(self):
        """Initialise fade animations and supporting timers."""
        self.container_fade_anim = QPropertyAnimation(
            self.container_opacity, b"opacity"
        )
        self.container_fade_anim.setDuration(self.fade_in_duration)
        self.container_fade_anim.setStartValue(0.0)
        self.container_fade_anim.setEndValue(1.0)
        self.container_fade_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

        self.bg_fade_timer = QTimer()
        self.bg_fade_timer.setInterval(16)
        self.bg_fade_timer.timeout.connect(self._animate_background)
        self.bg_target_opacity = 0.0
        self.bg_fade_step = 0.0

        self.bg_delay_timer = QTimer()
        self.bg_delay_timer.setSingleShot(True)
        self.bg_delay_timer.timeout.connect(self._start_background_fade)

        self.interactive_timer = QTimer()
        self.interactive_timer.setSingleShot(True)
        self.interactive_timer.timeout.connect(self._make_interactive)

    def paintEvent(self, event):
        """Paint the semi-transparent backdrop behind the reminder content."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(0, 0, 0, int(255 * self.background_opacity * self.max_opacity))
        painter.fillRect(self.rect(), color)

    def show_reminder(
        self,
        name: str,
        icon_path: Path,
        snooze_duration: int = 300,
        text: Optional[str] = None,
    ):
        """Populate the overlay and start its entrance animation."""
        self.reminder_name = name
        self.snooze_duration = snooze_duration
        self.background_opacity = 0.0
        self.is_interactive = False
        self._dismissing = False
        self.reminder_text = text
        self._current_icon_path = icon_path

        self._render_current_reminder()
        self.container_opacity.setOpacity(0.0)

        self.show()
        self.raise_()

        self.container_fade_anim.setDuration(self.fade_in_duration)
        self.container_fade_anim.start()
        self.bg_delay_timer.start(self.BACKGROUND_FADE_DELAY)

    def _render_current_reminder(self) -> None:
        """Render the current reminder icon and text using active settings."""
        self.icon_label.clear()
        self.icon_label.setStyleSheet("background: transparent;")

        scaled_size = int(200 * self.icon_scale)
        if self._current_icon_path and self._current_icon_path.exists():
            pixmap = QPixmap(str(self._current_icon_path))
            scaled_pixmap = pixmap.scaled(
                scaled_size,
                scaled_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.icon_label.setPixmap(scaled_pixmap)
        else:
            self.icon_label.setText(f"⏰\n{self.reminder_name}")
            self.icon_label.setStyleSheet(
                """
                background: transparent;
                color: white;
                font-size: 48px;
                font-weight: bold;
            """
            )

        if self.reminder_text:
            self.text_label.setText(self.reminder_text)
            self.text_label.show()
        else:
            self.text_label.hide()

    def _start_background_fade(self):
        """Start fading the backdrop in behind the content."""
        self.bg_target_opacity = 0.7
        bg_fade_duration = int(self.fade_in_duration * 1.5)
        steps = bg_fade_duration / 16
        self.bg_fade_step = self.bg_target_opacity / steps
        self.bg_fade_timer.start()

    def _animate_background(self):
        """Advance the backdrop opacity towards its current target."""
        self.background_opacity += self.bg_fade_step

        if self.bg_fade_step > 0 and self.background_opacity >= self.bg_target_opacity:
            self.background_opacity = self.bg_target_opacity
            self.bg_fade_timer.stop()
            self.interactive_timer.start(200)
        elif self.bg_fade_step < 0 and self.background_opacity <= 0:
            self.background_opacity = 0.0
            self.bg_fade_timer.stop()

        self.update()

    def _make_interactive(self):
        """Allow the user to interact with the action buttons."""
        self.is_interactive = True

    def _on_complete(self):
        """Dismiss the overlay and emit a completion event."""
        if not self.is_interactive or self._dismissing:
            return
        self._dismiss()
        self.completed.emit(self.reminder_name)

    def _on_snooze(self):
        """Dismiss the overlay and emit a snooze event."""
        if self._dismissing:
            return
        self._dismiss()
        self.snoozed.emit(self.reminder_name, self.snooze_duration)

    def _dismiss(self):
        """Fade the overlay out from its current animation state."""
        self._dismissing = True

        self.container_fade_anim.stop()
        self.bg_delay_timer.stop()
        self.bg_fade_timer.stop()
        self.interactive_timer.stop()

        steps = self.fade_out_duration / 16
        self.bg_target_opacity = 0.0
        if self.background_opacity > 0 and steps > 0:
            self.bg_fade_step = -self.background_opacity / steps
            self.bg_fade_timer.start()
        else:
            self.background_opacity = 0.0

        current_opacity = self.container_opacity.opacity()
        self._fade_out_container = QPropertyAnimation(
            self.container_opacity, b"opacity"
        )
        self._fade_out_container.setDuration(self.fade_out_duration)
        self._fade_out_container.setStartValue(current_opacity)
        self._fade_out_container.setEndValue(0.0)
        self._fade_out_container.start()

        QTimer.singleShot(self.fade_out_duration + 100, self._finish_dismiss)

    def _finish_dismiss(self):
        """Hide the overlay and reset dismissal state."""
        self.hide()
        self._dismissing = False

    def keyPressEvent(self, event):
        """Handle keyboard shortcuts for snooze and complete actions."""
        if event.key() == Qt.Key.Key_Escape:
            self._on_snooze()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._on_complete()
        super().keyPressEvent(event)
