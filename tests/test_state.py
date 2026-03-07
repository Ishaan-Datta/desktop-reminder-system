"""Unit tests for the PersistentState store."""

import json
import tempfile
from pathlib import Path

import pytest

from reminder_system.state import PersistentState


class TestPersistentState:
    """Tests for PersistentState key-value store."""

    def _make_state(self, tmp_path: Path) -> PersistentState:
        return PersistentState(tmp_path / "state.json")

    def test_defaults(self, tmp_path):
        """Fresh state returns built-in defaults."""
        state = self._make_state(tmp_path)
        assert state.get("work_session_operating_mode") == "automatic"

    def test_get_unknown_key(self, tmp_path):
        """Unknown key returns None (or explicit default)."""
        state = self._make_state(tmp_path)
        assert state.get("nonexistent") is None
        assert state.get("nonexistent", "fallback") == "fallback"

    def test_set_and_get(self, tmp_path):
        """Set then get returns the new value."""
        state = self._make_state(tmp_path)
        state.set("work_session_operating_mode", "manual")
        assert state.get("work_session_operating_mode") == "manual"

    def test_set_persists_to_disk(self, tmp_path):
        """Written values survive a fresh load from the same file."""
        path = tmp_path / "state.json"
        s1 = PersistentState(path)
        s1.set("work_session_operating_mode", "manual")

        # Reload from the same file
        s2 = PersistentState(path)
        assert s2.get("work_session_operating_mode") == "manual"

    def test_get_all(self, tmp_path):
        """get_all returns a dict with all keys."""
        state = self._make_state(tmp_path)
        state.set("custom_key", 42)
        data = state.get_all()
        assert "work_session_operating_mode" in data
        assert data["custom_key"] == 42

    def test_get_all_returns_copy(self, tmp_path):
        """Mutating the returned dict does not affect internal state."""
        state = self._make_state(tmp_path)
        data = state.get_all()
        data["work_session_operating_mode"] = "HACKED"
        assert state.get("work_session_operating_mode") == "automatic"

    def test_reset_known_key(self, tmp_path):
        """Resetting a known key restores the built-in default."""
        state = self._make_state(tmp_path)
        state.set("work_session_operating_mode", "manual")
        state.reset("work_session_operating_mode")
        assert state.get("work_session_operating_mode") == "automatic"

    def test_reset_unknown_key(self, tmp_path):
        """Resetting an unknown key removes it."""
        state = self._make_state(tmp_path)
        state.set("custom_key", "hello")
        state.reset("custom_key")
        assert state.get("custom_key") is None

    def test_handles_corrupt_file(self, tmp_path):
        """Corrupt JSON falls back to defaults without crashing."""
        path = tmp_path / "state.json"
        path.write_text("{invalid json!!")
        state = PersistentState(path)
        assert state.get("work_session_operating_mode") == "automatic"

    def test_handles_missing_file(self, tmp_path):
        """Missing file starts fresh with defaults."""
        path = tmp_path / "does_not_exist.json"
        state = PersistentState(path)
        assert state.get("work_session_operating_mode") == "automatic"

    def test_creates_parent_directories(self, tmp_path):
        """Deeply nested paths are created automatically."""
        path = tmp_path / "a" / "b" / "c" / "state.json"
        state = PersistentState(path)
        state.set("key", "value")
        assert path.exists()
        assert state.get("key") == "value"

    def test_atomic_write(self, tmp_path):
        """No .tmp file is left behind after a successful save."""
        path = tmp_path / "state.json"
        state = PersistentState(path)
        state.set("x", 1)
        assert not path.with_suffix(".tmp").exists()
        assert path.exists()
