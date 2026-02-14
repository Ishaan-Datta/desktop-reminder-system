"""Overlay window for displaying reminders."""

import sys
from pathlib import Path
from typing import Optional, Callable, TYPE_CHECKING

from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, 
    QSize, pyqtSignal, QRect, QPoint
)
from PyQt6.QtGui import (
    QPixmap, QColor, QPainter, QBrush, QPen,
    QScreen, QGuiApplication, QPainterPath, QRegion, QFont
)
from PyQt6.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, 
    QHBoxLayout, QGraphicsOpacityEffect, QApplication,
    QSizePolicy
)

if TYPE_CHECKING:
    from .config import GeneralConfig


class CircleButton(QPushButton):
    """A circular button with an icon."""
    
    def __init__(self, icon_text: str, color: str, hover_color: str, parent=None):
        super().__init__(parent)
        self.icon_text = icon_text
        self.base_color = color
        self.hover_color = hover_color
        self.current_color = color
        
        self.setFixedSize(60, 60)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("background: transparent; border: none;")
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw circle background
        painter.setBrush(QBrush(QColor(self.current_color)))
        painter.setPen(QPen(QColor(self.current_color).darker(120), 2))
        painter.drawEllipse(5, 5, 50, 50)
        
        # Draw icon text centered using tight bounding rect for accurate positioning
        painter.setPen(QPen(QColor("white")))
        font = painter.font()
        font.setPointSize(24)
        font.setBold(True)
        painter.setFont(font)
        
        # Use tightBoundingRect to get the actual visual bounds of the glyph
        circle_center_x = 5 + 25  # circle x + radius
        circle_center_y = 5 + 25  # circle y + radius
        tight_rect = painter.fontMetrics().tightBoundingRect(self.icon_text)
        x = circle_center_x - tight_rect.width() // 2 - tight_rect.x()
        y = circle_center_y - tight_rect.height() // 2 - tight_rect.y()
        painter.drawText(x, y, self.icon_text)
    
    def enterEvent(self, event):
        self.current_color = self.hover_color
        self.update()
    
    def leaveEvent(self, event):
        self.current_color = self.base_color
        self.update()


class ReminderOverlay(QWidget):
    """
    A transparent overlay window that displays reminder notifications.
    
    Features:
    - Borderless, transparent window
    - Centered on screen
    - Gradual fade-in of icon and background
    - Non-focusable initially (doesn't steal focus)
    - Complete and snooze buttons
    - Optional text display under the icon
    - Configurable font, icon scale, opacity, and animation timings
    """
    
    completed = pyqtSignal(str)  # Emits reminder name when completed
    snoozed = pyqtSignal(str, int)  # Emits reminder name and snooze duration
    
    # Default animation timings (milliseconds) - can be overridden by config
    DEFAULT_FADE_IN_DURATION = 2000
    DEFAULT_FADE_OUT_DURATION = 500
    BACKGROUND_FADE_DELAY = 1000
    
    # Default styling
    DEFAULT_TEXT_FONT = "Sans Serif"
    DEFAULT_TEXT_SIZE = 24
    DEFAULT_ICON_SCALE = 1.0
    DEFAULT_MAX_OPACITY = 0.85
    
    def __init__(self, parent=None, general_config: Optional["GeneralConfig"] = None):
        super().__init__(parent)
        
        self.reminder_name: str = ""
        self.snooze_duration: int = 300
        self.background_opacity: float = 0.0
        self.is_interactive: bool = False
        self.reminder_text: Optional[str] = None
        
        # Apply general config or use defaults
        if general_config:
            self.text_font = general_config.text_font
            self.text_size = general_config.text_size
            self.icon_scale = general_config.icon_scale
            self.max_opacity = general_config.max_opacity
            self.fade_in_duration = general_config.fade_in_duration
            self.fade_out_duration = general_config.fade_out_duration
        else:
            self.text_font = self.DEFAULT_TEXT_FONT
            self.text_size = self.DEFAULT_TEXT_SIZE
            self.icon_scale = self.DEFAULT_ICON_SCALE
            self.max_opacity = self.DEFAULT_MAX_OPACITY
            self.fade_in_duration = self.DEFAULT_FADE_IN_DURATION
            self.fade_out_duration = self.DEFAULT_FADE_OUT_DURATION
        
        self._setup_window()
        self._setup_ui()
        self._setup_animations()
    
    def _setup_window(self):
        """Configure window properties for overlay behavior."""
        # Frameless, transparent window - set flags once and never change them
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool  # Doesn't show in taskbar
        )
        
        # Enable transparency
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        
        # Set to full screen size
        screen = QGuiApplication.primaryScreen()
        if screen:
            geometry = screen.geometry()
            self.setGeometry(geometry)
    
    def _setup_ui(self):
        """Set up the UI components."""
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Container widget for icon, text, and buttons
        self.container = QWidget()
        self.container.setStyleSheet("background: transparent;")
        container_layout = QVBoxLayout(self.container)
        container_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        container_layout.setSpacing(0)  # We'll control spacing manually for symmetry
        
        # Single opacity effect for entire container (icon + text + buttons together)
        self.container_opacity = QGraphicsOpacityEffect()
        self.container_opacity.setOpacity(0.0)
        self.container.setGraphicsEffect(self.container_opacity)
        
        # Icon label
        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setStyleSheet("background: transparent;")
        
        container_layout.addWidget(self.icon_label)
        
        # Spacing between icon and text (same as between text and buttons)
        container_layout.addSpacing(25)
        
        # Text label (between icon and buttons)
        self.text_label = QLabel()
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text_label.setWordWrap(True)
        self.text_label.setMaximumWidth(600)  # Limit width for word wrap
        self.text_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self._update_text_label_style()
        self.text_label.hide()  # Hidden by default, shown when text is provided
        
        container_layout.addWidget(self.text_label)
        
        # Spacing between text and buttons (same as between icon and text)
        container_layout.addSpacing(25)
        
        # Buttons container
        self.buttons_container = QWidget()
        self.buttons_container.setStyleSheet("background: transparent;")
        buttons_layout = QHBoxLayout(self.buttons_container)
        buttons_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        buttons_layout.setSpacing(40)
        
        # Complete button (green checkmark)
        self.complete_btn = CircleButton("✔", "#4CAF50", "#66BB6A")
        self.complete_btn.setToolTip("Mark as complete")
        self.complete_btn.clicked.connect(self._on_complete)
        
        # Snooze button (grey - using nerd font clock icon)
        self.snooze_btn = CircleButton("⏳", "#757575", "#9E9E9E")  # Nerd font clock icon
        self.snooze_btn.setToolTip("Snooze")
        self.snooze_btn.clicked.connect(self._on_snooze)
        
        buttons_layout.addWidget(self.complete_btn)
        buttons_layout.addWidget(self.snooze_btn)
        
        container_layout.addWidget(self.buttons_container)
        
        main_layout.addWidget(self.container)
    
    def _update_text_label_style(self):
        """Update the text label style based on current settings."""
        self.text_label.setStyleSheet(f"""
            background: transparent;
            color: white;
            font-family: "{self.text_font}";
            font-size: {self.text_size}px;
        """)
    
    def _setup_animations(self):
        """Set up the fade animations."""
        # Container fade-in animation (icon + text + buttons together)
        self.container_fade_anim = QPropertyAnimation(self.container_opacity, b"opacity")
        self.container_fade_anim.setDuration(self.fade_in_duration)
        self.container_fade_anim.setStartValue(0.0)
        self.container_fade_anim.setEndValue(1.0)
        self.container_fade_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        
        # Background fade timer (we'll animate this manually)
        self.bg_fade_timer = QTimer()
        self.bg_fade_timer.setInterval(16)  # ~60 FPS
        self.bg_fade_timer.timeout.connect(self._animate_background)
        self.bg_target_opacity = 0.0
        self.bg_fade_step = 0.0
        
        # Timer to start background fade after delay
        self.bg_delay_timer = QTimer()
        self.bg_delay_timer.setSingleShot(True)
        self.bg_delay_timer.timeout.connect(self._start_background_fade)
        
        # Timer to make window interactive after fade completes
        self.interactive_timer = QTimer()
        self.interactive_timer.setSingleShot(True)
        self.interactive_timer.timeout.connect(self._make_interactive)
    
    def paintEvent(self, event):
        """Paint the semi-transparent background."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw semi-transparent black background using configurable max_opacity
        color = QColor(0, 0, 0, int(255 * self.background_opacity * self.max_opacity))
        painter.fillRect(self.rect(), color)
    
    def show_reminder(self, name: str, icon_path: Path, snooze_duration: int = 300, 
                       text: Optional[str] = None):
        """
        Show a reminder with the specified icon.
        
        Args:
            name: The name of the reminder
            icon_path: Path to the icon PNG file
            snooze_duration: Snooze duration in seconds
            text: Optional text to display under the icon
        """
        self.reminder_name = name
        self.snooze_duration = snooze_duration
        self.background_opacity = 0.0
        self.is_interactive = False
        self.reminder_text = text
        
        # Calculate scaled icon size based on icon_scale
        base_size = 200
        scaled_size = int(base_size * self.icon_scale)
        
        # Load and set the icon
        if icon_path.exists():
            pixmap = QPixmap(str(icon_path))
            # Scale to size based on icon_scale while maintaining aspect ratio
            scaled_pixmap = pixmap.scaled(
                scaled_size, scaled_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.icon_label.setPixmap(scaled_pixmap)
        else:
            # Fallback: show reminder name as text
            self.icon_label.setText(f"⏰\n{name}")
            self.icon_label.setStyleSheet("""
                background: transparent;
                color: white;
                font-size: 48px;
                font-weight: bold;
            """)
        
        # Set up text label if text is provided
        if text:
            self.text_label.setText(text)
            self.text_label.show()
        else:
            self.text_label.hide()
        
        # Reset container opacity
        self.container_opacity.setOpacity(0.0)
        
        # Show window
        self.show()
        self.raise_()
        
        # Start animations - container and background fade together
        self.container_fade_anim.setDuration(self.fade_in_duration)
        self.container_fade_anim.start()
        self.bg_delay_timer.start(self.BACKGROUND_FADE_DELAY)
    
    def _start_background_fade(self):
        """Start the background fade animation."""
        self.bg_target_opacity = 0.7
        # Calculate step size for smooth animation based on fade_in_duration
        # Background fade takes about 1.5x the container fade duration
        bg_fade_duration = int(self.fade_in_duration * 1.5)
        steps = bg_fade_duration / 16
        self.bg_fade_step = self.bg_target_opacity / steps
        self.bg_fade_timer.start()
    
    def _animate_background(self):
        """Animate the background opacity."""
        self.background_opacity += self.bg_fade_step
        
        if self.bg_fade_step > 0 and self.background_opacity >= self.bg_target_opacity:
            self.background_opacity = self.bg_target_opacity
            self.bg_fade_timer.stop()
            
            # Make window interactive after background is visible
            self.interactive_timer.start(200)
        elif self.bg_fade_step < 0 and self.background_opacity <= 0:
            self.background_opacity = 0.0
            self.bg_fade_timer.stop()
        
        self.update()
    
    def _make_interactive(self):
        """Make the window interactive (accept clicks)."""
        self.is_interactive = True
    
    def _on_complete(self):
        """Handle complete button click."""
        if not self.is_interactive:
            return
        self._dismiss()
        self.completed.emit(self.reminder_name)
    
    def _on_snooze(self):
        """Handle snooze button click."""
        if not self.is_interactive:
            return
        self._dismiss()
        self.snoozed.emit(self.reminder_name, self.snooze_duration)
    
    def _dismiss(self):
        """Dismiss the overlay with fade-out animation."""
        # Calculate fade step to match fade_out_duration
        # step = current_opacity / (duration / interval)
        steps = self.fade_out_duration / 16
        self.bg_target_opacity = 0.0
        self.bg_fade_step = -self.background_opacity / steps if steps > 0 else -0.05
        self.bg_fade_timer.start()
        
        # Fade out container (icon + text + buttons together)
        self._fade_out_container = QPropertyAnimation(self.container_opacity, b"opacity")
        self._fade_out_container.setDuration(self.fade_out_duration)
        self._fade_out_container.setEndValue(0.0)
        self._fade_out_container.start()
        
        # Hide after animation
        QTimer.singleShot(self.fade_out_duration + 100, self.hide)
    
    def keyPressEvent(self, event):
        """Handle key presses."""
        if event.key() == Qt.Key.Key_Escape:
            self._on_snooze()
        elif event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            self._on_complete()
        super().keyPressEvent(event)


def test_overlay():
    """Test the overlay window."""
    app = QApplication(sys.argv)
    
    overlay = ReminderOverlay()
    overlay.completed.connect(lambda name: print(f"Completed: {name}"))
    overlay.snoozed.connect(lambda name, dur: print(f"Snoozed: {name} for {dur}s"))
    
    # Test with a placeholder
    test_icon = Path("/tmp/test_icon.png")
    overlay.show_reminder("Test Reminder", test_icon, 300)
    
    sys.exit(app.exec())


if __name__ == "__main__":
    test_overlay()
