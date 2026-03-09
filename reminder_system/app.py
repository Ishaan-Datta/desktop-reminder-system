"""Main application for the reminder system."""

import sys
import signal
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QAction
from PyQt6.QtCore import QObject, pyqtSignal, QTimer, QFileSystemWatcher

from .config import ConfigManager, ReminderConfig
from .scheduler import ReminderScheduler
from .overlay import ReminderOverlay
from .queue import PersistentReminderQueue
from .status_notifier import StatusNotifierBackend
from .state import PersistentState
from .tray_window import TrayWindow


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
        self._status_notifier: Optional[StatusNotifierBackend] = None
        self._enable_tray = enable_tray
        
        # Bridge for thread-safe Qt signal emission
        self.trigger = ReminderTrigger()
        self.trigger.triggered.connect(self._on_reminder_triggered)
        
        # Current active reminder
        self.active_reminder: Optional[ReminderConfig] = None
        self._active_from_queue: bool = False  # Whether the current overlay is a queued reminder
        
        # Persistent queue for reminders (initialized in initialize())
        self._queue: Optional[PersistentReminderQueue] = None
        
        # Persistent state store (initialized in initialize())
        self._state: Optional[PersistentState] = None
        
        # Lock file state tracking (glob-scanned from lock_dir)
        self._lock_was_active: bool = False
        self._snooze_lock_names: list[str] = []  # prefixes from *_snooze.lock files
        self._cancel_lock_names: list[str] = []  # prefixes from *_cancel.lock files
        
        # Tray panel window (initialized in _setup_tray)
        self._tray_window: Optional[TrayWindow] = None
        
        # Stagger state: prevents showing next queued reminder too quickly
        self._stagger_pending: bool = False
        
        # Resume state: delay before showing the first queued reminder
        self._resume_pending: bool = False
        
        # Queue polling timer (initialized in initialize())
        self._queue_poll_timer: Optional[QTimer] = None
        
        # Config file watcher for hot reload
        self._config_watcher: Optional[QFileSystemWatcher] = None
        self._reload_timer: Optional[QTimer] = None
        
        # Work session timer
        self._work_session_timer: Optional[QTimer] = None
        
        # Track last tray icon color to avoid unnecessary repaints
        self._last_tray_color: Optional[str] = None

    def _apply_general_overrides(self, general_overrides: Optional[dict[str, Any]]) -> None:
        """Apply caller-provided general config overrides before startup."""
        if not general_overrides:
            return

        for key, value in general_overrides.items():
            if not hasattr(self.config_manager.general, key):
                raise AttributeError(f"Unknown general config override: {key}")
            setattr(self.config_manager.general, key, value)

    def initialize(
        self,
        skip_scheduler: bool = False,
        general_overrides: Optional[dict[str, Any]] = None,
    ) -> bool:
        """
        Initialize the application.
        
        Args:
            skip_scheduler: If True, don't schedule reminders (useful for testing)
            general_overrides: Optional overrides for loaded general config
            
        Returns:
            True on success
        """
        try:
            # Load configuration
            reminders = self.config_manager.load_config()
            self._apply_general_overrides(general_overrides)
            
            if not reminders:
                print("No reminders configured. Please add reminders to the config file.")
                return False
            
            print(f"Loaded {len(reminders)} reminders:")
            for name, config in reminders.items():
                schedules = ', '.join(config.schedule)
                print(f"  - {name}: [{schedules}]")
            
            # Create overlay with general config settings
            self.overlay = ReminderOverlay(general_config=self.config_manager.general)
            self.overlay.completed.connect(self._on_reminder_completed)
            self.overlay.snoozed.connect(self._on_reminder_snoozed)
            
            # Initialize persistent queue (survives restarts)
            queue_file = self.config_manager.config_dir / "queue.json"
            self._queue = PersistentReminderQueue(queue_file)
            
            # Initialize persistent state store (survives restarts)
            state_file = self.config_manager.config_dir / "state.json"
            self._state = PersistentState(state_file)

            # Prime work-session and lock state before creating the tray UI so
            # the first painted icon/panel contents already match reality.
            self._check_work_session()
            cancel_active, snooze_active = self._scan_lock_files()
            if cancel_active:
                self._clear_queue_for_cancel_lock("startup")
            self._lock_was_active = cancel_active or snooze_active
            
            # Set up periodic timer to check lock files and process queue
            self._queue_poll_timer = QTimer()
            self._queue_poll_timer.setInterval(1000)  # Check every second
            self._queue_poll_timer.timeout.connect(self._check_queue_and_locks)
            self._queue_poll_timer.start()
            
            # Set up config file watcher for hot reload
            self._setup_config_watcher()
            
            # Set up work session timer (checks once per minute)
            self._work_session_timer = QTimer()
            self._work_session_timer.setInterval(15000)  # 15 seconds
            self._work_session_timer.timeout.connect(self._check_work_session)
            self._work_session_timer.start()
            
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
        """Set up the system tray icon and panel window."""
        # Panel window (shown on left-click)
        self._tray_window = TrayWindow(self)
        self._tray_window.refresh_contents()
        
        # Right-click context menu
        menu = QMenu()
        
        show_status = QAction("Print Status", menu)
        show_status.triggered.connect(self._show_status)
        menu.addAction(show_status)
        
        menu.addSeparator()
        
        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)

        desired = self._get_tray_icon_state()
        fill, border = self._get_tray_icon_colours(desired)
        self._last_tray_color = desired

        if StatusNotifierBackend.is_supported():
            self._status_notifier = StatusNotifierBackend(
                icon_factory=self._make_tray_icon,
                on_activate=self._on_status_notifier_activate,
                on_context_menu=menu.popup,
                parent=self,
            )
            self._status_notifier.start()
            self._status_notifier.set_icon_state(desired, fill, border)
            self._status_notifier.set_status("Active")
            return

        self.tray_icon = QSystemTrayIcon(self._make_tray_icon(fill, border))
        self.tray_icon.setToolTip("Reminder System")
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()
    
    @staticmethod
    def _make_tray_icon(fill: str, border: str) -> QIcon:
        """Create a simple circular tray icon with the given colours."""
        pixmap = QPixmap(32, 32)
        pixmap.fill(QColor("transparent"))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(fill))
        painter.setPen(QColor(border))
        painter.drawEllipse(2, 2, 28, 28)
        painter.setPen(QColor("white"))
        font = painter.font()
        font.setPointSize(16)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), 0x0084, "⏰")  # AlignCenter
        painter.end()
        return QIcon(pixmap)

    @staticmethod
    def _get_tray_icon_colours(state: str) -> tuple[str, str]:
        """Return tray fill/border colours for a logical icon state."""
        colours = {
            "green": ("#4CAF50", "#388E3C"),
            "grey": ("#9E9E9E", "#757575"),
            "yellow": ("#FFC107", "#FFA000"),
        }
        return colours[state]

    def _get_tray_icon_state(self) -> str:
        """Return the current logical tray state from scanned locks."""
        if self._cancel_lock_names:
            return "grey"
        if self._snooze_lock_names:
            return "yellow"
        return "green"

    def _clear_queue_for_cancel_lock(self, reason: str) -> None:
        """Clear queued reminders because cancel locks suppress them."""
        if self._queue is None or self._queue.is_empty():
            return

        count = self._queue.size()
        self._queue.clear()
        print(f"Cancel lock active ({reason}) – cleared {count} queued reminder(s)")
    
    def _update_tray_icon_color(self):
        """Set the tray icon colour based on the current lock state.
        
        - Green  : no cancel or snooze locks active (normal)
        - Grey   : at least one cancel lock active
        - Yellow : at least one snooze lock active (but no cancel lock)
        """
        if self.tray_icon is None and self._status_notifier is None:
            return

        desired = self._get_tray_icon_state()
        
        if desired == self._last_tray_color:
            return  # No change needed
        
        self._last_tray_color = desired

        fill, border = self._get_tray_icon_colours(desired)
        if self._status_notifier is not None:
            self._status_notifier.set_icon_state(desired, fill, border)
            self._status_notifier.set_status("Active")
        elif self.tray_icon is not None:
            self.tray_icon.setIcon(self._make_tray_icon(fill, border))
    
    def _on_tray_activated(self, reason):
        """Toggle tray panel on left-click."""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._toggle_tray_window_from_activation()

    def _toggle_tray_window_from_activation(self):
        """Open or close the tray window after a tray activation."""
        if self._tray_window is None or self.tray_icon is None:
            return
        self._tray_window.toggle_visibility(self.tray_icon.geometry())

    def _on_status_notifier_activate(self, tray_geometry):
        """Toggle the tray panel using the freshest Wayland activation token."""
        if self._tray_window is None:
            return

        activation_token = ""
        if self._status_notifier is not None:
            activation_token = self._status_notifier.take_activation_token()

        self._tray_window.toggle_visibility(tray_geometry, activation_token)
    
    def _trigger_reminder_threadsafe(self, name: str):
        """Thread-safe method to trigger a reminder."""
        # Emit signal to main thread
        self.trigger.triggered.emit(name)
    
    def _scan_lock_files(self) -> tuple[bool, bool]:
        """Scan lock_dir for \*_cancel.lock and \*_snooze.lock files.
        
        Updates self._cancel_lock_names and self._snooze_lock_names with
        the prefixes scraped from each filename (the part before the
        ``_cancel.lock`` / ``_snooze.lock`` suffix).
        
        Returns:
            (cancel_active, snooze_active) booleans.
        """
        lock_dir = Path(self.config_manager.general.lock_dir)
        cancel_names: list[str] = []
        snooze_names: list[str] = []
        
        if lock_dir.is_dir():
            for f in lock_dir.glob("*_cancel.lock"):
                if f.is_file():
                    prefix = f.name[: -len("_cancel.lock")]
                    cancel_names.append(prefix)
            for f in lock_dir.glob("*_snooze.lock"):
                if f.is_file():
                    prefix = f.name[: -len("_snooze.lock")]
                    snooze_names.append(prefix)
        
        self._cancel_lock_names = cancel_names
        self._snooze_lock_names = snooze_names
        return bool(cancel_names), bool(snooze_names)
    
    def _check_work_session(self):
        """Manage the work-session cancel lock based on the current time.
        
        When ``work_session_enable`` is True and the operating mode
        (from persistent state) is ``"automatic"``:
        - During the work session window → delete ``work-session_cancel.lock``
        - Outside the work session window → create ``work-session_cancel.lock``
        
        When the operating mode is ``"manual"``, this method does nothing
        (the lock is managed by the tray UI toggle instead).
        
        The lock file lives in ``lock_dir`` and is named
        ``work-session_cancel.lock`` so the existing glob scanner picks it up.
        """
        general = self.config_manager.general
        lock_dir = Path(general.lock_dir)
        lock_file = lock_dir / "work-session_cancel.lock"
        
        operating_mode = (
            self._state.get("work_session_operating_mode", "automatic")
            if self._state else "automatic"
        )
        
        if not general.work_session_enable or operating_mode != "automatic":
            # Feature disabled or manual mode – automatic management stops.
            # In manual mode the tray UI manages the lock file directly,
            # so we must NOT touch it here.
            if not general.work_session_enable and lock_file.exists():
                lock_file.unlink()
                print("Work session: disabled – removed cancel lock")
            return
        
        # Parse HH:MM start / end
        try:
            start_h, start_m = (int(x) for x in general.work_session_start.split(":"))
            end_h, end_m = (int(x) for x in general.work_session_end.split(":"))
        except (ValueError, AttributeError):
            print(f"Work session: bad time format "
                  f"(start={general.work_session_start!r}, end={general.work_session_end!r})")
            return
        
        now = datetime.now()
        current_minutes = now.hour * 60 + now.minute
        start_minutes = start_h * 60 + start_m
        end_minutes = end_h * 60 + end_m
        
        # Support overnight ranges (e.g. 22:00 – 06:00)
        if start_minutes <= end_minutes:
            in_session = start_minutes <= current_minutes < end_minutes
        else:
            in_session = current_minutes >= start_minutes or current_minutes < end_minutes
        
        if in_session:
            # Inside work session → ensure lock is removed
            if lock_file.exists():
                lock_file.unlink()
                print("Work session: now inside schedule – removed cancel lock")
        else:
            # Outside work session → ensure lock exists
            if not lock_file.exists():
                lock_dir.mkdir(parents=True, exist_ok=True)
                lock_file.touch()
                print("Work session: outside schedule – created cancel lock")
                self._clear_queue_for_cancel_lock("work session")
    
    def _is_cancel_locked(self) -> bool:
        """Convenience: True when any \*_cancel.lock file exists."""
        cancel, _ = self._scan_lock_files()
        return cancel
    
    def _is_snooze_locked(self) -> bool:
        """Convenience: True when any \*_snooze.lock file exists."""
        _, snooze = self._scan_lock_files()
        return snooze
    
    def _on_reminder_triggered(self, name: str):
        """Handle a reminder being triggered (main thread)."""
        print(f"Reminder triggered: {name}")
        
        if name not in self.config_manager.reminders:
            print(f"Warning: Unknown reminder '{name}'")
            return
        
        # Scan lock files once (cancel takes precedence over snooze)
        cancel_active, snooze_active = self._scan_lock_files()
        
        if cancel_active:
            print(f"Cancel lock active, skipping reminder: {name}")
            self.scheduler.complete_reminder(name)
            return
        
        if snooze_active:
            print(f"Snooze lock active, queueing reminder: {name}")
            self._queue.push_back(name)
            self._lock_was_active = True
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
        - Scanning lock_dir for *_snooze.lock / *_cancel.lock files
        - Holding the queue while any lock is active (cancel takes precedence)
        - Detecting when all locks are removed to resume queue processing
        - Respecting stagger / resume delays
        """
        if self._queue is None:
            return
        
        cancel_active, snooze_active = self._scan_lock_files()
        any_lock = cancel_active or snooze_active

        if cancel_active:
            self._clear_queue_for_cancel_lock("lock scan")
        
        # Update tray icon colour to reflect current lock state
        self._update_tray_icon_color()
        
        # While any lock is active, hold the queue
        if any_lock:
            self._lock_was_active = True
            return
        
        # Locks just removed → start resume delay
        if self._lock_was_active and not any_lock:
            self._lock_was_active = False
            if not self._queue.is_empty():
                resume_s = self.config_manager.general.resume_interval
                print(f"Lock files removed, resuming queue in {resume_s}s")
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
        
        # Safety: re-check locks (could have appeared since last tick)
        cancel_active, snooze_active = self._scan_lock_files()
        if cancel_active or snooze_active:
            return
        
        name = self._queue.pop()
        if name is None:
            return
        
        # Check if the reminder still exists in config
        if name not in self.config_manager.reminders:
            print(f"Queued reminder '{name}' no longer in config, skipping")
            self._process_next_queued()  # Try next
            return
        
        print(f"Showing queued reminder: {name}")
        config = self.config_manager.reminders[name]
        self._active_from_queue = True
        self._show_reminder(config)
    
    # ── Config hot reload ────────────────────────────────────────
    
    def _setup_config_watcher(self):
        """Set up a file watcher on config.toml for hot reloading."""
        self._config_watcher = QFileSystemWatcher()
        config_path = str(self.config_manager.config_file)
        self._config_watcher.addPath(config_path)
        self._config_watcher.fileChanged.connect(self._on_config_file_changed)
        
        # Debounce timer to handle editors that delete+recreate files
        self._reload_timer = QTimer()
        self._reload_timer.setSingleShot(True)
        self._reload_timer.setInterval(500)  # 500ms debounce
        self._reload_timer.timeout.connect(self._reload_config)
        
        print(f"Watching config file for changes: {config_path}")
    
    def _on_config_file_changed(self, path: str):
        """Handle config file change notification (debounced)."""
        print(f"Config file change detected: {path}")
        # Restart debounce timer (handles rapid successive writes)
        self._reload_timer.start()
    
    def _reload_config(self):
        """Reload configuration and update scheduler for non-snoozed reminders."""
        config_path = str(self.config_manager.config_file)
        
        try:
            new_reminders = self.config_manager.load_config()
        except Exception as e:
            print(f"Error reloading config: {e}")
            # Re-add path in case it was removed (editor atomic save)
            self._config_watcher.addPath(config_path)
            return
        
        # Re-add the file to the watcher (some editors delete+recreate)
        if config_path not in self._config_watcher.files():
            self._config_watcher.addPath(config_path)
        
        # Determine which reminders are currently snoozed
        snoozed_names = self.scheduler.get_snoozed_names()
        
        old_names = set(self.scheduler.reminders.keys())
        new_names = set(new_reminders.keys())
        
        # Remove reminders that are no longer in config
        for removed_name in old_names - new_names:
            print(f"  Hot reload: removing '{removed_name}'")
            self.scheduler.remove_reminder(removed_name)
            self._queue.remove(removed_name)
        
        # Add or update reminders (skip snoozed ones)
        for name, config in new_reminders.items():
            if name in snoozed_names:
                print(f"  Hot reload: skipping snoozed '{name}'")
                continue
            
            # Remove old entry (if any) and re-add with new schedule
            self.scheduler.remove_reminder(name)
            self.scheduler.add_reminder(
                name=name,
                cron_expression=config.schedule,
                callback=self._trigger_reminder_threadsafe
            )
        
        print(f"Config reloaded: {len(new_reminders)} reminders "
              f"({len(snoozed_names)} snoozed, kept unchanged)")
    
    # ── Tray and status ──────────────────────────────────────────
    
    def _show_status(self):
        """Show the status of all reminders."""
        status = self.scheduler.get_status()
        print("\n=== Reminder Status ===")
        for name, info in status.items():
            print(f"\n{name}:")
            schedules = ', '.join(info['schedules'])
            print(f"  Schedules: [{schedules}]")
            print(f"  Next run: {info['effective_next']}")
            if info['snoozed_until']:
                print(f"  Snoozed until: {info['snoozed_until']}")
        # Show queue and lock file status
        if self._queue:
            queued = self._queue.get_all()
            print(f"\nQueued reminders: {queued if queued else '(none)'}")
        print(f"Lock dir: {self.config_manager.general.lock_dir}")
        print(f"Cancel locks: {self._cancel_lock_names if self._cancel_lock_names else 'none'}")
        print(f"Snooze locks: {self._snooze_lock_names if self._snooze_lock_names else 'none'}")
        general = self.config_manager.general
        ws_status = "enabled" if general.work_session_enable else "disabled"
        ws_mode = self._state.get("work_session_operating_mode", "automatic") if self._state else "automatic"
        print(f"Work session: {ws_status} ({general.work_session_start}-{general.work_session_end}, mode={ws_mode})")
        print("=" * 24 + "\n")
    
    def _quit(self):
        """Quit the application."""
        print("Shutting down...")
        if self._reload_timer:
            self._reload_timer.stop()
        if self._config_watcher:
            self._config_watcher.fileChanged.disconnect(self._on_config_file_changed)
        if self._queue_poll_timer:
            self._queue_poll_timer.stop()
        if self._work_session_timer:
            self._work_session_timer.stop()
        if self._status_notifier:
            self._status_notifier.stop()
        if self._tray_window:
            self._tray_window.close()
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
