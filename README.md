# Desktop Reminder System

A beautiful, non-intrusive desktop reminder overlay application for Linux (KDE Plasma 6 compatible).

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

## Usage
### Run on startup
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

