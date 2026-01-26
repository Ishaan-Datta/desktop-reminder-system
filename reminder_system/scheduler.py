"""Cron-based scheduler for reminders."""

import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Callable, Optional
from dataclasses import dataclass

from croniter import croniter


@dataclass
class ScheduledReminder:
    """A scheduled reminder with its next run time."""
    name: str
    cron_expression: str
    callback: Callable[[str], None]
    next_run: datetime
    snoozed_until: Optional[datetime] = None
    
    def calculate_next_run(self) -> datetime:
        """Calculate the next run time based on the cron expression."""
        cron = croniter(self.cron_expression, datetime.now())
        self.next_run = cron.get_next(datetime)
        return self.next_run
    
    def snooze(self, seconds: int) -> datetime:
        """Snooze the reminder for the specified duration."""
        self.snoozed_until = datetime.now() + timedelta(seconds=seconds)
        return self.snoozed_until
    
    def clear_snooze(self):
        """Clear the snooze and recalculate next run."""
        self.snoozed_until = None
        self.calculate_next_run()
    
    def get_effective_next_run(self) -> datetime:
        """Get the effective next run time considering snooze."""
        if self.snoozed_until and self.snoozed_until > datetime.now():
            return self.snoozed_until
        return self.next_run


class ReminderScheduler:
    """
    Scheduler that triggers reminders based on cron expressions.
    
    Uses a background thread to check for due reminders.
    """
    
    CHECK_INTERVAL = 1.0  # Check every second
    
    def __init__(self):
        self.reminders: Dict[str, ScheduledReminder] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._triggered_this_minute: set = set()
        self._last_minute: Optional[int] = None
    
    def add_reminder(
        self, 
        name: str, 
        cron_expression: str, 
        callback: Callable[[str], None]
    ) -> None:
        """
        Add a reminder to the scheduler.
        
        Args:
            name: Unique name for the reminder
            cron_expression: Cron expression for scheduling
            callback: Function to call when reminder triggers
        """
        # Validate cron expression
        if not croniter.is_valid(cron_expression):
            raise ValueError(f"Invalid cron expression: {cron_expression}")
        
        cron = croniter(cron_expression, datetime.now())
        next_run = cron.get_next(datetime)
        
        with self._lock:
            self.reminders[name] = ScheduledReminder(
                name=name,
                cron_expression=cron_expression,
                callback=callback,
                next_run=next_run
            )
        
        print(f"Scheduled reminder '{name}' - next run: {next_run}")
    
    def remove_reminder(self, name: str) -> None:
        """Remove a reminder from the scheduler."""
        with self._lock:
            if name in self.reminders:
                del self.reminders[name]
    
    def snooze_reminder(self, name: str, seconds: int) -> None:
        """Snooze a reminder for the specified duration."""
        with self._lock:
            if name in self.reminders:
                snoozed_until = self.reminders[name].snooze(seconds)
                print(f"Snoozed '{name}' until {snoozed_until}")
    
    def complete_reminder(self, name: str) -> None:
        """Mark a reminder as complete and schedule next occurrence."""
        with self._lock:
            if name in self.reminders:
                self.reminders[name].clear_snooze()
                next_run = self.reminders[name].next_run
                print(f"Completed '{name}' - next run: {next_run}")
    
    def start(self) -> None:
        """Start the scheduler background thread."""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        print("Scheduler started")
    
    def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        print("Scheduler stopped")
    
    def _run_loop(self) -> None:
        """Main scheduler loop."""
        while self._running:
            now = datetime.now()
            current_minute = now.minute
            
            # Reset triggered set when minute changes
            if self._last_minute != current_minute:
                self._triggered_this_minute.clear()
                self._last_minute = current_minute
            
            with self._lock:
                for name, reminder in list(self.reminders.items()):
                    # Skip if already triggered this minute
                    if name in self._triggered_this_minute:
                        continue
                    
                    effective_time = reminder.get_effective_next_run()
                    
                    # Check if reminder is due
                    if now >= effective_time:
                        self._triggered_this_minute.add(name)
                        
                        # Clear snooze if it was a snoozed trigger
                        if reminder.snoozed_until:
                            reminder.snoozed_until = None
                        
                        # Calculate next regular run
                        reminder.calculate_next_run()
                        
                        # Trigger callback in separate thread to not block scheduler
                        threading.Thread(
                            target=reminder.callback,
                            args=(name,),
                            daemon=True
                        ).start()
            
            time.sleep(self.CHECK_INTERVAL)
    
    def get_status(self) -> Dict[str, dict]:
        """Get the status of all scheduled reminders."""
        status = {}
        with self._lock:
            for name, reminder in self.reminders.items():
                status[name] = {
                    "next_run": reminder.next_run.isoformat(),
                    "snoozed_until": reminder.snoozed_until.isoformat() if reminder.snoozed_until else None,
                    "effective_next": reminder.get_effective_next_run().isoformat()
                }
        return status
