#!/usr/bin/env python3
"""
Manual test for overlapping / queued reminders.

This script creates multiple fake reminders and fires them in rapid succession
so you can observe the queue, stagger, resume, snooze-lock, and cancel-lock
behaviours without waiting for cron schedules.

Usage:
    # Basic test – fire 3 reminders back-to-back:
    uv run python -m tests.manual_trigger_overlap

    # Fire 5 reminders:
    uv run python -m tests.manual_trigger_overlap --count 5

    # Custom stagger / resume intervals (seconds):
    uv run python -m tests.manual_trigger_overlap --stagger 3 --resume 2

    # Pre-create the snooze lock so reminders get queued, then remove it:
    touch /tmp/test-reminder-snooze.lock
    uv run python -m tests.manual_trigger_overlap
    # (reminders queue up; remove the lock to see them drain)
    rm /tmp/test-reminder-snooze.lock

    # Pre-create the cancel lock so all reminders are silently skipped:
    touch /tmp/test-reminder-cancel.lock
    uv run python -m tests.manual_trigger_overlap
"""

import sys
import signal
import argparse
from pathlib import Path

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

sys.path.insert(0, str(Path(__file__).parent.parent))

from reminder_system.app import ReminderApp
from reminder_system.config import ReminderConfig, GeneralConfig, ConfigManager


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def build_fake_reminders(count: int, config_dir: Path) -> dict[str, ReminderConfig]:
    """Generate *count* unique ReminderConfigs with distinct names."""
    colours = [
        "🔴", "🟠", "🟡", "🟢", "🔵", "🟣", "⚪", "🟤", "⬛", "🩷",
    ]
    reminders: dict[str, ReminderConfig] = {}
    for i in range(count):
        name = f"test_reminder_{i + 1}"
        emoji = colours[i % len(colours)]
        reminders[name] = ReminderConfig(
            name=name,
            schedule=["* * * * *"],          # not used – we fire manually
            icon=f"test_icon.png",
            snooze_duration=10,
            icon_path=config_dir / "test_icon.png",
            text=f"{emoji}  Overlapping reminder #{i + 1} of {count}",
        )
    return reminders


def main():
    parser = argparse.ArgumentParser(
        description="Test overlapping / queued reminder behaviour",
    )
    parser.add_argument(
        "--count", "-c", type=int, default=3,
        help="Number of reminders to fire (default: 3)",
    )
    parser.add_argument(
        "--delay", "-d", type=int, default=500,
        help="Milliseconds between each trigger (default: 500)",
    )
    parser.add_argument(
        "--stagger", "-s", type=int, default=None,
        help="Override stagger_interval (seconds between queued reminders)",
    )
    parser.add_argument(
        "--resume", "-r", type=int, default=None,
        help="Override resume_interval (seconds before first queued reminder)",
    )
    parser.add_argument(
        "--snooze-lock", type=str, default=None,
        help="Override snooze lock file path",
    )
    parser.add_argument(
        "--cancel-lock", type=str, default=None,
        help="Override cancel lock file path",
    )
    args = parser.parse_args()

    # ── Qt setup ─────────────────────────────────────────────────
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("Reminder Overlap Test")

    signal.signal(signal.SIGINT, lambda *_: app.quit())
    heartbeat = QTimer()
    heartbeat.timeout.connect(lambda: None)
    heartbeat.start(500)

    # ── Build reminders ──────────────────────────────────────────
    config_dir = FIXTURES_DIR
    reminders = build_fake_reminders(args.count, config_dir)

    # ── Create ReminderApp with fixture config ───────────────────
    reminder_app = ReminderApp(config_dir=config_dir, enable_tray=False)
    if not reminder_app.initialize(skip_scheduler=True):
        print("Failed to initialize app")
        sys.exit(1)

    # Inject our fake reminders into the config manager
    reminder_app.config_manager.reminders.update(reminders)

    # Apply CLI overrides to general config
    general: GeneralConfig = reminder_app.config_manager.general
    if args.stagger is not None:
        general.stagger_interval = args.stagger
    if args.resume is not None:
        general.resume_interval = args.resume
    if args.snooze_lock is not None:
        general.snooze_lock_file = args.snooze_lock
    if args.cancel_lock is not None:
        general.cancel_lock_file = args.cancel_lock

    # ── Print summary ────────────────────────────────────────────
    print("=" * 60)
    print("OVERLAPPING REMINDERS TEST")
    print("=" * 60)
    print(f"  Reminders to fire : {args.count}")
    print(f"  Trigger delay     : {args.delay}ms between each")
    print(f"  Stagger interval  : {general.stagger_interval}s")
    print(f"  Resume interval   : {general.resume_interval}s")
    print(f"  Snooze lock file  : {general.snooze_lock_file}")
    print(f"  Cancel lock file  : {general.cancel_lock_file}")
    print(f"  Snooze lock exists: {Path(general.snooze_lock_file).exists()}")
    print(f"  Cancel lock exists: {Path(general.cancel_lock_file).exists()}")
    print("-" * 60)
    print("Reminders will be triggered shortly.")
    print("  ✓  = mark complete        ⏳ = snooze")
    print("  Ctrl+C = quit")
    print()
    print("Tip: create/remove the snooze or cancel lock files in another")
    print("terminal while this is running to observe the behaviour.")
    print("=" * 60)

    # ── Track dismissals to auto-exit ──────────────────────────
    dismissed = {"count": 0, "total": args.count}

    def _on_done(*_args):
        dismissed["count"] += 1
        remaining = dismissed["total"] - dismissed["count"]
        print(f"  [{dismissed['count']}/{dismissed['total']}] reminders handled"
              + (f", {remaining} remaining" if remaining else ""))
        if dismissed["count"] >= dismissed["total"]:
            print("\n✅ All reminders handled, exiting in 1s...")
            QTimer.singleShot(1000, app.quit)

    reminder_app.overlay.completed.connect(_on_done)
    reminder_app.overlay.snoozed.connect(_on_done)

    # ── Schedule rapid-fire triggers ─────────────────────────────
    names = list(reminders.keys())
    for i, name in enumerate(names):
        delay_ms = 500 + i * args.delay  # first one after 500ms
        QTimer.singleShot(
            delay_ms,
            lambda n=name: _fire(reminder_app, n, dismissed),
        )

    # ── Safety timeout (in case lock files keep reminders queued) ─
    safety_timeout = 300_000  # 5 minutes
    QTimer.singleShot(safety_timeout, lambda: _auto_quit(app))

    app.exec()


def _fire(reminder_app: ReminderApp, name: str, dismissed: dict):
    """Fire a single reminder through the app's trigger pathway."""
    print(f"\n>>> Firing reminder: {name}")
    reminder_app._trigger_reminder_threadsafe(name)
    # If the reminder was immediately skipped by cancel lock, count it
    # (it won't go through the overlay signals)
    if name not in (reminder_app.config_manager.reminders or {}) \
       or reminder_app._is_cancel_locked():
        dismissed["count"] += 1
        remaining = dismissed["total"] - dismissed["count"]
        print(f"  [{dismissed['count']}/{dismissed['total']}] reminders handled (skipped)"
              + (f", {remaining} remaining" if remaining else ""))
        if dismissed["count"] >= dismissed["total"]:
            print("\n✅ All reminders handled (all skipped), exiting in 1s...")
            from PyQt6.QtWidgets import QApplication
            QTimer.singleShot(1000, QApplication.instance().quit)


def _auto_quit(app: QApplication):
    """Quit after the generous timeout expires."""
    print("\n⏱  Test timeout reached, quitting.")
    app.quit()


if __name__ == "__main__":
    main()
