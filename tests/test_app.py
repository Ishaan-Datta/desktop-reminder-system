"""Integration tests for reminder app queue/cancel-lock behaviour."""

import os
import shutil
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from reminder_system.app import ReminderApp


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
