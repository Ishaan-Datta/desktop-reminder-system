"""Configuration parser for the reminder system."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

try:
    import tomllib
except ImportError:
    import tomli as tomllib


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


class ConfigManager:
    """Manages loading and parsing of the reminder configuration."""
    
    DEFAULT_CONFIG_DIR = Path.home() / ".config" / "reminder-system"
    CONFIG_FILE = "config.toml"
    
    def __init__(self, config_dir: Optional[Path] = None):
        self.config_dir = config_dir or self.DEFAULT_CONFIG_DIR
        self.config_file = self.config_dir / self.CONFIG_FILE
        self.reminders: Dict[str, ReminderConfig] = {}
    
    def ensure_config_dir(self) -> None:
        """Create the config directory if it doesn't exist."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
    
    def load_config(self) -> Dict[str, ReminderConfig]:
        """Load and parse the configuration file."""
        if not self.config_file.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {self.config_file}\n"
                f"Please create a config file at {self.config_file}"
            )
        
        with open(self.config_file, "rb") as f:
            config_data = tomllib.load(f)
        
        self.reminders = {}
        
        for name, settings in config_data.items():
            if not isinstance(settings, dict):
                continue
            
            # Validate required fields
            if "schedule" not in settings:
                raise ValueError(f"Reminder '{name}' is missing 'schedule' field")
            if "icon" not in settings:
                raise ValueError(f"Reminder '{name}' is missing 'icon' field")
            
            icon_filename = settings["icon"]
            icon_path = self.config_dir / icon_filename
            
            if not icon_path.exists():
                print(f"Warning: Icon file not found: {icon_path}")
            
            self.reminders[name] = ReminderConfig(
                name=name,
                schedule=settings["schedule"],
                icon=icon_filename,
                snooze_duration=settings.get("snooze_duration", 300),  # Default 5 minutes
                icon_path=icon_path
            )
        
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
