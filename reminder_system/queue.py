"""Persistent reminder queue for crash resilience.

Stores queued reminder names to a JSON file on disk so that
the queue survives service restarts and crashes.
"""

import json
import threading
from pathlib import Path
from typing import List, Optional


class PersistentReminderQueue:
    """
    A persistent FIFO queue of reminder names backed by a JSON file.

    Every mutation (push/pop/remove/clear) is immediately flushed to disk
    using atomic rename so that no data is lost on crash.

    Thread-safe: all public methods acquire an internal lock.
    """

    def __init__(self, queue_file: Path):
        """Initialise the queue and load any persisted reminder names."""
        self.queue_file = queue_file
        self._queue: List[str] = []
        self._lock = threading.Lock()
        self._load()

    # ── Persistence ──────────────────────────────────────────────

    def _load(self):
        """Load queue from disk on startup."""
        if self.queue_file.exists():
            try:
                with open(self.queue_file, "r") as f:
                    data = json.load(f)
                    self._queue = data.get("queue", [])
                if self._queue:
                    print(
                        f"Restored {len(self._queue)} queued reminders from disk: {self._queue}"
                    )
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Could not load queue file: {e}")
                self._queue = []

    def _save(self):
        """Persist queue to disk atomically (write-tmp then rename)."""
        try:
            self.queue_file.parent.mkdir(parents=True, exist_ok=True)
            tmp_file = self.queue_file.with_suffix(".tmp")
            with open(tmp_file, "w") as f:
                json.dump({"queue": self._queue}, f, indent=2)
            tmp_file.rename(self.queue_file)
        except IOError as e:
            print(f"Warning: Could not save queue file: {e}")

    # ── Queue operations ─────────────────────────────────────────

    def push_front(self, name: str):
        """Add a reminder to the *front* of the queue (highest priority).

        Used when the snooze lock file defers a reminder.
        Duplicates are silently ignored.
        """
        with self._lock:
            if name not in self._queue:
                self._queue.insert(0, name)
                self._save()

    def push_back(self, name: str):
        """Add a reminder to the *back* of the queue.

        Used when the overlay is already showing another reminder.
        Duplicates are silently ignored.
        """
        with self._lock:
            if name not in self._queue:
                self._queue.append(name)
                self._save()

    def pop(self) -> Optional[str]:
        """Remove and return the first (highest-priority) reminder, or None."""
        with self._lock:
            if self._queue:
                name = self._queue.pop(0)
                self._save()
                return name
            return None

    def peek(self) -> Optional[str]:
        """Return the first reminder without removing it, or None."""
        with self._lock:
            return self._queue[0] if self._queue else None

    def remove(self, name: str):
        """Remove a specific reminder from the queue (if present)."""
        with self._lock:
            if name in self._queue:
                self._queue.remove(name)
                self._save()

    def is_empty(self) -> bool:
        """Check whether the queue has no items."""
        with self._lock:
            return len(self._queue) == 0

    def size(self) -> int:
        """Return the number of items in the queue."""
        with self._lock:
            return len(self._queue)

    def get_all(self) -> List[str]:
        """Return a *copy* of all queued reminder names (front-to-back)."""
        with self._lock:
            return list(self._queue)

    def clear(self):
        """Remove all items and persist the empty queue."""
        with self._lock:
            self._queue.clear()
            self._save()
