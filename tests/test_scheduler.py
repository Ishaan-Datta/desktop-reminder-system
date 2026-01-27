"""Unit tests for the scheduler module."""

import pytest
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from reminder_system.scheduler import ReminderScheduler, ScheduledReminder


class TestScheduledReminder:
    """Tests for ScheduledReminder dataclass."""
    
    def test_calculate_next_run(self):
        """Test calculating next run time."""
        reminder = ScheduledReminder(
            name="test",
            cron_expression="* * * * *",  # Every minute
            callback=Mock(),
            next_run=datetime.now()
        )
        
        next_run = reminder.calculate_next_run()
        
        # Should be within the next minute
        assert next_run > datetime.now()
        assert next_run < datetime.now() + timedelta(minutes=2)
    
    def test_snooze(self):
        """Test snoozing a reminder."""
        reminder = ScheduledReminder(
            name="test",
            cron_expression="0 * * * *",
            callback=Mock(),
            next_run=datetime.now()
        )
        
        snoozed_until = reminder.snooze(300)  # 5 minutes
        
        assert reminder.snoozed_until is not None
        assert snoozed_until > datetime.now()
        assert snoozed_until < datetime.now() + timedelta(seconds=310)
    
    def test_clear_snooze(self):
        """Test clearing snooze."""
        reminder = ScheduledReminder(
            name="test",
            cron_expression="* * * * *",
            callback=Mock(),
            next_run=datetime.now()
        )
        
        reminder.snooze(60)
        assert reminder.snoozed_until is not None
        
        reminder.clear_snooze()
        assert reminder.snoozed_until is None
    
    def test_get_effective_next_run_no_snooze(self):
        """Test effective next run without snooze."""
        next_run = datetime.now() + timedelta(hours=1)
        reminder = ScheduledReminder(
            name="test",
            cron_expression="0 * * * *",
            callback=Mock(),
            next_run=next_run
        )
        
        assert reminder.get_effective_next_run() == next_run
    
    def test_get_effective_next_run_with_snooze(self):
        """Test effective next run with active snooze."""
        next_run = datetime.now() + timedelta(hours=1)
        reminder = ScheduledReminder(
            name="test",
            cron_expression="0 * * * *",
            callback=Mock(),
            next_run=next_run
        )
        
        reminder.snooze(60)
        effective = reminder.get_effective_next_run()
        
        # Should return snooze time, not scheduled time
        assert effective < next_run
        assert effective > datetime.now()


class TestReminderScheduler:
    """Tests for ReminderScheduler class."""
    
    def test_add_reminder(self):
        """Test adding a reminder."""
        scheduler = ReminderScheduler()
        callback = Mock()
        
        scheduler.add_reminder("test", "0 * * * *", callback)
        
        assert "test" in scheduler.reminders
        assert scheduler.reminders["test"].name == "test"
        assert scheduler.reminders["test"].cron_expression == "0 * * * *"
    
    def test_add_reminder_invalid_cron(self):
        """Test adding reminder with invalid cron expression."""
        scheduler = ReminderScheduler()
        
        with pytest.raises(ValueError, match="Invalid cron expression"):
            scheduler.add_reminder("test", "invalid cron", Mock())
    
    def test_remove_reminder(self):
        """Test removing a reminder."""
        scheduler = ReminderScheduler()
        scheduler.add_reminder("test", "0 * * * *", Mock())
        
        assert "test" in scheduler.reminders
        
        scheduler.remove_reminder("test")
        
        assert "test" not in scheduler.reminders
    
    def test_snooze_reminder(self):
        """Test snoozing a reminder."""
        scheduler = ReminderScheduler()
        scheduler.add_reminder("test", "0 * * * *", Mock())
        
        scheduler.snooze_reminder("test", 120)
        
        assert scheduler.reminders["test"].snoozed_until is not None
    
    def test_complete_reminder(self):
        """Test completing a reminder."""
        scheduler = ReminderScheduler()
        scheduler.add_reminder("test", "0 * * * *", Mock())
        scheduler.snooze_reminder("test", 60)
        
        scheduler.complete_reminder("test")
        
        assert scheduler.reminders["test"].snoozed_until is None
    
    def test_get_status(self):
        """Test getting scheduler status."""
        scheduler = ReminderScheduler()
        scheduler.add_reminder("test1", "0 * * * *", Mock())
        scheduler.add_reminder("test2", "30 * * * *", Mock())
        
        status = scheduler.get_status()
        
        assert "test1" in status
        assert "test2" in status
        assert "next_run" in status["test1"]
        assert "effective_next" in status["test1"]
    
    def test_start_stop(self):
        """Test starting and stopping the scheduler."""
        scheduler = ReminderScheduler()
        scheduler.add_reminder("test", "0 * * * *", Mock())
        
        scheduler.start()
        assert scheduler._running
        assert scheduler._thread is not None
        
        scheduler.stop()
        assert not scheduler._running
