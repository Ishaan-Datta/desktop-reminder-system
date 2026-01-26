"""Overlay window for displaying reminders."""

import sys
from pathlib import Path
from typing import Optional, Callable

from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, 
    QSize, pyqtSignal, QRect, QPoint
)
from PyQt6.QtGui import (
    QPixmap, QColor, QPainter, QBrush, QPen,
    QScreen, QGuiApplication, QPainterPath, QRegion
)
from PyQt6.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, 
    QHBoxLayout, QGraphicsOpacityEffect, QApplication,
    QSizePolicy
)


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
        
        # Draw icon text
        painter.setPen(QPen(QColor("white")))
        font = painter.font()
        font.setPointSize(24)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.icon_text)
    
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
    """
    
    completed = pyqtSignal(str)  # Emits reminder name when completed
    snoozed = pyqtSignal(str, int)  # Emits reminder name and snooze duration
    
    # Animation timings (milliseconds)
    ICON_FADE_DURATION = 2000
    BACKGROUND_FADE_DURATION = 3000
    BACKGROUND_FADE_DELAY = 1000
    BUTTON_FADE_DURATION = 500
    DISMISS_FADE_DURATION = 500
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.reminder_name: str = ""
        self.snooze_duration: int = 300
        self.background_opacity: float = 0.0
        self.is_interactive: bool = False
        
        self._setup_window()
        self._setup_ui()
        self._setup_animations()
    
    def _setup_window(self):
        """Configure window properties for overlay behavior."""
        # Frameless, transparent window
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |  # Doesn't show in taskbar
            Qt.WindowType.WindowDoesNotAcceptFocus  # Don't steal focus initially
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
        
        # Container widget for icon and buttons
        self.container = QWidget()
        self.container.setStyleSheet("background: transparent;")
        container_layout = QVBoxLayout(self.container)
        container_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        container_layout.setSpacing(30)
        
        # Icon label
        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setStyleSheet("background: transparent;")
        
        # Opacity effect for icon
        self.icon_opacity = QGraphicsOpacityEffect()
        self.icon_opacity.setOpacity(0.0)
        self.icon_label.setGraphicsEffect(self.icon_opacity)
        
        container_layout.addWidget(self.icon_label)
        
        # Buttons container
        self.buttons_container = QWidget()
        self.buttons_container.setStyleSheet("background: transparent;")
        buttons_layout = QHBoxLayout(self.buttons_container)
        buttons_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        buttons_layout.setSpacing(40)
        
        # Complete button (green checkmark)
        self.complete_btn = CircleButton("✓", "#4CAF50", "#66BB6A")
        self.complete_btn.setToolTip("Mark as complete")
        self.complete_btn.clicked.connect(self._on_complete)
        
        # Snooze button (grey clock)
        self.snooze_btn = CircleButton("⏰", "#757575", "#9E9E9E")
        self.snooze_btn.setToolTip("Snooze")
        self.snooze_btn.clicked.connect(self._on_snooze)
        
        buttons_layout.addWidget(self.complete_btn)
        buttons_layout.addWidget(self.snooze_btn)
        
        # Opacity effect for buttons
        self.buttons_opacity = QGraphicsOpacityEffect()
        self.buttons_opacity.setOpacity(0.0)
        self.buttons_container.setGraphicsEffect(self.buttons_opacity)
        
        container_layout.addWidget(self.buttons_container)
        
        main_layout.addWidget(self.container)
    
    def _setup_animations(self):
        """Set up the fade animations."""
        # Icon fade-in animation
        self.icon_fade_anim = QPropertyAnimation(self.icon_opacity, b"opacity")
        self.icon_fade_anim.setDuration(self.ICON_FADE_DURATION)
        self.icon_fade_anim.setStartValue(0.0)
        self.icon_fade_anim.setEndValue(1.0)
        self.icon_fade_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        
        # Background fade timer (we'll animate this manually)
        self.bg_fade_timer = QTimer()
        self.bg_fade_timer.setInterval(16)  # ~60 FPS
        self.bg_fade_timer.timeout.connect(self._animate_background)
        self.bg_target_opacity = 0.0
        self.bg_fade_step = 0.0
        
        # Buttons fade-in animation
        self.buttons_fade_anim = QPropertyAnimation(self.buttons_opacity, b"opacity")
        self.buttons_fade_anim.setDuration(self.BUTTON_FADE_DURATION)
        self.buttons_fade_anim.setStartValue(0.0)
        self.buttons_fade_anim.setEndValue(1.0)
        self.buttons_fade_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        
        # Timer to start background fade after delay
        self.bg_delay_timer = QTimer()
        self.bg_delay_timer.setSingleShot(True)
        self.bg_delay_timer.timeout.connect(self._start_background_fade)
        
        # Timer to show buttons after background fades
        self.buttons_delay_timer = QTimer()
        self.buttons_delay_timer.setSingleShot(True)
        self.buttons_delay_timer.timeout.connect(self._show_buttons)
    
    def paintEvent(self, event):
        """Paint the semi-transparent background."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw semi-transparent black background
        color = QColor(0, 0, 0, int(255 * self.background_opacity * 0.85))
        painter.fillRect(self.rect(), color)
    
    def show_reminder(self, name: str, icon_path: Path, snooze_duration: int = 300):
        """
        Show a reminder with the specified icon.
        
        Args:
            name: The name of the reminder
            icon_path: Path to the icon PNG file
            snooze_duration: Snooze duration in seconds
        """
        self.reminder_name = name
        self.snooze_duration = snooze_duration
        self.background_opacity = 0.0
        self.is_interactive = False
        
        # Reset window flags to non-interactive
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowDoesNotAcceptFocus
        )
        
        # Load and set the icon
        if icon_path.exists():
            pixmap = QPixmap(str(icon_path))
            # Scale to reasonable size while maintaining aspect ratio
            scaled_pixmap = pixmap.scaled(
                200, 200,
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
        
        # Reset opacity effects
        self.icon_opacity.setOpacity(0.0)
        self.buttons_opacity.setOpacity(0.0)
        
        # Show window
        self.show()
        self.raise_()
        
        # Start animations
        self.icon_fade_anim.start()
        self.bg_delay_timer.start(self.BACKGROUND_FADE_DELAY)
    
    def _start_background_fade(self):
        """Start the background fade animation."""
        self.bg_target_opacity = 0.7
        # Calculate step size for smooth animation
        steps = self.BACKGROUND_FADE_DURATION / 16
        self.bg_fade_step = self.bg_target_opacity / steps
        self.bg_fade_timer.start()
    
    def _animate_background(self):
        """Animate the background opacity."""
        self.background_opacity += self.bg_fade_step
        
        if self.background_opacity >= self.bg_target_opacity:
            self.background_opacity = self.bg_target_opacity
            self.bg_fade_timer.stop()
            
            # Show buttons after background is visible
            self.buttons_delay_timer.start(200)
        
        self.update()
    
    def _show_buttons(self):
        """Show the buttons and make window interactive."""
        self.is_interactive = True
        
        # Update window flags to accept focus and clicks
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.show()
        self.raise_()
        
        # Fade in buttons
        self.buttons_fade_anim.start()
    
    def _on_complete(self):
        """Handle complete button click."""
        self._dismiss()
        self.completed.emit(self.reminder_name)
    
    def _on_snooze(self):
        """Handle snooze button click."""
        self._dismiss()
        self.snoozed.emit(self.reminder_name, self.snooze_duration)
    
    def _dismiss(self):
        """Dismiss the overlay with fade-out animation."""
        # Quick fade out
        self.bg_target_opacity = 0.0
        self.bg_fade_step = -0.05
        self.bg_fade_timer.start()
        
        # Fade out icon and buttons
        fade_out_icon = QPropertyAnimation(self.icon_opacity, b"opacity")
        fade_out_icon.setDuration(self.DISMISS_FADE_DURATION)
        fade_out_icon.setEndValue(0.0)
        fade_out_icon.start()
        
        fade_out_buttons = QPropertyAnimation(self.buttons_opacity, b"opacity")
        fade_out_buttons.setDuration(self.DISMISS_FADE_DURATION)
        fade_out_buttons.setEndValue(0.0)
        fade_out_buttons.start()
        
        # Hide after animation
        QTimer.singleShot(self.DISMISS_FADE_DURATION + 100, self.hide)
    
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
