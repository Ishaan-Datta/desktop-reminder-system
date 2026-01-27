#!/usr/bin/env python3
"""
Manual trigger script for testing the reminder overlay.

This script allows you to test the overlay window without needing to:
1. Copy config to ~/.config/reminder-system/
2. Wait for cron schedules to trigger

Usage:
    # From project root:
    python -m tests.manual_trigger
    
    # Or with uv:
    uv run python -m tests.manual_trigger
    
    # With custom icon:
    python -m tests.manual_trigger --icon /path/to/icon.png
    
    # With specific test reminder name:
    python -m tests.manual_trigger --name "Water Break"
"""

import sys
import signal
import argparse
from pathlib import Path

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from reminder_system.overlay import ReminderOverlay
from reminder_system.config import ReminderConfig


# Directory containing test fixtures
FIXTURES_DIR = Path(__file__).parent / "fixtures"


def create_test_reminder(
    name: str = "Test Reminder",
    icon_path: Path | None = None,
    snooze_duration: int = 30
) -> ReminderConfig:
    """Create a ReminderConfig for testing."""
    if icon_path is None:
        # Use test icon if available, otherwise use a placeholder path
        icon_path = FIXTURES_DIR / "test_icon.png"
    
    return ReminderConfig(
        name=name,
        schedule="* * * * *",  # Every minute (not used in manual trigger)
        icon=icon_path.name,
        snooze_duration=snooze_duration,
        icon_path=icon_path
    )


def on_completed(name: str):
    """Handle reminder completion."""
    print(f"\n✓ Reminder '{name}' marked as COMPLETE")
    print("Exiting in 1 second...")
    QTimer.singleShot(1000, QApplication.quit)


def on_snoozed(name: str, duration: int):
    """Handle reminder snooze."""
    print(f"\n⏰ Reminder '{name}' SNOOZED for {duration} seconds")
    print("Exiting in 1 second...")
    QTimer.singleShot(1000, QApplication.quit)


def main():
    parser = argparse.ArgumentParser(
        description="Manually trigger a reminder overlay for testing"
    )
    parser.add_argument(
        "--name", "-n",
        default="Test Reminder",
        help="Name to display for the reminder"
    )
    parser.add_argument(
        "--icon", "-i",
        type=Path,
        default=None,
        help="Path to a PNG icon file"
    )
    parser.add_argument(
        "--snooze", "-s",
        type=int,
        default=30,
        help="Snooze duration in seconds"
    )
    parser.add_argument(
        "--use-fixture",
        action="store_true",
        help="Use the test fixture config instead of custom values"
    )
    
    args = parser.parse_args()
    
    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("Reminder Test")
    
    # Handle Ctrl+C
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    timer = QTimer()
    timer.timeout.connect(lambda: None)
    timer.start(500)
    
    # Determine icon path
    icon_path = args.icon
    if icon_path is None:
        icon_path = FIXTURES_DIR / "test_icon.png"
    
    if not icon_path.exists():
        print(f"Note: Icon file not found at {icon_path}")
        print("The overlay will display a text fallback instead.")
    
    # Create reminder config
    config = create_test_reminder(
        name=args.name,
        icon_path=icon_path,
        snooze_duration=args.snooze
    )
    
    print("=" * 50)
    print("MANUAL REMINDER TRIGGER TEST")
    print("=" * 50)
    print(f"Reminder: {config.name}")
    print(f"Icon: {config.icon_path}")
    print(f"Snooze duration: {config.snooze_duration}s")
    print("-" * 50)
    print("The overlay will appear shortly.")
    print("Click ✓ to complete or ⏰ to snooze.")
    print("Press Ctrl+C to cancel.")
    print("=" * 50)
    
    # Create and show overlay
    overlay = ReminderOverlay()
    overlay.completed.connect(on_completed)
    overlay.snoozed.connect(on_snoozed)
    
    # Trigger after a brief delay to let the window initialize
    QTimer.singleShot(500, lambda: overlay.show_reminder(
        name=config.name,
        icon_path=config.icon_path,
        snooze_duration=config.snooze_duration
    ))
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
