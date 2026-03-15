"""Integration tests for reminder app queue/cancel-lock behaviour."""

import os
import shutil
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from reminder_system.app import ReminderApp
from reminder_system.config import ReminderConfig
from reminder_system.tray_window import TrayWindow


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def qt_app():
    """Provide a QApplication instance for Qt-based app tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """Create a temporary config directory based on the test fixtures."""
    shutil.copy(FIXTURES_DIR / "config.toml", tmp_path / "config.toml")
    return tmp_path


def _cleanup_app(reminder_app: ReminderApp):
    """Stop timers/watchers created during app initialization."""
    if reminder_app._reload_timer:
        reminder_app._reload_timer.stop()
    if reminder_app._config_watcher:
        try:
            reminder_app._config_watcher.fileChanged.disconnect(
                reminder_app._on_config_file_changed
            )
        except TypeError:
            pass
    if reminder_app._queue_poll_timer:
        reminder_app._queue_poll_timer.stop()
    if reminder_app._work_session_timer:
        reminder_app._work_session_timer.stop()
    reminder_app.scheduler.stop()
    if reminder_app.overlay is not None:
        reminder_app.overlay.close()
    if reminder_app._tray_window is not None:
        reminder_app._tray_window.close()


def _write_config(config_dir: Path, content: str) -> None:
    """Write TOML content into the temporary config directory."""
    (config_dir / "config.toml").write_text(content.strip() + "\n", encoding="utf-8")


def test_cancel_lock_scan_clears_queue(qt_app, config_dir: Path):
    """Any detected cancel lock should empty the persisted queue."""
    lock_dir = config_dir / "locks"
    reminder_app = ReminderApp(config_dir=config_dir, enable_tray=False)

    assert reminder_app.initialize(
        skip_scheduler=True,
        general_overrides={
            "lock_dir": str(lock_dir),
            "work_session_enable": False,
        },
    )

    try:
        assert reminder_app._queue is not None
        reminder_app._queue.push_back("first")
        reminder_app._queue.push_back("second")
        assert reminder_app._queue.get_all() == ["first", "second"]

        lock_dir.mkdir(parents=True, exist_ok=True)
        (lock_dir / "external_cancel.lock").touch()

        reminder_app._check_queue_and_locks()

        assert reminder_app._queue.get_all() == []
    finally:
        _cleanup_app(reminder_app)


def test_trigger_reminder_queues_when_snooze_lock_is_active(qt_app, config_dir: Path):
    """Public named triggers should respect snooze locks and queue the reminder."""
    lock_dir = config_dir / "locks"
    reminder_app = ReminderApp(config_dir=config_dir, enable_tray=False)

    assert reminder_app.initialize(
        skip_scheduler=True,
        general_overrides={
            "lock_dir": str(lock_dir),
            "work_session_enable": False,
        },
    )

    try:
        lock_dir.mkdir(parents=True, exist_ok=True)
        (lock_dir / "reminder-system_snooze.lock").touch()

        assert reminder_app.trigger_reminder("test_reminder") is True
        assert reminder_app.active_reminder is None
        assert reminder_app._queue is not None
        assert reminder_app._queue.get_all() == ["test_reminder"]
    finally:
        _cleanup_app(reminder_app)


def test_trigger_reminder_config_queues_when_delay_is_pending(qt_app, config_dir: Path):
    """Direct config triggers should obey pending queue delays instead of bypassing them."""
    reminder_app = ReminderApp(config_dir=config_dir, enable_tray=False)

    assert reminder_app.initialize(
        skip_scheduler=True,
        general_overrides={"work_session_enable": False},
    )

    try:
        reminder_app._resume_pending = True
        adhoc = ReminderConfig(
            name="adhoc",
            schedule=["* * * * *"],
            icon="missing.png",
            snooze_duration=45,
            icon_path=config_dir / "missing.png",
            text="Ad-hoc reminder",
        )

        assert reminder_app.trigger_reminder_config(adhoc) is True
        assert reminder_app.active_reminder is None
        assert reminder_app._queue is not None
        assert reminder_app._queue.get_all() == ["adhoc"]
        assert reminder_app.config_manager.reminders["adhoc"] is adhoc
    finally:
        _cleanup_app(reminder_app)


def test_hot_reload_reapplies_general_settings_and_active_reminder(
    qt_app, config_dir: Path
):
    """Hot reload should update overlay settings, scheduler state, and the active reminder."""
    lock_dir = config_dir / "locks"
    reminder_app = ReminderApp(config_dir=config_dir, enable_tray=False)

    assert reminder_app.initialize(
        skip_scheduler=False,
        general_overrides={
            "lock_dir": str(lock_dir),
            "work_session_enable": False,
        },
    )

    try:
        assert reminder_app.trigger_reminder("test_reminder") is True
        assert reminder_app.overlay is not None
        assert reminder_app.active_reminder is not None

        config_text = f"""
            [general]
            text_font = "Monospace"
            text_size = 30
            icon_scale = 1.5
            max_opacity = 0.65
            fade_in_duration = 1200
            fade_out_duration = 700
            lock_dir = "{lock_dir}"
            stagger_interval = 4
            resume_interval = 2
            work_session_enable = false
            work_session_start = "08:00"
            work_session_end = "18:00"

            [test_reminder]
            text = "Updated reminder text"
            schedule = ["*/5 * * * *"]
            icon = "test_icon.png"
            snooze_duration = 9
            """

        _write_config(
            config_dir,
            config_text,
        )

        reminder_app._reload_config()

        assert reminder_app.overlay.text_font == "Monospace"
        assert reminder_app.overlay.text_size == 30
        assert reminder_app.overlay.icon_scale == 1.5
        assert reminder_app.overlay.max_opacity == 0.65
        assert reminder_app.overlay.fade_in_duration == 1200
        assert reminder_app.overlay.fade_out_duration == 700
        assert reminder_app.overlay.text_label.text() == "Updated reminder text"
        assert reminder_app.active_reminder.snooze_duration == 9
        assert reminder_app.scheduler.reminders["test_reminder"].cron_expressions == [
            "*/5 * * * *"
        ]
    finally:
        _cleanup_app(reminder_app)


def test_tray_snooze_toggle_creates_and_removes_lock(qt_app, config_dir: Path):
    """The tray snooze toggle should manage its lock file immediately."""
    lock_dir = config_dir / "locks"
    reminder_app = ReminderApp(config_dir=config_dir, enable_tray=False)

    assert reminder_app.initialize(
        skip_scheduler=True,
        general_overrides={
            "lock_dir": str(lock_dir),
            "work_session_enable": False,
        },
    )

    tray = TrayWindow(reminder_app)
    reminder_app._tray_window = tray

    try:
        tray._toggle_snooze()
        assert (lock_dir / "reminder-system_snooze.lock").exists()
        assert reminder_app._snooze_lock_names == ["reminder-system"]

        tray._toggle_snooze()
        assert not (lock_dir / "reminder-system_snooze.lock").exists()
        assert reminder_app._snooze_lock_names == []
    finally:
        tray.close()
        _cleanup_app(reminder_app)


def test_tray_manual_work_session_controls_manage_state_and_lock(
    qt_app, config_dir: Path
):
    """The tray work-session controls should update persistent state and cancel locks."""
    lock_dir = config_dir / "locks"
    reminder_app = ReminderApp(config_dir=config_dir, enable_tray=False)

    assert reminder_app.initialize(
        skip_scheduler=True,
        general_overrides={
            "lock_dir": str(lock_dir),
            "work_session_enable": True,
        },
    )

    tray = TrayWindow(reminder_app)
    reminder_app._tray_window = tray

    try:
        assert reminder_app._state is not None
        assert reminder_app._state.get("work_session_operating_mode") == "automatic"

        tray._toggle_ws_mode()
        assert reminder_app._state.get("work_session_operating_mode") == "manual"

        initial_exists = (lock_dir / "work-session_cancel.lock").exists()
        tray._toggle_ws_lock()
        assert (lock_dir / "work-session_cancel.lock").exists() is (not initial_exists)
        assert reminder_app._cancel_lock_names == (
            ["work-session"] if not initial_exists else []
        )

        tray._toggle_ws_lock()
        assert (lock_dir / "work-session_cancel.lock").exists() is initial_exists
        assert reminder_app._cancel_lock_names == (
            ["work-session"] if initial_exists else []
        )
    finally:
        tray.close()
        _cleanup_app(reminder_app)
