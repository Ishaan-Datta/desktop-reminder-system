"""Persistent key-value state store for the reminder system.

Stores runtime state (e.g. work-session operating mode) to a JSON file
on disk so that it survives service restarts and crashes.
"""

import json
import threading
from pathlib import Path
from typing import Any


# Keys and their default values
_DEFAULTS: dict[str, Any] = {
    "work_session_operating_mode": "automatic",  # "automatic" | "manual"
}


class PersistentState:
    """
    A persistent key-value store backed by a JSON file.

    Every mutation is immediately flushed to disk using
    atomic write-tmp-then-rename so no data is lost on crash.

    Thread-safe: all public methods acquire an internal lock.
    """

    def __init__(self, state_file: Path):
        """Initialise the state store and load any persisted values."""
        self.state_file = state_file
        self._data: dict[str, Any] = dict(_DEFAULTS)
        self._lock = threading.Lock()
        self._load()

    # ── Persistence ──────────────────────────────────────────────

    def _load(self):
        """Load state from disk on startup, merging with defaults."""
        if self.state_file.exists():
            try:
                with open(self.state_file, "r") as f:
                    stored = json.load(f)
                if isinstance(stored, dict):
                    self._data.update(stored)
                    print(f"Restored state from {self.state_file}")
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Could not load state file: {e}")

    def _save(self):
        """Persist state to disk atomically (write-tmp then rename)."""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            tmp_file = self.state_file.with_suffix(".tmp")
            with open(tmp_file, "w") as f:
                json.dump(self._data, f, indent=2)
            tmp_file.rename(self.state_file)
        except IOError as e:
            print(f"Warning: Could not save state file: {e}")

    # ── Public API ───────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        """Read a value.  Falls back to *default*, then ``_DEFAULTS``."""
        with self._lock:
            if key in self._data:
                return self._data[key]
            if key in _DEFAULTS:
                return _DEFAULTS[key]
            return default

    def set(self, key: str, value: Any) -> None:
        """Write a value and persist immediately."""
        with self._lock:
            self._data[key] = value
            self._save()

    def get_all(self) -> dict[str, Any]:
        """Return a shallow copy of all stored state."""
        with self._lock:
            return dict(self._data)

    def reset(self, key: str) -> None:
        """Reset a key back to its default (or remove it)."""
        with self._lock:
            if key in _DEFAULTS:
                self._data[key] = _DEFAULTS[key]
            else:
                self._data.pop(key, None)
            self._save()
