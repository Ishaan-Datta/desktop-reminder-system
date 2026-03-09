"""Unit tests for the scheduler module."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock

from reminder_system.scheduler import ReminderScheduler, ScheduledReminder


class TestScheduledReminder:
    """Tests for ScheduledReminder dataclass."""
    
    def test_calculate_next_run(self):
        """Test calculating next run time."""
        reminder = ScheduledReminder(
            name="test",
            cron_expressions=["* * * * *"],  # Every minute
            callback=Mock(),
            next_runs=[datetime.now()]
        )
        
        next_run = reminder.calculate_next_run()
        
        # Should be within the next minute
        assert next_run > datetime.now()
        assert next_run < datetime.now() + timedelta(minutes=2)
    
    def test_calculate_next_run_multiple_schedules(self):
        """Test that next_run returns the earliest across multiple schedules."""
        reminder = ScheduledReminder(
            name="test",
            cron_expressions=["0 * * * *", "30 * * * *"],  # On the hour and half-hour
            callback=Mock(),
            next_runs=[datetime.now(), datetime.now()]
        )
        
        next_run = reminder.calculate_next_run()
        
        # Should have two next_runs
        assert len(reminder.next_runs) == 2
        # next_run property should be the minimum
        assert next_run == min(reminder.next_runs)
    
    def test_snooze(self):
        """Test snoozing a reminder."""
        reminder = ScheduledReminder(
            name="test",
            cron_expressions=["0 * * * *"],
            callback=Mock(),
            next_runs=[datetime.now()]
        )
        
        snoozed_until = reminder.snooze(300)  # 5 minutes
        
        assert reminder.snoozed_until is not None
        assert snoozed_until > datetime.now()
        assert snoozed_until < datetime.now() + timedelta(seconds=310)
    
    def test_clear_snooze(self):
        """Test clearing snooze."""
        reminder = ScheduledReminder(
            name="test",
            cron_expressions=["* * * * *"],
            callback=Mock(),
            next_runs=[datetime.now()]
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
            cron_expressions=["0 * * * *"],
            callback=Mock(),
            next_runs=[next_run]
        )
        
        assert reminder.get_effective_next_run() == next_run
    
    def test_get_effective_next_run_with_snooze(self):
        """Test effective next run with active snooze."""
        next_run = datetime.now() + timedelta(hours=1)
        reminder = ScheduledReminder(
            name="test",
            cron_expressions=["0 * * * *"],
            callback=Mock(),
            next_runs=[next_run]
        )
        
        reminder.snooze(60)
        effective = reminder.get_effective_next_run()
        
        # Should return snooze time, not scheduled time
        assert effective < next_run
        assert effective > datetime.now()

    def test_get_effective_next_run_with_expired_snooze(self):
        """Expired snoozes remain due until the scheduler consumes them."""
        next_run = datetime.now() + timedelta(hours=1)
        expired_snooze = datetime.now() - timedelta(seconds=5)
        reminder = ScheduledReminder(
            name="test",
            cron_expressions=["0 * * * *"],
            callback=Mock(),
            next_runs=[next_run],
            snoozed_until=expired_snooze,
        )

        assert reminder.get_effective_next_run() == expired_snooze


class TestReminderScheduler:
    """Tests for ReminderScheduler class."""
    
    def test_add_reminder(self):
        """Test adding a reminder."""
        scheduler = ReminderScheduler()
        callback = Mock()
        
        scheduler.add_reminder("test", "0 * * * *", callback)
        
        assert "test" in scheduler.reminders
        assert scheduler.reminders["test"].name == "test"
        assert scheduler.reminders["test"].cron_expressions == ["0 * * * *"]
    
    def test_add_reminder_list_schedule(self):
        """Test adding a reminder with multiple schedules."""
        scheduler = ReminderScheduler()
        callback = Mock()
        
        scheduler.add_reminder("test", ["0 * * * *", "30 * * * *"], callback)
        
        assert "test" in scheduler.reminders
        assert scheduler.reminders["test"].cron_expressions == ["0 * * * *", "30 * * * *"]
        assert len(scheduler.reminders["test"].next_runs) == 2
    
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

    def test_snooze_reminder_clears_same_minute_trigger_guard(self):
        """Test snoozing allows a same-minute re-trigger after expiry."""
        scheduler = ReminderScheduler()
        scheduler.add_reminder("test", "0 * * * *", Mock())

        scheduler._triggered_this_minute.add("test")
        scheduler.snooze_reminder("test", 15)

        assert "test" not in scheduler._triggered_this_minute
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
        scheduler.add_reminder("test2", ["30 * * * *", "0 9 * * *"], Mock())
        
        status = scheduler.get_status()
        
        assert "test1" in status
        assert "test2" in status
        assert "next_run" in status["test1"]
        assert "effective_next" in status["test1"]
        assert "schedules" in status["test1"]
        assert status["test1"]["schedules"] == ["0 * * * *"]
        assert status["test2"]["schedules"] == ["30 * * * *", "0 9 * * *"]
    
    def test_get_snoozed_names(self):
        """Test getting names of snoozed reminders."""
        scheduler = ReminderScheduler()
        scheduler.add_reminder("test1", "0 * * * *", Mock())
        scheduler.add_reminder("test2", "30 * * * *", Mock())
        scheduler.add_reminder("test3", "15 * * * *", Mock())
        
        # No snoozes initially
        assert scheduler.get_snoozed_names() == set()
        
        # Snooze test1 and test3
        scheduler.snooze_reminder("test1", 120)
        scheduler.snooze_reminder("test3", 60)
        
        snoozed = scheduler.get_snoozed_names()
        assert snoozed == {"test1", "test3"}
    
    def test_start_stop(self):
        """Test starting and stopping the scheduler."""
        scheduler = ReminderScheduler()
        scheduler.add_reminder("test", "0 * * * *", Mock())
        
        scheduler.start()
        assert scheduler._running
        assert scheduler._thread is not None
        
        scheduler.stop()
        assert not scheduler._running
