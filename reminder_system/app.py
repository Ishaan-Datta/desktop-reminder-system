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
from .queue import PersistentReminderQueue


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
        self._active_from_queue: bool = False  # Whether the current overlay is a queued reminder
        
        # Persistent queue for reminders (initialized in initialize())
        self._queue: Optional[PersistentReminderQueue] = None
        
        # Lock file state tracking
        self._snooze_lock_was_active: bool = False
        
        # Stagger state: prevents showing next queued reminder too quickly
        self._stagger_pending: bool = False
        
        # Resume state: delay before showing the first queued reminder
        self._resume_pending: bool = False
        
        # Queue polling timer (initialized in initialize())
        self._queue_poll_timer: Optional[QTimer] = None
    
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
            
            # Initialize persistent queue (survives restarts)
            queue_file = self.config_manager.config_dir / "queue.json"
            self._queue = PersistentReminderQueue(queue_file)
            
            # Set up periodic timer to check lock files and process queue
            self._queue_poll_timer = QTimer()
            self._queue_poll_timer.setInterval(1000)  # Check every second
            self._queue_poll_timer.timeout.connect(self._check_queue_and_locks)
            self._queue_poll_timer.start()
            
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
        
        # Initialize persistent queue for testing (uses temp directory)
        import tempfile
        queue_file = Path(tempfile.mkdtemp()) / "queue.json"
        self._queue = PersistentReminderQueue(queue_file)
        
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
    
    def _is_snooze_locked(self) -> bool:
        """Check if the snooze lock file is present."""
        return Path(self.config_manager.general.snooze_lock_file).exists()
    
    def _is_cancel_locked(self) -> bool:
        """Check if the cancel lock file is present."""
        return Path(self.config_manager.general.cancel_lock_file).exists()
    
    def _on_reminder_triggered(self, name: str):
        """Handle a reminder being triggered (main thread)."""
        print(f"Reminder triggered: {name}")
        
        if name not in self.config_manager.reminders:
            print(f"Warning: Unknown reminder '{name}'")
            return
        
        # Check cancel lock — skip entirely
        if self._is_cancel_locked():
            print(f"Cancel lock active, skipping reminder: {name}")
            self.scheduler.complete_reminder(name)
            return
        
        # Check snooze lock — queue for later
        if self._is_snooze_locked():
            print(f"Snooze lock active, queueing reminder: {name}")
            self._queue.push_back(name)
            self._snooze_lock_was_active = True
            return
        
        # If overlay is already showing or stagger delay is pending, queue
        if self.active_reminder is not None or self._stagger_pending:
            print(f"Overlay active or stagger pending, queueing reminder: {name}")
            self._queue.push_back(name)
            return
        
        config = self.config_manager.reminders[name]
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
        was_from_queue = self._active_from_queue
        self.active_reminder = None
        self._active_from_queue = False
        self._start_queue_delay(was_from_queue)
    
    def _on_reminder_snoozed(self, name: str, duration: int):
        """Handle reminder being snoozed."""
        print(f"Reminder snoozed: {name} for {duration}s")
        self.scheduler.snooze_reminder(name, duration)
        was_from_queue = self._active_from_queue
        self.active_reminder = None
        self._active_from_queue = False
        self._start_queue_delay(was_from_queue)
    
    def _start_queue_delay(self, previous_was_queued: bool):
        """Start the appropriate delay before showing the next queued reminder.
        
        Uses resume_interval for the first queued item (previous reminder was
        live-triggered), stagger_interval for subsequent queue items.
        """
        if self._queue is None or self._queue.is_empty():
            return
        if previous_was_queued:
            delay_s = self.config_manager.general.stagger_interval
            label = "Stagger"
            self._stagger_pending = True
            QTimer.singleShot(delay_s * 1000, self._end_stagger_delay)
        else:
            delay_s = self.config_manager.general.resume_interval
            label = "Resume"
            self._resume_pending = True
            QTimer.singleShot(delay_s * 1000, self._end_resume_delay)
        print(f"{label} delay: waiting {delay_s}s before next reminder")
    
    def _end_stagger_delay(self):
        """End the stagger delay, allowing queue processing to resume."""
        self._stagger_pending = False
    
    def _end_resume_delay(self):
        """End the resume delay, allowing the first queued reminder to show."""
        self._resume_pending = False
        print("Resume delay ended, processing queue")
    
    def _check_queue_and_locks(self):
        """
        Periodic check for lock file state changes and queue processing.
        
        Called every second by _queue_poll_timer.  Handles:
        - Detecting when snooze lock file is removed to resume queue processing
        - Processing queued reminders when no overlay is active
        - Respecting cancel lock during queue processing
        """
        if self._queue is None:
            return
        
        snooze_active = self._is_snooze_locked()
        
        # Track snooze lock transitions
        if snooze_active:
            self._snooze_lock_was_active = True
            return  # Don't process queue while snooze lock is active
        
        if self._snooze_lock_was_active and not snooze_active:
            self._snooze_lock_was_active = False
            if not self._queue.is_empty():
                resume_s = self.config_manager.general.resume_interval
                print(f"Snooze lock removed, resuming queue in {resume_s}s")
                self._resume_pending = True
                QTimer.singleShot(resume_s * 1000, self._end_resume_delay)
            return  # Wait for the resume timer to fire
        
        # Don't process if overlay is active or any delay is pending
        if self.active_reminder is not None or self._stagger_pending or self._resume_pending:
            return
        
        # Process next item from queue
        self._process_next_queued()
    
    def _process_next_queued(self):
        """Pop and display the next reminder from the persistent queue."""
        if self._queue is None or self._queue.is_empty():
            return
        
        name = self._queue.pop()
        if name is None:
            return
        
        # Check if the reminder still exists in config
        if name not in self.config_manager.reminders:
            print(f"Queued reminder '{name}' no longer in config, skipping")
            self._process_next_queued()  # Try next
            return
        
        # Check cancel lock — skip queued item too
        if self._is_cancel_locked():
            print(f"Cancel lock active, skipping queued reminder: {name}")
            self.scheduler.complete_reminder(name)
            self._process_next_queued()  # Try next
            return
        
        print(f"Showing queued reminder: {name}")
        config = self.config_manager.reminders[name]
        self._active_from_queue = True
        self._show_reminder(config)
    
    def _show_status(self):
        """Show the status of all reminders."""
        status = self.scheduler.get_status()
        print("\n=== Reminder Status ===")
        for name, info in status.items():
            print(f"\n{name}:")
            print(f"  Next run: {info['effective_next']}")
            if info['snoozed_until']:
                print(f"  Snoozed until: {info['snoozed_until']}")
        # Show queue and lock file status
        if self._queue:
            queued = self._queue.get_all()
            print(f"\nQueued reminders: {queued if queued else '(none)'}")
        print(f"Snooze lock: {'ACTIVE' if self._is_snooze_locked() else 'inactive'}")
        print(f"Cancel lock: {'ACTIVE' if self._is_cancel_locked() else 'inactive'}")
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
        if self._queue_poll_timer:
            self._queue_poll_timer.stop()
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
