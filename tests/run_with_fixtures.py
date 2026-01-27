#!/usr/bin/env python3
"""
Run the full reminder app using test fixtures.

This allows running the complete application with:
- Config from tests/fixtures/ instead of ~/.config/reminder-system/
- Test icons from the project directory
- Full scheduler functionality

Usage:
    python -m tests.run_with_fixtures
    
    # Or with uv:
    uv run python -m tests.run_with_fixtures
"""

import sys
import signal
from pathlib import Path

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from reminder_system.app import ReminderApp


# Directory containing test fixtures
FIXTURES_DIR = Path(__file__).parent / "fixtures"


def main():
    print("=" * 50)
    print("REMINDER SYSTEM - TEST MODE")
    print("=" * 50)
    print(f"Using config from: {FIXTURES_DIR}")
    print("=" * 50)
    
    # Create Qt application
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("Reminder System (Test)")
    
    # Create reminder app with custom config directory
    reminder_app = ReminderApp(
        config_dir=FIXTURES_DIR,
        enable_tray=True
    )
    
    if not reminder_app.initialize():
        print("\nFailed to initialize. Make sure tests/fixtures/config.toml exists.")
        sys.exit(1)
    
    # Handle Ctrl+C
    signal.signal(signal.SIGINT, lambda *_: reminder_app._quit())
    timer = QTimer()
    timer.timeout.connect(lambda: None)
    timer.start(500)
    
    # Start the application
    reminder_app.run()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
