"""Configuration parser for the reminder system."""

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional


@dataclass
class ReminderConfig:
    """Configuration for a single reminder."""
    name: str
    schedule: str  # Cron string
    icon: str  # Filename of the icon
    snooze_duration: int  # Seconds
    icon_path: Path  # Full path to the icon

    def __post_init__(self):
        if isinstance(self.icon_path, str):
            self.icon_path = Path(self.icon_path)
    
    @classmethod
    def from_dict(cls, name: str, settings: dict, config_dir: Path) -> "ReminderConfig":
        """Create a ReminderConfig from a dictionary."""
        if "schedule" not in settings:
            raise ValueError(f"Reminder '{name}' is missing 'schedule' field")
        if "icon" not in settings:
            raise ValueError(f"Reminder '{name}' is missing 'icon' field")
        
        icon_filename = settings["icon"]
        icon_path = config_dir / icon_filename
        
        return cls(
            name=name,
            schedule=settings["schedule"],
            icon=icon_filename,
            snooze_duration=settings.get("snooze_duration", 300),
            icon_path=icon_path
        )


def parse_config_data(config_data: dict, config_dir: Path) -> Dict[str, ReminderConfig]:
    """
    Parse configuration data into ReminderConfig objects.
    
    Args:
        config_data: Raw parsed TOML data
        config_dir: Directory where icons are located
        
    Returns:
        Dictionary mapping reminder names to ReminderConfig objects
    """
    reminders = {}
    
    for name, settings in config_data.items():
        if not isinstance(settings, dict):
            continue
        
        reminder = ReminderConfig.from_dict(name, settings, config_dir)
        
        if not reminder.icon_path.exists():
            print(f"Warning: Icon file not found: {reminder.icon_path}")
        
        reminders[name] = reminder
    
    return reminders


def load_config_file(config_file: Path) -> dict:
    """Load and parse a TOML configuration file."""
    if not config_file.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {config_file}\n"
            f"Please create a config file at {config_file}"
        )
    
    with open(config_file, "rb") as f:
        return tomllib.load(f)


class ConfigManager:
    """Manages loading and parsing of the reminder configuration."""
    
    DEFAULT_CONFIG_DIR = Path.home() / ".config" / "reminder-system"
    CONFIG_FILE = "config.toml"
    
    def __init__(self, config_dir: Optional[Path] = None):
        self.config_dir = Path(config_dir) if config_dir else self.DEFAULT_CONFIG_DIR
        self.config_file = self.config_dir / self.CONFIG_FILE
        self.reminders: Dict[str, ReminderConfig] = {}
    
    def ensure_config_dir(self) -> None:
        """Create the config directory if it doesn't exist."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
    
    def load_config(self) -> Dict[str, ReminderConfig]:
        """Load and parse the configuration file."""
        config_data = load_config_file(self.config_file)
        self.reminders = parse_config_data(config_data, self.config_dir)
        return self.reminders
    
    def load_from_data(self, config_data: dict) -> Dict[str, ReminderConfig]:
        """Load reminders from already-parsed config data."""
        self.reminders = parse_config_data(config_data, self.config_dir)
        return self.reminders
    
    def create_example_config(self) -> None:
        """Create an example configuration file."""
        self.ensure_config_dir()
        
        example_config = '''# Reminder System Configuration
# Place icon files in ~/.config/reminder-system/

[water_break]
schedule = "0 * * * *"  # Every hour
icon = "water.png"
snooze_duration = 300  # 5 minutes

[stretch_break]
schedule = "30 9-17 * * 1-5"  # Every 30 minutes during work hours on weekdays
icon = "stretch.png"
snooze_duration = 600  # 10 minutes

[eye_rest]
schedule = "*/20 * * * *"  # Every 20 minutes (20-20-20 rule)
icon = "eye.png"
snooze_duration = 120  # 2 minutes
'''
        
        with open(self.config_file, "w") as f:
            f.write(example_config)
        
        print(f"Created example config at: {self.config_file}")
