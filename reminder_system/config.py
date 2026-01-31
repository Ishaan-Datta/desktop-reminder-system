"""Configuration parser for the reminder system."""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional


@dataclass
class GeneralConfig:
    """General settings for the reminder system."""
    text_font: str = "Sans Serif"
    text_size: int = 24
    icon_scale: float = 1.0
    max_opacity: float = 0.85
    fade_in_duration: int = 2000  # milliseconds
    fade_out_duration: int = 500  # milliseconds
    
    @classmethod
    def from_dict(cls, settings: dict) -> "GeneralConfig":
        """Create a GeneralConfig from a dictionary."""
        return cls(
            text_font=settings.get("text_font", "Sans Serif"),
            text_size=settings.get("text_size", 24),
            icon_scale=settings.get("icon_scale", 1.0),
            max_opacity=settings.get("max_opacity", 0.85),
            fade_in_duration=settings.get("fade_in_duration", 2000),
            fade_out_duration=settings.get("fade_out_duration", 500),
        )


@dataclass
class ReminderConfig:
    """Configuration for a single reminder."""
    name: str
    schedule: str  # Cron string
    icon: str  # Filename of the icon
    snooze_duration: int  # Seconds
    icon_path: Path  # Full path to the icon
    text: Optional[str] = None  # Optional text to display under the icon

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
            icon_path=icon_path,
            text=settings.get("text", None)
        )


def parse_config_data(config_data: dict, config_dir: Path) -> tuple[Dict[str, ReminderConfig], GeneralConfig]:
    """
    Parse configuration data into ReminderConfig objects and GeneralConfig.
    
    Args:
        config_data: Raw parsed TOML data
        config_dir: Directory where icons are located
        
    Returns:
        Tuple of (dictionary mapping reminder names to ReminderConfig objects, GeneralConfig)
    """
    reminders = {}
    general_config = GeneralConfig()
    
    for name, settings in config_data.items():
        if not isinstance(settings, dict):
            continue
        
        # Handle [general] section separately
        if name == "general":
            general_config = GeneralConfig.from_dict(settings)
            continue
        
        reminder = ReminderConfig.from_dict(name, settings, config_dir)
        
        if not reminder.icon_path.exists():
            print(f"Warning: Icon file not found: {reminder.icon_path}")
        
        reminders[name] = reminder
    
    return reminders, general_config


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
        self.general: GeneralConfig = GeneralConfig()
    
    def ensure_config_dir(self) -> None:
        """Create the config directory if it doesn't exist."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
    
    def load_config(self) -> Dict[str, ReminderConfig]:
        """Load and parse the configuration file."""
        config_data = load_config_file(self.config_file)
        self.reminders, self.general = parse_config_data(config_data, self.config_dir)
        return self.reminders
    
    def load_from_data(self, config_data: dict) -> Dict[str, ReminderConfig]:
        """Load reminders from already-parsed config data."""
        self.reminders, self.general = parse_config_data(config_data, self.config_dir)
        return self.reminders
    
    def create_example_config(self) -> None:
        """Create an example configuration file."""
        self.ensure_config_dir()
        
        example_config = '''# Reminder System Configuration
# Place icon files in ~/.config/reminder-system/

# General settings (optional - these are the defaults)
[general]
text_font = "Sans Serif"  # Font for reminder text
text_size = 24            # Font size for reminder text
icon_scale = 1.0          # Scale factor for icons (1.0 = 200px)
max_opacity = 0.85        # Maximum opacity of dark overlay (0.0-1.0)
fade_in_duration = 2000   # Fade-in animation duration in milliseconds
fade_out_duration = 500   # Fade-out animation duration in milliseconds

[water_break]
schedule = "0 * * * *"  # Every hour
icon = "water.png"
snooze_duration = 300  # 5 minutes
text = "Time to drink some water!"

[stretch_break]
schedule = "30 9-17 * * 1-5"  # Every 30 minutes during work hours on weekdays
icon = "stretch.png"
snooze_duration = 600  # 10 minutes
text = "Stand up and stretch for a minute"

[eye_rest]
schedule = "*/20 * * * *"  # Every 20 minutes (20-20-20 rule)
icon = "eye.png"
snooze_duration = 120  # 2 minutes
text = "Look at something 20 feet away for 20 seconds"
'''
        
        with open(self.config_file, "w") as f:
            f.write(example_config)
        
        print(f"Created example config at: {self.config_file}")
