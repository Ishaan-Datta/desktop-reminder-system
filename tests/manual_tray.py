#!/usr/bin/env python3
"""
Manual test for the system tray icon, context menu, and popup window.

Starts the full ReminderApp with a handful of fake reminders (no real cron
scheduling) so you can interact with the tray icon immediately:

  • Left-click  → toggle the tray panel window (Controls / Upcoming / Queue)
  • Right-click → context menu (Print Status, Quit)

A few reminders are pre-queued so the Queue page has something to show.

Usage:
    # Basic – uses tests/fixtures/ config for lock_dir, icons, etc.:
    uv run python -m tests.manual_tray

    # Override lock dir (e.g. a temp directory you control):
    uv run python -m tests.manual_tray --lock-dir /tmp/my-locks

    # Pre-populate the queue with N fake items:
    uv run python -m tests.manual_tray --queued 5

    # Enable the work session feature for testing:
    uv run python -m tests.manual_tray --work-session

    # Set custom work session window (HH:MM):
    uv run python -m tests.manual_tray --work-session --ws-start 08:00 --ws-end 20:00
"""

import sys
import signal
import argparse
from pathlib import Path

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

sys.path.insert(0, str(Path(__file__).parent.parent))

from reminder_system.app import ReminderApp
from reminder_system.config import ReminderConfig, GeneralConfig, load_config_file


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def build_fake_reminders(config_dir: Path) -> dict[str, ReminderConfig]:
    """Generate a small set of reminders for interactive testing."""
    entries = [
        ("water_break", "💧", "Time to drink some water!", "0 * * * *", 15),
        ("stretch_break", "🧘", "Stand up and stretch!", "*/30 9-17 * * 1-5", 600),
        ("eye_rest", "👁", "Look away for 20 seconds", "*/20 * * * *", 120),
        ("posture_check", "🪑", "Check your posture!", "*/15 * * * *", 180),
    ]
    reminders: dict[str, ReminderConfig] = {}
    for name, emoji, text, schedule, snooze in entries:
        reminders[name] = ReminderConfig(
            name=name,
            schedule=[schedule],
            icon="test_icon.png",
            snooze_duration=snooze,
            icon_path=config_dir / "test_icon.png",
            text=f"{emoji}  {text}",
        )
    return reminders


def main():
    parser = argparse.ArgumentParser(
        description="Interactive test for the tray icon, context menu, and panel window",
    )
    parser.add_argument(
        "--lock-dir",
        type=str,
        default=None,
        help="Override lock_dir (default: value from fixtures config)",
    )
    parser.add_argument(
        "--queued",
        "-q",
        type=int,
        default=2,
        help="Number of fake reminders to pre-queue (default: 2)",
    )
    parser.add_argument(
        "--work-session",
        action="store_true",
        help="Enable the work session feature",
    )
    parser.add_argument(
        "--ws-start",
        type=str,
        default="09:00",
        help="Work session start time HH:MM (default: 09:00)",
    )
    parser.add_argument(
        "--ws-end",
        type=str,
        default="17:00",
        help="Work session end time HH:MM (default: 17:00)",
    )
    parser.add_argument(
        "--start-snooze-lock",
        action="store_true",
        help="Create reminder-system_snooze.lock before the app starts",
    )
    parser.add_argument(
        "--start-cancel-lock",
        action="store_true",
        help="Create reminder-system_cancel.lock before the app starts",
    )
    args = parser.parse_args()

    # ── Qt setup ─────────────────────────────────────────────────
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("Tray Test")

    signal.signal(signal.SIGINT, lambda *_: app.quit())
    heartbeat = QTimer()
    heartbeat.timeout.connect(lambda: None)
    heartbeat.start(500)

    general_overrides: dict[str, object] = {}
    if args.lock_dir is not None:
        general_overrides["lock_dir"] = args.lock_dir
    if args.work_session:
        general_overrides["work_session_enable"] = True
        general_overrides["work_session_start"] = args.ws_start
        general_overrides["work_session_end"] = args.ws_end

    config_data = load_config_file(FIXTURES_DIR / "config.toml")
    effective_general = dict(config_data.get("general", {}))
    effective_general.update(general_overrides)

    effective_lock_dir = Path(effective_general.get("lock_dir", "/tmp"))
    effective_lock_dir.mkdir(parents=True, exist_ok=True)
    if args.start_snooze_lock:
        (effective_lock_dir / "reminder-system_snooze.lock").touch()
    if args.start_cancel_lock:
        (effective_lock_dir / "reminder-system_cancel.lock").touch()

    # ── Create ReminderApp with fixture config ───────────────────
    reminder_app = ReminderApp(config_dir=FIXTURES_DIR, enable_tray=True)
    if not reminder_app.initialize(
        skip_scheduler=True,
        general_overrides=general_overrides or None,
    ):
        print("Failed to initialize app")
        sys.exit(1)

    # Inject fake reminders
    fake = build_fake_reminders(FIXTURES_DIR)
    reminder_app.config_manager.reminders.update(fake)

    # Add some to the scheduler so the Upcoming page is populated
    for name, cfg in fake.items():
        reminder_app.scheduler.add_reminder(
            name=name,
            cron_expression=cfg.schedule,
            # Use the real app trigger path so snoozed reminders can fire again
            # and re-enter the queue/overlay flow during manual testing.
            callback=reminder_app._trigger_reminder_threadsafe,
        )

    general: GeneralConfig = reminder_app.config_manager.general

    # Pre-queue some reminders
    names = list(fake.keys())
    for i in range(min(args.queued, len(names))):
        reminder_app._queue.push_back(names[i])

    # ── Print summary ────────────────────────────────────────────
    print("=" * 60)
    print("TRAY ICON / PANEL INTERACTIVE TEST")
    print("=" * 60)
    print(f"  Lock dir          : {general.lock_dir}")
    print(f"  Fake reminders    : {len(fake)}")
    print(f"  Pre-queued        : {min(args.queued, len(names))}")
    print(f"  Startup snooze lock: {'ON' if args.start_snooze_lock else 'OFF'}")
    print(f"  Startup cancel lock: {'ON' if args.start_cancel_lock else 'OFF'}")
    ws = "ON" if general.work_session_enable else "OFF"
    print(f"  Work session      : {ws}", end="")
    if general.work_session_enable:
        ws_mode = (
            reminder_app._state.get("work_session_operating_mode", "automatic")
            if reminder_app._state
            else "automatic"
        )
        print(
            f"  ({general.work_session_start} – {general.work_session_end},"
            f" mode={ws_mode})"
        )
    else:
        print()
    print()
    print("  Left-click tray icon  → toggle panel window")
    print("  Right-click tray icon → context menu")
    print("  Ctrl+C                → quit")
    print("=" * 60)

    # ── Run ──────────────────────────────────────────────────────
    reminder_app.run()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
