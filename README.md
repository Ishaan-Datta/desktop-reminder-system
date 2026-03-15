# Desktop Reminder System

A Linux desktop reminder application with a full-screen overlay, cron scheduling, a persistent queue, config hot reload, and a tray control panel.

## Features

- Transparent reminder overlay with complete and snooze actions
- Multiple cron schedules per reminder
- Persistent queue and persistent runtime state across restarts
- Lock-file based pause/cancel controls
- Work-session automation with manual tray overrides
- Config hot reload for reminder schedules and overlay appearance
- Tray window with Upcoming, Queue, and Controls pages
- Wayland-aware tray integration through StatusNotifierItem
- Nix flake and uv-based development workflow

## Installation

If you use `direnv` and `nix-direnv` packages on your system the `.envrc` and flake `devShell` hooks will setup everything, or manually:

```bash
nix develop
uv sync
uv run python run.py
```

## Configuration

The application reads [config.toml](example_config/config.toml) from `~/.config/reminder-system/config.toml`.

### Reminder format

```toml
[my_reminder]
schedule = ["0 * * * *", "30 9-17 * * 1-5"]
icon = "water.png"
snooze_duration = 300
text = "Time to drink some water"
```

### General settings

The optional `[general]` section supports:

- `text_font`
- `text_size`
- `icon_scale`
- `max_opacity`
- `fade_in_duration`
- `fade_out_duration`
- `lock_dir`
- `stagger_interval`
- `resume_interval`
- `work_session_enable`
- `work_session_start`
- `work_session_end`

See [example_config/config.toml](example_config/config.toml) for the current complete sample.

## Usage

### Run the app

```bash
uv run python run.py
```

You can also run the package entry point:

```bash
uv run reminder-system
```

### Keyboard shortcuts

When the overlay is visible:

- `Enter`: complete the reminder
- `Escape`: snooze the reminder

## Tray behavior

### Left-click tray window

The tray window exposes three pages:

- `Upcoming`: next scheduled reminders
- `Queue`: currently queued reminders
- `Controls`: snooze lock, work-session mode, and work-session lock

## Hot reload

Editing the config file reloads:

- reminder schedules
- general overlay appearance settings
- the active reminder content when that reminder still exists after reload
- tray status derived from the updated config and lock directory

## Testing

- [tests/manual_trigger.py](tests/manual_trigger.py): display a single reminder from fixture or example config
- [tests/manual_trigger_overlap.py](tests/manual_trigger_overlap.py): stress queueing and lock behavior
- [tests/manual_tray.py](tests/manual_tray.py): exercise tray controls and the tray panel
- [tests/run_with_fixtures.py](tests/run_with_fixtures.py): run the full app with fixture config

