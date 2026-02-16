"""Tray panel window for the reminder system.

A small dark-themed panel accessible from the system tray icon.
Contains three switchable pages: Controls, Upcoming, and Queue.
"""

import time
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from PyQt6.QtCore import Qt, QTimer, QRect
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QStackedWidget, QScrollArea, QFrame,
    QApplication,
)

if TYPE_CHECKING:
    from .app import ReminderApp


STYLE = """
QWidget#TrayWindow {
    background: #2b2b2b;
    border: 1px solid #555;
    border-radius: 8px;
}

QLabel {
    color: #e0e0e0;
    background: transparent;
}

QLabel#header {
    font-size: 14px;
    font-weight: bold;
    color: #ffffff;
}

QLabel#section {
    font-size: 12px;
    font-weight: bold;
    color: #9e9e9e;
    padding-top: 8px;
}

QLabel#status {
    font-size: 11px;
    color: #9e9e9e;
}

QPushButton#navBtn {
    background: #3a3a3a;
    color: #b0b0b0;
    border: none;
    border-radius: 4px;
    padding: 6px 12px;
    font-size: 12px;
    font-weight: bold;
}

QPushButton#navBtn:hover {
    background: #4a4a4a;
}

QPushButton#navBtnActive {
    background: #4CAF50;
    color: #ffffff;
    border: none;
    border-radius: 4px;
    padding: 6px 12px;
    font-size: 12px;
    font-weight: bold;
}

QPushButton#actionBtn {
    background: #3a3a3a;
    color: #e0e0e0;
    border: 1px solid #555;
    border-radius: 6px;
    padding: 10px 16px;
    font-size: 13px;
    text-align: left;
}

QPushButton#actionBtn:hover {
    background: #4a4a4a;
    border-color: #777;
}

QPushButton#toggleOn {
    background: #2E7D32;
    color: #ffffff;
    border: 1px solid #4CAF50;
    border-radius: 6px;
    padding: 10px 16px;
    font-size: 13px;
    text-align: left;
}

QPushButton#toggleOn:hover {
    background: #388E3C;
}

QPushButton#dangerBtn {
    background: #3a3a3a;
    color: #ef5350;
    border: 1px solid #555;
    border-radius: 6px;
    padding: 10px 16px;
    font-size: 13px;
    text-align: left;
}

QPushButton#dangerBtn:hover {
    background: #4a4a4a;
    border-color: #ef5350;
}

QScrollArea {
    background: transparent;
    border: none;
}

QWidget#scrollContent {
    background: transparent;
}

QFrame#card {
    background: #333333;
    border: 1px solid #444;
    border-radius: 6px;
}
"""


class TrayWindow(QWidget):
    """
    Panel window shown from the system tray icon.

    Three switchable pages:
      0 – Controls  : snooze toggle, clear queue, lock status
      1 – Upcoming  : next scheduled reminders sorted by time
      2 – Queue     : currently queued reminders in order
    """

    PAGE_CONTROLS = 0
    PAGE_UPCOMING = 1
    PAGE_QUEUE = 2

    def __init__(self, app: "ReminderApp", parent=None):
        super().__init__(parent)
        self._app = app
        self._current_page = self.PAGE_CONTROLS
        self._last_hide_time: float = 0.0

        self.setWindowTitle("Reminder System")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setFixedSize(340, 400)
        self.setObjectName("TrayWindow")
        self.setStyleSheet(STYLE)

        self._setup_ui()

        # Refresh visible page once per second while the window is shown
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(1000)
        self._refresh_timer.timeout.connect(self._refresh_current_page)

    # ── UI setup ─────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # Header
        header = QLabel("⏰  Reminder System")
        header.setObjectName("header")
        root.addWidget(header)

        # Navigation bar
        nav = QHBoxLayout()
        nav.setSpacing(4)
        self._nav_buttons: list[QPushButton] = []
        for label, idx in [("Controls", 0), ("Upcoming", 1), ("Queue", 2)]:
            btn = QPushButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _checked, i=idx: self._switch_page(i))
            nav.addWidget(btn)
            self._nav_buttons.append(btn)
        root.addLayout(nav)

        # Page stack
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_controls_page())
        self._stack.addWidget(self._build_upcoming_page())
        self._stack.addWidget(self._build_queue_page())
        root.addWidget(self._stack)

        self._update_nav_style()

    # ── Page builders ────────────────────────────────────────────

    def _build_controls_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(8)

        # Snooze toggle button
        self._snooze_btn = QPushButton("⏸  Snooze  —  OFF")
        self._snooze_btn.setObjectName("actionBtn")
        self._snooze_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._snooze_btn.clicked.connect(self._toggle_snooze)
        layout.addWidget(self._snooze_btn)

        # Clear queue button
        self._clear_btn = QPushButton("🗑  Clear Queue")
        self._clear_btn.setObjectName("dangerBtn")
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_btn.clicked.connect(self._clear_queue)
        layout.addWidget(self._clear_btn)

        # Status section
        section = QLabel("Status")
        section.setObjectName("section")
        layout.addWidget(section)

        self._status_label = QLabel()
        self._status_label.setObjectName("status")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        layout.addStretch()
        return page

    def _build_upcoming_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._upcoming_container = QWidget()
        self._upcoming_container.setObjectName("scrollContent")
        self._upcoming_layout = QVBoxLayout(self._upcoming_container)
        self._upcoming_layout.setContentsMargins(0, 0, 0, 0)
        self._upcoming_layout.setSpacing(6)
        self._upcoming_layout.addStretch()

        scroll.setWidget(self._upcoming_container)
        layout.addWidget(scroll)
        return page

    def _build_queue_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._queue_container = QWidget()
        self._queue_container.setObjectName("scrollContent")
        self._queue_layout = QVBoxLayout(self._queue_container)
        self._queue_layout.setContentsMargins(0, 0, 0, 0)
        self._queue_layout.setSpacing(6)
        self._queue_layout.addStretch()

        scroll.setWidget(self._queue_container)
        layout.addWidget(scroll)
        return page

    # ── Navigation ───────────────────────────────────────────────

    def _switch_page(self, index: int):
        self._current_page = index
        self._stack.setCurrentIndex(index)
        self._update_nav_style()
        self._refresh_current_page()

    def _update_nav_style(self):
        for i, btn in enumerate(self._nav_buttons):
            btn.setObjectName("navBtnActive" if i == self._current_page else "navBtn")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    # ── Refresh logic ────────────────────────────────────────────

    def _refresh_current_page(self):
        page = self._current_page
        if page == self.PAGE_CONTROLS:
            self._refresh_controls()
        elif page == self.PAGE_UPCOMING:
            self._refresh_upcoming()
        elif page == self.PAGE_QUEUE:
            self._refresh_queue()

    def _refresh_controls(self):
        # Snooze toggle visual state
        lock_dir = Path(self._app.config_manager.general.lock_dir)
        own_lock = lock_dir / "reminder-system_snooze.lock"
        is_on = own_lock.exists()

        if is_on:
            self._snooze_btn.setText("⏸  Snooze  —  ON")
            self._snooze_btn.setObjectName("toggleOn")
        else:
            self._snooze_btn.setText("⏸  Snooze  —  OFF")
            self._snooze_btn.setObjectName("actionBtn")
        self._snooze_btn.style().unpolish(self._snooze_btn)
        self._snooze_btn.style().polish(self._snooze_btn)

        # Queue count
        qsize = self._app._queue.size() if self._app._queue else 0
        self._clear_btn.setText(
            f"🗑  Clear Queue  ({qsize} item{'s' if qsize != 1 else ''})"
        )

        # Lock status
        snooze_names = getattr(self._app, "_snooze_lock_names", [])
        cancel_names = getattr(self._app, "_cancel_lock_names", [])

        lines: list[str] = []
        if cancel_names:
            names = ", ".join(n if n else "(unnamed)" for n in cancel_names)
            lines.append(f"🚫 Cancel locks: {names}")
        if snooze_names:
            names = ", ".join(n if n else "(unnamed)" for n in snooze_names)
            lines.append(f"⏸ Snooze locks: {names}")
        if not lines:
            lines.append("✅ No active locks")

        self._status_label.setText("\n".join(lines))

    def _refresh_upcoming(self):
        self._clear_layout(self._upcoming_layout)

        status = self._app.scheduler.get_status()
        if not status:
            lbl = QLabel("No reminders scheduled")
            lbl.setObjectName("status")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._upcoming_layout.insertWidget(0, lbl)
            return

        # Sort by effective next run time
        sorted_items = sorted(
            status.items(), key=lambda kv: kv[1]["effective_next"]
        )

        for i, (name, info) in enumerate(sorted_items):
            card = self._make_upcoming_card(name, info)
            self._upcoming_layout.insertWidget(i, card)

    def _refresh_queue(self):
        self._clear_layout(self._queue_layout)

        items = self._app._queue.get_all() if self._app._queue else []
        if not items:
            lbl = QLabel("No queued reminders")
            lbl.setObjectName("status")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._queue_layout.insertWidget(0, lbl)
            return

        for i, name in enumerate(items):
            card = QFrame()
            card.setObjectName("card")
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(10, 8, 10, 8)

            pos_label = QLabel(f"#{i + 1}")
            pos_label.setStyleSheet(
                "color: #9e9e9e; font-size: 12px; font-weight: bold;"
            )
            pos_label.setFixedWidth(28)
            card_layout.addWidget(pos_label)

            name_label = QLabel(name)
            name_label.setStyleSheet("color: #e0e0e0; font-size: 13px;")
            card_layout.addWidget(name_label)

            self._queue_layout.insertWidget(i, card)

    # ── Helpers ──────────────────────────────────────────────────

    def _make_upcoming_card(self, name: str, info: dict) -> QFrame:
        """Build a card widget for an upcoming reminder."""
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(10, 8, 10, 8)
        card_layout.setSpacing(2)

        name_label = QLabel(name)
        name_label.setStyleSheet(
            "color: #e0e0e0; font-size: 13px; font-weight: bold;"
        )
        card_layout.addWidget(name_label)

        # Relative time string
        try:
            effective = datetime.fromisoformat(info["effective_next"])
            delta = effective - datetime.now()
            total_seconds = int(delta.total_seconds())

            if total_seconds < 0:
                time_str = "due now"
            elif total_seconds < 60:
                time_str = f"in {total_seconds}s"
            elif total_seconds < 3600:
                mins = total_seconds // 60
                time_str = f"in {mins}m"
            else:
                hours = total_seconds // 3600
                mins = (total_seconds % 3600) // 60
                time_str = f"in {hours}h {mins}m"

            time_label = QLabel(
                f"Next: {effective.strftime('%H:%M')}  ({time_str})"
            )
        except (ValueError, KeyError):
            time_label = QLabel(f"Next: {info.get('effective_next', '?')}")

        time_label.setStyleSheet("color: #9e9e9e; font-size: 11px;")
        card_layout.addWidget(time_label)

        if info.get("snoozed_until"):
            snooze_label = QLabel("⏳ Snoozed")
            snooze_label.setStyleSheet("color: #FFA726; font-size: 11px;")
            card_layout.addWidget(snooze_label)

        return card

    def _clear_layout(self, layout):
        """Remove all widgets from a layout except the final stretch."""
        while layout.count() > 1:
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    # ── Actions ──────────────────────────────────────────────────

    def _toggle_snooze(self):
        """Toggle the reminder-system snooze lock file."""
        lock_dir = Path(self._app.config_manager.general.lock_dir)
        lock_file = lock_dir / "reminder-system_snooze.lock"

        if lock_file.exists():
            lock_file.unlink()
            print("Tray: snooze lock removed")
        else:
            lock_dir.mkdir(parents=True, exist_ok=True)
            lock_file.touch()
            print("Tray: snooze lock created")

        self._refresh_controls()

    def _clear_queue(self):
        """Clear all queued reminders."""
        if self._app._queue:
            count = self._app._queue.size()
            self._app._queue.clear()
            print(f"Tray: cleared {count} queued reminder(s)")
        self._refresh_controls()

    # ── Visibility ───────────────────────────────────────────────

    def toggle_visibility(self, tray_geometry: Optional[QRect] = None):
        """Show or hide the window, positioning near the tray icon."""
        if self.isVisible():
            self.hide()
            return

        # Avoid reopening immediately after an auto-hide triggered by
        # the same tray-icon click (deactivation arrives before the
        # activated signal).
        if time.monotonic() - self._last_hide_time < 0.3:
            return

        # Position near tray icon
        if tray_geometry and not tray_geometry.isNull():
            screen = QApplication.primaryScreen()
            if screen:
                sg = screen.availableGeometry()
                cx = tray_geometry.center().x()
                x = max(sg.left(), min(cx - self.width() // 2, sg.right() - self.width()))

                # Show above tray if it's in the lower half, else below
                if tray_geometry.top() > sg.height() // 2:
                    y = tray_geometry.top() - self.height() - 4
                else:
                    y = tray_geometry.bottom() + 4
                y = max(sg.top(), min(y, sg.bottom() - self.height()))
                self.move(x, y)

        self.show()
        self.raise_()
        self.activateWindow()
        self._refresh_current_page()
        self._refresh_timer.start()

    # ── Events ───────────────────────────────────────────────────

    def hideEvent(self, event):
        self._refresh_timer.stop()
        self._last_hide_time = time.monotonic()
        super().hideEvent(event)

    def changeEvent(self, event):
        """Auto-hide when the window loses activation (user clicks away)."""
        if (
            event.type() == event.Type.ActivationChange
            and not self.isActiveWindow()
        ):
            self.hide()
        super().changeEvent(event)

    def keyPressEvent(self, event):
        """Close on Escape."""
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)
