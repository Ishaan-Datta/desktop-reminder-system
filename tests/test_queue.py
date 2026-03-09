"""Unit tests for the persistent reminder queue."""

import json
import pytest

from reminder_system.queue import PersistentReminderQueue


class TestPersistentReminderQueue:
    """Tests for PersistentReminderQueue."""
    
    @pytest.fixture
    def queue_file(self, tmp_path):
        """Provide a temporary queue file path."""
        return tmp_path / "queue.json"
    
    @pytest.fixture
    def queue(self, queue_file):
        """Provide a fresh PersistentReminderQueue."""
        return PersistentReminderQueue(queue_file)
    
    # ── Basic operations ─────────────────────────────────────────
    
    def test_new_queue_is_empty(self, queue):
        """A freshly created queue should be empty."""
        assert queue.is_empty()
        assert queue.size() == 0
        assert queue.peek() is None
        assert queue.get_all() == []
    
    def test_push_back(self, queue):
        """push_back adds items to the end."""
        queue.push_back("a")
        queue.push_back("b")
        queue.push_back("c")
        
        assert queue.size() == 3
        assert queue.get_all() == ["a", "b", "c"]
    
    def test_push_front(self, queue):
        """push_front adds items to the beginning."""
        queue.push_back("a")
        queue.push_back("b")
        queue.push_front("z")
        
        assert queue.get_all() == ["z", "a", "b"]
    
    def test_pop_returns_front(self, queue):
        """pop removes and returns the front item."""
        queue.push_back("a")
        queue.push_back("b")
        queue.push_back("c")
        
        assert queue.pop() == "a"
        assert queue.pop() == "b"
        assert queue.pop() == "c"
        assert queue.pop() is None
    
    def test_peek_does_not_remove(self, queue):
        """peek returns the front item without removing it."""
        queue.push_back("a")
        
        assert queue.peek() == "a"
        assert queue.peek() == "a"
        assert queue.size() == 1
    
    def test_remove_specific_item(self, queue):
        """remove deletes a specific item by name."""
        queue.push_back("a")
        queue.push_back("b")
        queue.push_back("c")
        
        queue.remove("b")
        
        assert queue.get_all() == ["a", "c"]
    
    def test_remove_nonexistent_item(self, queue):
        """remove is a no-op for items not in the queue."""
        queue.push_back("a")
        queue.remove("nonexistent")
        
        assert queue.get_all() == ["a"]
    
    def test_clear(self, queue):
        """clear removes all items."""
        queue.push_back("a")
        queue.push_back("b")
        queue.clear()
        
        assert queue.is_empty()
        assert queue.size() == 0
    
    # ── Duplicate prevention ─────────────────────────────────────
    
    def test_push_back_ignores_duplicates(self, queue):
        """push_back silently ignores items already in the queue."""
        queue.push_back("a")
        queue.push_back("a")
        queue.push_back("a")
        
        assert queue.size() == 1
    
    def test_push_front_ignores_duplicates(self, queue):
        """push_front silently ignores items already in the queue."""
        queue.push_back("a")
        queue.push_front("a")
        
        assert queue.size() == 1
        # Original position is preserved (not moved to front)
        assert queue.get_all() == ["a"]
    
    # ── Persistence ──────────────────────────────────────────────
    
    def test_persists_to_disk(self, queue, queue_file):
        """Queue state is written to disk after each mutation."""
        queue.push_back("a")
        queue.push_back("b")
        
        # Read the JSON file directly
        with open(queue_file, "r") as f:
            data = json.load(f)
        
        assert data["queue"] == ["a", "b"]
    
    def test_survives_restart(self, queue_file):
        """A new queue instance restores state from the same file."""
        q1 = PersistentReminderQueue(queue_file)
        q1.push_back("x")
        q1.push_back("y")
        q1.push_back("z")
        
        # Simulate restart by creating a new instance
        q2 = PersistentReminderQueue(queue_file)
        
        assert q2.get_all() == ["x", "y", "z"]
        assert q2.size() == 3
    
    def test_pop_persists(self, queue_file):
        """pop is persisted — items don't reappear after restart."""
        q1 = PersistentReminderQueue(queue_file)
        q1.push_back("a")
        q1.push_back("b")
        q1.pop()  # removes "a"
        
        q2 = PersistentReminderQueue(queue_file)
        assert q2.get_all() == ["b"]
    
    def test_clear_persists(self, queue_file):
        """clear is persisted — queue stays empty after restart."""
        q1 = PersistentReminderQueue(queue_file)
        q1.push_back("a")
        q1.clear()
        
        q2 = PersistentReminderQueue(queue_file)
        assert q2.is_empty()
    
    def test_handles_corrupt_file(self, queue_file):
        """Gracefully handles a corrupt/invalid queue file."""
        queue_file.parent.mkdir(parents=True, exist_ok=True)
        queue_file.write_text("not valid json {{{")
        
        q = PersistentReminderQueue(queue_file)
        
        assert q.is_empty()
    
    def test_handles_missing_queue_key(self, queue_file):
        """Gracefully handles a JSON file without a 'queue' key."""
        queue_file.parent.mkdir(parents=True, exist_ok=True)
        queue_file.write_text('{"other_key": 123}')
        
        q = PersistentReminderQueue(queue_file)
        
        assert q.is_empty()
    
    def test_creates_parent_directories(self, tmp_path):
        """Queue file parent directories are created if they don't exist."""
        deep_path = tmp_path / "a" / "b" / "c" / "queue.json"
        q = PersistentReminderQueue(deep_path)
        q.push_back("test")
        
        assert deep_path.exists()
    
    # ── Ordering ─────────────────────────────────────────────────
    
    def test_push_front_then_back_ordering(self, queue):
        """Mixed push_front and push_back maintain expected order."""
        queue.push_back("b")
        queue.push_back("c")
        queue.push_front("a")
        queue.push_back("d")
        
        assert queue.get_all() == ["a", "b", "c", "d"]
    
    def test_get_all_returns_copy(self, queue):
        """get_all returns a copy, not a reference to the internal list."""
        queue.push_back("a")
        items = queue.get_all()
        items.append("b")
        
        assert queue.get_all() == ["a"]
