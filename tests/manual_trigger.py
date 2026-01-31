#!/usr/bin/env python3
"""
Manual trigger script for testing the reminder overlay.

This script allows you to test the overlay window without needing to:
1. Copy config to ~/.config/reminder-system/
2. Wait for cron schedules to trigger

Usage:
    # From project root (uses tests/fixtures/config.toml by default):
    python -m tests.manual_trigger
    
    # Or with uv:
    uv run python -m tests.manual_trigger
    
    # Use example_config instead:
    python -m tests.manual_trigger --example
    
    # Trigger a specific reminder by name:
    python -m tests.manual_trigger --name water_break
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
from reminder_system.config import ConfigManager


# Directory containing test fixtures
FIXTURES_DIR = Path(__file__).parent / "fixtures"
EXAMPLE_CONFIG_DIR = Path(__file__).parent.parent / "example_config"


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
        default=None,
        help="Name of the reminder to trigger (uses first reminder if not specified)"
    )
    parser.add_argument(
        "--example", "-e",
        action="store_true",
        help="Use example_config/config.toml instead of tests/fixtures/config.toml"
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
    
    # Load config from fixture or example_config
    config_dir = EXAMPLE_CONFIG_DIR if args.example else FIXTURES_DIR
    print(f"Loading config from: {config_dir / 'config.toml'}")
    
    manager = ConfigManager(config_dir)
    try:
        reminders = manager.load_config()
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    
    general_config = manager.general
    
    if not reminders:
        print("No reminders found in config!")
        sys.exit(1)
    
    # Select reminder by name or use first one
    if args.name:
        if args.name not in reminders:
            print(f"Error: Reminder '{args.name}' not found in config.")
            print(f"Available reminders: {', '.join(reminders.keys())}")
            sys.exit(1)
        config = reminders[args.name]
    else:
        config = list(reminders.values())[0]
    
    if not config.icon_path.exists():
        print(f"Note: Icon file not found at {config.icon_path}")
        print("The overlay will display a text fallback instead.")
    
    print("=" * 50)
    print("MANUAL REMINDER TRIGGER TEST")
    print("=" * 50)
    print(f"Reminder: {config.name}")
    print(f"Icon: {config.icon_path}")
    print(f"Snooze duration: {config.snooze_duration}s")
    if config.text:
        print(f"Text: {config.text}")
    print("-" * 50)
    print("General Settings:")
    print(f"  Font: {general_config.text_font}")
    print(f"  Text size: {general_config.text_size}px")
    print(f"  Icon scale: {general_config.icon_scale}x")
    print(f"  Max opacity: {general_config.max_opacity}")
    print(f"  Fade-in: {general_config.fade_in_duration}ms")
    print(f"  Fade-out: {general_config.fade_out_duration}ms")
    print("-" * 50)
    print("The overlay will appear shortly.")
    print("Click ✓ to complete or ⏰ to snooze.")
    print("Press Ctrl+C to cancel.")
    print("=" * 50)
    
    # Create and show overlay with general config
    overlay = ReminderOverlay(general_config=general_config)
    overlay.completed.connect(on_completed)
    overlay.snoozed.connect(on_snoozed)
    
    # Trigger after a brief delay to let the window initialize
    QTimer.singleShot(500, lambda: overlay.show_reminder(
        name=config.name,
        icon_path=config.icon_path,
        snooze_duration=config.snooze_duration,
        text=config.text
    ))
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
