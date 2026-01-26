# Desktop Reminder System

A beautiful, non-intrusive desktop reminder overlay application for Linux (KDE Plasma 6 compatible).

## Features

- 🎯 **Non-intrusive overlay**: Appears as a transparent overlay that doesn't steal focus
- 🌅 **Smooth animations**: Gradual fade-in of icon and background
- ⏰ **Cron-based scheduling**: Flexible scheduling using cron expressions
- 😴 **Snooze support**: Snooze reminders for a configurable duration
- 🖼️ **Custom icons**: Use your own PNG icons for each reminder
- 🔔 **System tray**: Runs quietly in the system tray

## Screenshots

The overlay appears in the center of your screen with:
- Your custom PNG icon fading in
- Background gradually darkening
- Two buttons: ✓ (Complete) and ⏰ (Snooze)

## Installation

### Prerequisites

- Python 3.9+
- PyQt6
- KDE Plasma 6 (or any Linux DE with X11/Wayland)

### Install from source

```bash
# Clone or navigate to the project
cd desktop-reminder-system

# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Or install as a package
pip install -e .
```

## Configuration

Configuration is stored in `~/.config/reminder-system/config.toml`

### Setup

```bash
# Create the config directory
mkdir -p ~/.config/reminder-system

# Copy example config
cp example_config/config.toml ~/.config/reminder-system/

# Add your icon files to the same directory
cp your-icons/*.png ~/.config/reminder-system/
```

### Config Format

```toml
[alarm_name]
schedule = "cron expression"
icon = "icon_filename.png"
snooze_duration = 300  # seconds
```

### Example Configuration

```toml
# Water break every hour
[water_break]
schedule = "0 * * * *"
icon = "water.png"
snooze_duration = 300

# Stretch break every 30 minutes during work hours
[stretch_break]
schedule = "*/30 9-17 * * 1-5"
icon = "stretch.png"
snooze_duration = 600

# Eye rest every 20 minutes (20-20-20 rule)
[eye_rest]
schedule = "*/20 * * * *"
icon = "eye.png"
snooze_duration = 120
```

### Cron Expression Reference

```
┌───────────── minute (0-59)
│ ┌───────────── hour (0-23)
│ │ ┌───────────── day of month (1-31)
│ │ │ ┌───────────── month (1-12)
│ │ │ │ ┌───────────── day of week (0-6, 0=Sunday)
│ │ │ │ │
* * * * *
```

Common examples:
- `0 * * * *` - Every hour at minute 0
- `*/20 * * * *` - Every 20 minutes
- `30 9-17 * * 1-5` - At minute 30, hours 9-17, Monday-Friday
- `0 12 * * *` - Every day at noon

## Usage

### Run directly

```bash
# From project directory
python run.py

# Or as a module
python -m reminder_system.app

# Or if installed
reminder-system
```

### Run on startup

#### Option 1: Autostart (KDE/Desktop)

```bash
# Copy desktop file to autostart
cp reminder-system.desktop ~/.config/autostart/
```

#### Option 2: Systemd user service

```bash
# Copy service file
cp reminder-system.service ~/.config/systemd/user/

# Enable and start
systemctl --user enable reminder-system
systemctl --user start reminder-system

# Check status
systemctl --user status reminder-system
```

## Keyboard Shortcuts

When the overlay is active:
- **Enter** - Mark reminder as complete
- **Escape** - Snooze reminder

## System Tray Menu

Right-click the tray icon for:
- **Show Status** - Display all reminders and their next trigger times
- **Test Reminder** - Trigger a test notification
- **Quit** - Exit the application

## How It Works

1. **Startup**: Loads configuration and schedules all reminders
2. **Trigger**: When a cron schedule matches, the overlay appears
3. **Animation sequence**:
   - Icon fades in (2 seconds)
   - Background gradually darkens (3 seconds)
   - Buttons appear
4. **User action**:
   - ✓ Complete: Schedules next occurrence
   - ⏰ Snooze: Reschedules for snooze_duration seconds later
5. **Dismiss**: Overlay fades out smoothly

## Project Structure

```
desktop-reminder-system/
├── reminder_system/
│   ├── __init__.py
│   ├── app.py          # Main application
│   ├── config.py       # Configuration parser
│   ├── overlay.py      # Overlay window widget
│   └── scheduler.py    # Cron-based scheduler
├── example_config/
│   └── config.toml     # Example configuration
├── run.py              # Entry point
├── requirements.txt
├── setup.py
├── pyproject.toml
├── reminder-system.service  # Systemd service
└── reminder-system.desktop  # Desktop autostart
```

## Troubleshooting

### Overlay not appearing on Wayland

Some Wayland compositors may require additional permissions. Try:

```bash
# Run with X11 backend
QT_QPA_PLATFORM=xcb python run.py
```

### Icons not showing

- Ensure PNG files are in `~/.config/reminder-system/`
- Check file permissions
- Verify filenames match config exactly (case-sensitive)

### System tray not visible

Make sure your desktop environment supports system tray icons. On KDE Plasma 6, the system tray should work out of the box.

## License

MIT License  