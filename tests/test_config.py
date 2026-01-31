"""Unit tests for the config module."""

import pytest
from pathlib import Path
import tempfile

from reminder_system.config import (
    ReminderConfig,
    GeneralConfig,
    ConfigManager,
    parse_config_data,
    load_config_file
)


FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestReminderConfig:
    """Tests for ReminderConfig dataclass."""
    
    def test_from_dict_valid(self):
        """Test creating config from valid dictionary."""
        settings = {
            "schedule": "0 * * * *",
            "icon": "test.png",
            "snooze_duration": 120
        }
        config = ReminderConfig.from_dict("test", settings, Path("/tmp"))
        
        assert config.name == "test"
        assert config.schedule == "0 * * * *"
        assert config.icon == "test.png"
        assert config.snooze_duration == 120
        assert config.icon_path == Path("/tmp/test.png")
    
    def test_from_dict_missing_schedule(self):
        """Test that missing schedule raises ValueError."""
        settings = {"icon": "test.png"}
        with pytest.raises(ValueError, match="missing 'schedule'"):
            ReminderConfig.from_dict("test", settings, Path("/tmp"))
    
    def test_from_dict_missing_icon(self):
        """Test that missing icon raises ValueError."""
        settings = {"schedule": "0 * * * *"}
        with pytest.raises(ValueError, match="missing 'icon'"):
            ReminderConfig.from_dict("test", settings, Path("/tmp"))
    
    def test_from_dict_default_snooze(self):
        """Test that snooze_duration defaults to 300."""
        settings = {
            "schedule": "0 * * * *",
            "icon": "test.png"
        }
        config = ReminderConfig.from_dict("test", settings, Path("/tmp"))
        assert config.snooze_duration == 300
    
    def test_from_dict_with_text(self):
        """Test creating config with optional text field."""
        settings = {
            "schedule": "0 * * * *",
            "icon": "test.png",
            "text": "Time to take a break!"
        }
        config = ReminderConfig.from_dict("test", settings, Path("/tmp"))
        
        assert config.text == "Time to take a break!"
    
    def test_from_dict_without_text(self):
        """Test that text defaults to None when not provided."""
        settings = {
            "schedule": "0 * * * *",
            "icon": "test.png"
        }
        config = ReminderConfig.from_dict("test", settings, Path("/tmp"))
        
        assert config.text is None


class TestGeneralConfig:
    """Tests for GeneralConfig dataclass."""
    
    def test_default_values(self):
        """Test that GeneralConfig has correct default values."""
        config = GeneralConfig()
        
        assert config.text_font == "Sans Serif"
        assert config.text_size == 24
        assert config.icon_scale == 1.0
        assert config.max_opacity == 0.85
        assert config.fade_in_duration == 2000
        assert config.fade_out_duration == 500
    
    def test_from_dict_full(self):
        """Test creating GeneralConfig from dictionary with all values."""
        settings = {
            "text_font": "Roboto",
            "text_size": 32,
            "icon_scale": 1.5,
            "max_opacity": 0.9,
            "fade_in_duration": 3000,
            "fade_out_duration": 800
        }
        config = GeneralConfig.from_dict(settings)
        
        assert config.text_font == "Roboto"
        assert config.text_size == 32
        assert config.icon_scale == 1.5
        assert config.max_opacity == 0.9
        assert config.fade_in_duration == 3000
        assert config.fade_out_duration == 800
    
    def test_from_dict_partial(self):
        """Test creating GeneralConfig with only some values specified."""
        settings = {
            "text_font": "Arial",
            "icon_scale": 2.0
        }
        config = GeneralConfig.from_dict(settings)
        
        assert config.text_font == "Arial"
        assert config.text_size == 24  # default
        assert config.icon_scale == 2.0
        assert config.max_opacity == 0.85  # default
        assert config.fade_in_duration == 2000  # default
        assert config.fade_out_duration == 500  # default
    
    def test_from_dict_empty(self):
        """Test creating GeneralConfig from empty dictionary uses defaults."""
        config = GeneralConfig.from_dict({})
        
        assert config.text_font == "Sans Serif"
        assert config.text_size == 24
        assert config.icon_scale == 1.0
    """Tests for parse_config_data function."""
    
    def test_parse_multiple_reminders(self):
        """Test parsing multiple reminders."""
        config_data = {
            "reminder1": {
                "schedule": "0 * * * *",
                "icon": "icon1.png",
                "snooze_duration": 60
            },
            "reminder2": {
                "schedule": "30 9 * * *",
                "icon": "icon2.png"
            }
        }
        
        reminders, general = parse_config_data(config_data, Path("/config"))
        
        assert len(reminders) == 2
        assert "reminder1" in reminders
        assert "reminder2" in reminders
        assert reminders["reminder1"].snooze_duration == 60
        assert reminders["reminder2"].snooze_duration == 300  # default
    
    def test_parse_skips_non_dict_values(self):
        """Test that non-dictionary values are skipped."""
        config_data = {
            "valid": {
                "schedule": "0 * * * *",
                "icon": "icon.png"
            },
            "invalid": "not a dict",
            "also_invalid": 123
        }
        
        reminders, general = parse_config_data(config_data, Path("/config"))
        
        assert len(reminders) == 1
        assert "valid" in reminders
    
    def test_parse_with_general_section(self):
        """Test parsing config with [general] section."""
        config_data = {
            "general": {
                "text_font": "Helvetica",
                "text_size": 28,
                "icon_scale": 1.2,
                "max_opacity": 0.75,
                "fade_in_duration": 1500,
                "fade_out_duration": 400
            },
            "reminder1": {
                "schedule": "0 * * * *",
                "icon": "icon1.png",
                "text": "Drink water!"
            }
        }
        
        reminders, general = parse_config_data(config_data, Path("/config"))
        
        # General section should be parsed, not treated as reminder
        assert len(reminders) == 1
        assert "general" not in reminders
        assert "reminder1" in reminders
        
        # Check general config values
        assert general.text_font == "Helvetica"
        assert general.text_size == 28
        assert general.icon_scale == 1.2
        assert general.max_opacity == 0.75
        assert general.fade_in_duration == 1500
        assert general.fade_out_duration == 400
        
        # Check reminder text
        assert reminders["reminder1"].text == "Drink water!"
    
    def test_parse_without_general_section(self):
        """Test parsing config without [general] section uses defaults."""
        config_data = {
            "reminder1": {
                "schedule": "0 * * * *",
                "icon": "icon1.png"
            }
        }
        
        reminders, general = parse_config_data(config_data, Path("/config"))
        
        assert len(reminders) == 1
        # General should have default values
        assert general.text_font == "Sans Serif"
        assert general.text_size == 24
        assert general.icon_scale == 1.0


class TestConfigManager:
    """Tests for ConfigManager class."""
    
    def test_custom_config_dir(self):
        """Test using custom config directory."""
        manager = ConfigManager(Path("/custom/path"))
        assert manager.config_dir == Path("/custom/path")
        assert manager.config_file == Path("/custom/path/config.toml")
    
    def test_default_config_dir(self):
        """Test default config directory."""
        manager = ConfigManager()
        assert manager.config_dir == Path.home() / ".config" / "reminder-system"
    
    def test_default_general_config(self):
        """Test that ConfigManager has default GeneralConfig."""
        manager = ConfigManager()
        assert manager.general is not None
        assert manager.general.text_font == "Sans Serif"
    
    def test_load_config_file_not_found(self):
        """Test loading non-existent config file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ConfigManager(Path(tmpdir))
            with pytest.raises(FileNotFoundError):
                manager.load_config()
    
    def test_load_config_from_fixtures(self):
        """Test loading config from fixtures directory."""
        manager = ConfigManager(FIXTURES_DIR)
        reminders = manager.load_config()
        
        assert len(reminders) >= 1
        assert "test_reminder" in reminders
        
        # Check that general config was loaded
        assert manager.general is not None
    
    def test_load_config_with_general_settings(self):
        """Test that general settings are loaded from fixtures."""
        manager = ConfigManager(FIXTURES_DIR)
        manager.load_config()
        
        # The fixture has general settings
        assert manager.general.text_font == "Sans Serif"
        assert manager.general.text_size == 24
        assert manager.general.icon_scale == 1.0
        assert manager.general.max_opacity == 0.85
        assert manager.general.fade_in_duration == 2000
        assert manager.general.fade_out_duration == 500
    
    def test_load_config_reminder_with_text(self):
        """Test that reminder text is loaded from fixtures."""
        manager = ConfigManager(FIXTURES_DIR)
        reminders = manager.load_config()
        
        # The fixture has a test_reminder with text
        assert "test_reminder" in reminders
        assert reminders["test_reminder"].text == "Something something fr fr"
    
    def test_load_from_data(self):
        """Test loading reminders from pre-parsed data."""
        manager = ConfigManager(Path("/tmp"))
        config_data = {
            "my_reminder": {
                "schedule": "*/5 * * * *",
                "icon": "icon.png",
                "snooze_duration": 180,
                "text": "Custom reminder text"
            }
        }
        
        reminders = manager.load_from_data(config_data)
        
        assert len(reminders) == 1
        assert "my_reminder" in reminders
        assert reminders["my_reminder"].snooze_duration == 180
        assert reminders["my_reminder"].text == "Custom reminder text"
    
    def test_load_from_data_with_general(self):
        """Test loading general config from pre-parsed data."""
        manager = ConfigManager(Path("/tmp"))
        config_data = {
            "general": {
                "text_font": "Courier",
                "text_size": 18,
                "icon_scale": 0.8
            },
            "my_reminder": {
                "schedule": "*/5 * * * *",
                "icon": "icon.png"
            }
        }
        
        reminders = manager.load_from_data(config_data)
        
        assert len(reminders) == 1
        assert manager.general.text_font == "Courier"
        assert manager.general.text_size == 18
        assert manager.general.icon_scale == 0.8


class TestLoadConfigFile:
    """Tests for load_config_file function."""
    
    def test_load_valid_file(self):
        """Test loading a valid TOML file."""
        config_file = FIXTURES_DIR / "config.toml"
        if config_file.exists():
            data = load_config_file(config_file)
            assert isinstance(data, dict)
            assert "test_reminder" in data
    
    def test_load_nonexistent_file(self):
        """Test loading a file that doesn't exist."""
        with pytest.raises(FileNotFoundError):
            load_config_file(Path("/nonexistent/config.toml"))
