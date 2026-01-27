"""Unit tests for the config module."""

import pytest
from pathlib import Path
import tempfile

from reminder_system.config import (
    ReminderConfig,
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


class TestParseConfigData:
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
        
        reminders = parse_config_data(config_data, Path("/config"))
        
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
        
        reminders = parse_config_data(config_data, Path("/config"))
        
        assert len(reminders) == 1
        assert "valid" in reminders


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
    
    def test_load_from_data(self):
        """Test loading reminders from pre-parsed data."""
        manager = ConfigManager(Path("/tmp"))
        config_data = {
            "my_reminder": {
                "schedule": "*/5 * * * *",
                "icon": "icon.png",
                "snooze_duration": 180
            }
        }
        
        reminders = manager.load_from_data(config_data)
        
        assert len(reminders) == 1
        assert "my_reminder" in reminders
        assert reminders["my_reminder"].snooze_duration == 180


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
