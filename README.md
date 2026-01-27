# Desktop Reminder System

A beautiful, non-intrusive desktop reminder overlay application for Linux (KDE Plasma 6 compatible).

## Features

- 🎯 **Non-intrusive overlay**: Appears as a transparent overlay that doesn't steal focus
- 🌅 **Smooth animations**: Gradual fade-in of icon and background
- ⏰ **Cron-based scheduling**: Flexible scheduling using cron expressions
- 😴 **Snooze support**: Snooze reminders for a configurable duration
- 🖼️ **Custom icons**: Use your own PNG icons for each reminder
- 🔔 **System tray**: Runs quietly in the system tray
- ❄️ **NixOS support**: Includes Nix flake with uv2nix

## Screenshots

The overlay appears in the center of your screen with:
- Your custom PNG icon fading in
- Background gradually darkening
- Two buttons: ✓ (Complete) and ⏰ (Snooze)

## Installation

### NixOS / Nix (Recommended)

```bash
# Enter development shell
nix develop

# Sync dependencies with uv
uv sync

# Run the application
uv run python run.py

# Or run tests
uv run python -m tests.manual_trigger
```

#### Home Manager Integration

Add to your `home.nix`:

```nix
{
  imports = [
    (builtins.getFlake "path:/path/to/desktop-reminder-system").homeManagerModules.default
  ];
  
  services.reminder-system = {
    enable = true;
    settings = {
      water_break = {
        schedule = "0 * * * *";
        icon = "water.png";
        snooze_duration = 300;
      };
      stretch_break = {
        schedule = "*/30 9-17 * * 1-5";
        icon = "stretch.png";
        snooze_duration = 600;
      };
    };
  };
}
```

### Traditional Installation

#### Prerequisites

- Python 3.11+
- PyQt6
- KDE Plasma 6 (or any Linux DE with X11/Wayland)

#### Using uv (Recommended)

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Sync dependencies
uv sync

# Run the application
uv run python run.py
```

#### Using pip

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install as a package
pip install -e .

# Run the application
reminder-system
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
├── tests/
│   ├── fixtures/       # Test config and icons
│   ├── manual_trigger.py   # Manual overlay test
│   ├── run_with_fixtures.py # Run with test config
│   ├── test_config.py  # Config unit tests
│   └── test_scheduler.py   # Scheduler unit tests
├── example_config/
│   └── config.toml     # Example configuration
├── flake.nix           # Nix flake (uv2nix)
├── pyproject.toml      # Python project config
├── run.py              # Entry point
├── reminder-system.service  # Systemd service
└── reminder-system.desktop  # Desktop autostart
```

## Testing

### Manual Overlay Test

Test the overlay without configuring `~/.config/reminder-system/`:

```bash
# Using uv
uv run python -m tests.manual_trigger

# With custom icon
uv run python -m tests.manual_trigger --icon /path/to/icon.png

# With custom name
uv run python -m tests.manual_trigger --name "Water Break"
```

### Run with Test Fixtures

Run the full app using the test fixtures directory:

```bash
uv run python -m tests.run_with_fixtures
```

### Unit Tests

```bash
uv run pytest tests/
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