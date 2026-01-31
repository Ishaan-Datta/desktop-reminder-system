"""Main application for the reminder system."""

import sys
import signal
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QAction
from PyQt6.QtCore import QObject, pyqtSignal, QThread, QTimer

from .config import ConfigManager, ReminderConfig
from .scheduler import ReminderScheduler
from .overlay import ReminderOverlay


class ReminderTrigger(QObject):
    """Bridge between scheduler thread and Qt main thread."""
    triggered = pyqtSignal(str)


class ReminderApp(QObject):
    """
    Main application class that coordinates the reminder system.
    
    Manages:
    - Configuration loading
    - Scheduler lifecycle
    - Overlay display
    - System tray icon
    """
    
    def __init__(self, config_dir: Optional[Path] = None, enable_tray: bool = True):
        """
        Initialize the ReminderApp.
        
        Args:
            config_dir: Optional custom config directory path
            enable_tray: Whether to enable the system tray icon
        """
        super().__init__()
        
        self.config_manager = ConfigManager(config_dir)
        self.scheduler = ReminderScheduler()
        self.overlay: Optional[ReminderOverlay] = None
        self.tray_icon: Optional[QSystemTrayIcon] = None
        self._enable_tray = enable_tray
        
        # Bridge for thread-safe Qt signal emission
        self.trigger = ReminderTrigger()
        self.trigger.triggered.connect(self._on_reminder_triggered)
        
        # Current active reminder
        self.active_reminder: Optional[ReminderConfig] = None
        
        # Queue for reminders that come while another is showing
        self.reminder_queue: list = []
    
    def initialize(self, skip_scheduler: bool = False) -> bool:
        """
        Initialize the application.
        
        Args:
            skip_scheduler: If True, don't schedule reminders (useful for testing)
            
        Returns:
            True on success
        """
        try:
            # Load configuration
            reminders = self.config_manager.load_config()
            
            if not reminders:
                print("No reminders configured. Please add reminders to the config file.")
                return False
            
            print(f"Loaded {len(reminders)} reminders:")
            for name, config in reminders.items():
                print(f"  - {name}: {config.schedule}")
            
            # Create overlay with general config settings
            self.overlay = ReminderOverlay(general_config=self.config_manager.general)
            self.overlay.completed.connect(self._on_reminder_completed)
            self.overlay.snoozed.connect(self._on_reminder_snoozed)
            
            # Setup system tray (optional)
            if self._enable_tray:
                self._setup_tray()
            
            # Schedule all reminders (optional)
            if not skip_scheduler:
                for name, config in reminders.items():
                    self.scheduler.add_reminder(
                        name=name,
                        cron_expression=config.schedule,
                        callback=self._trigger_reminder_threadsafe
                    )
            
            return True
            
        except FileNotFoundError as e:
            print(f"Error: {e}")
            print("\nCreating example configuration...")
            self.config_manager.create_example_config()
            print(f"Please edit {self.config_manager.config_file} and restart.")
            return False
        except Exception as e:
            print(f"Error initializing application: {e}")
            return False
    
    def initialize_minimal(self, reminders: dict) -> bool:
        """
        Initialize with pre-loaded reminder configs (for testing).
        
        Args:
            reminders: Dictionary of name -> ReminderConfig
            
        Returns:
            True on success
        """
        self.config_manager.reminders = reminders
        
        # Create overlay
        self.overlay = ReminderOverlay()
        self.overlay.completed.connect(self._on_reminder_completed)
        self.overlay.snoozed.connect(self._on_reminder_snoozed)
        
        return True
    
    def trigger_reminder(self, name: str) -> bool:
        """
        Manually trigger a reminder by name.
        
        Args:
            name: The name of the reminder to trigger
            
        Returns:
            True if the reminder was found and triggered
        """
        if name not in self.config_manager.reminders:
            print(f"Unknown reminder: {name}")
            return False
        
        config = self.config_manager.reminders[name]
        self._show_reminder(config)
        return True
    
    def trigger_reminder_config(self, config: ReminderConfig):
        """
        Trigger a reminder with a given config directly.
        
        Args:
            config: The ReminderConfig to display
        """
        self._show_reminder(config)
    
    def _setup_tray(self):
        """Set up the system tray icon."""
        # Create a simple icon
        pixmap = QPixmap(32, 32)
        pixmap.fill(QColor("transparent"))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor("#4CAF50"))
        painter.setPen(QColor("#388E3C"))
        painter.drawEllipse(2, 2, 28, 28)
        painter.setPen(QColor("white"))
        font = painter.font()
        font.setPointSize(16)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), 0x0084, "⏰")  # AlignCenter
        painter.end()
        
        icon = QIcon(pixmap)
        
        self.tray_icon = QSystemTrayIcon(icon)
        self.tray_icon.setToolTip("Reminder System")
        
        # Create tray menu
        menu = QMenu()
        
        status_action = QAction("Reminder System", menu)
        status_action.setEnabled(False)
        menu.addAction(status_action)
        
        menu.addSeparator()
        
        # Show status action
        show_status = QAction("Show Status", menu)
        show_status.triggered.connect(self._show_status)
        menu.addAction(show_status)
        
        # Test reminder action
        test_action = QAction("Test Reminder", menu)
        test_action.triggered.connect(self._test_reminder)
        menu.addAction(test_action)
        
        menu.addSeparator()
        
        # Quit action
        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()
    
    def _trigger_reminder_threadsafe(self, name: str):
        """Thread-safe method to trigger a reminder."""
        # Emit signal to main thread
        self.trigger.triggered.emit(name)
    
    def _on_reminder_triggered(self, name: str):
        """Handle a reminder being triggered (main thread)."""
        print(f"Reminder triggered: {name}")
        
        if name not in self.config_manager.reminders:
            print(f"Warning: Unknown reminder '{name}'")
            return
        
        config = self.config_manager.reminders[name]
        
        # If overlay is already showing, queue this reminder
        if self.active_reminder is not None:
            print(f"Queueing reminder: {name}")
            self.reminder_queue.append(config)
            return
        
        self._show_reminder(config)
    
    def _show_reminder(self, config: ReminderConfig):
        """Show the overlay for a reminder."""
        self.active_reminder = config
        self.overlay.show_reminder(
            name=config.name,
            icon_path=config.icon_path,
            snooze_duration=config.snooze_duration,
            text=config.text
        )
    
    def _on_reminder_completed(self, name: str):
        """Handle reminder being marked as complete."""
        print(f"Reminder completed: {name}")
        self.scheduler.complete_reminder(name)
        self.active_reminder = None
        self._process_queue()
    
    def _on_reminder_snoozed(self, name: str, duration: int):
        """Handle reminder being snoozed."""
        print(f"Reminder snoozed: {name} for {duration}s")
        self.scheduler.snooze_reminder(name, duration)
        self.active_reminder = None
        self._process_queue()
    
    def _process_queue(self):
        """Process queued reminders."""
        if self.reminder_queue:
            next_reminder = self.reminder_queue.pop(0)
            # Small delay before showing next
            QTimer.singleShot(500, lambda: self._show_reminder(next_reminder))
    
    def _show_status(self):
        """Show the status of all reminders."""
        status = self.scheduler.get_status()
        print("\n=== Reminder Status ===")
        for name, info in status.items():
            print(f"\n{name}:")
            print(f"  Next run: {info['effective_next']}")
            if info['snoozed_until']:
                print(f"  Snoozed until: {info['snoozed_until']}")
        print("=" * 24 + "\n")
    
    def _test_reminder(self):
        """Trigger a test reminder."""
        if self.config_manager.reminders:
            # Get first reminder for testing
            name = list(self.config_manager.reminders.keys())[0]
            config = self.config_manager.reminders[name]
            print(f"Testing reminder: {name}")
            self._show_reminder(config)
        else:
            print("No reminders configured")
    
    def _quit(self):
        """Quit the application."""
        print("Shutting down...")
        self.scheduler.stop()
        QApplication.quit()
    
    def run(self):
        """Start the application."""
        self.scheduler.start()
        print("\nReminder system is running. Use the system tray icon to access options.")
        print("Press Ctrl+C to quit.\n")


def main():
    """Main entry point."""
    # Create Qt application
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # Keep running with just tray icon
    app.setApplicationName("Reminder System")
    
    # Create and initialize reminder app
    reminder_app = ReminderApp()
    
    if not reminder_app.initialize():
        sys.exit(1)
    
    # Handle SIGINT (Ctrl+C)
    signal.signal(signal.SIGINT, lambda *args: reminder_app._quit())
    
    # Timer to allow signal handling
    timer = QTimer()
    timer.timeout.connect(lambda: None)
    timer.start(500)
    
    # Start the application
    reminder_app.run()
    
    # Run Qt event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
