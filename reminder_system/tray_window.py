"""Tray panel window for the reminder system.

A small dark-themed panel accessible from the system tray icon.
Contains three switchable pages: Controls, Upcoming, and Queue.
"""

import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from PyQt6.QtCore import Qt, QTimer, QRect, QSize, QEvent
from PyQt6.QtGui import QCursor, QGuiApplication, QIcon
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QStackedWidget, QScrollArea, QFrame,
    QApplication, QSizePolicy, QStyle,
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
    min-height: 20px;
    max-height: 20px;
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
    min-height: 20px;
    max-height: 20px;
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
    min-height: 20px;
    max-height: 20px;
    font-size: 13px;
    text-align: left;
}

QPushButton#dangerBtn:hover {
    background: #4a4a4a;
    border-color: #ef5350;
}

QPushButton#disabledBtn {
    background: #2e2e2e;
    color: #666;
    border: 1px solid #3a3a3a;
    border-radius: 6px;
    padding: 10px 16px;
    min-height: 20px;
    max-height: 20px;
    font-size: 13px;
    text-align: left;
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


CONTROL_BUTTON_HEIGHT = 42
CONTROL_BUTTON_ICON_SIZE = QSize(18, 18)
CONTROL_BUTTON_ICON_WIDTH = 22

# Change this single value to quickly try a different icon pack mapping.
# Each candidate below may be either an icon-theme name or a file path.
ACTIVE_CONTROL_ICON_THEME = "system-symbolic"

CONTROL_BUTTON_ICON_THEMES: dict[str, dict[str, tuple[str, ...]]] = {
    "system-symbolic": {
        "pause": (
            "media-playback-pause-symbolic",
            "media-playback-pause",
        ),
        "play": (
            "media-playback-start-symbolic",
            "media-playback-start",
        ),
        "settings": (
            "settings-symbolic",
            "settings-configure-symbolic",
            "settings-configure",
            "preferences-system-symbolic",
            "preferences-system",
        ),
        "lock-open": (
            "lock-open-symbolic",
            "object-unlocked-symbolic",
            "lock-open",
        ),
    },
    "material-symbols-outlined": {
        "pause": (
            "pause_circle",
            "pause",
            "media-playback-pause-symbolic",
        ),
        "play": (
            "play_circle",
            "play_arrow",
            "media-playback-start-symbolic",
        ),
        "settings": (
            "settings",
            "tune",
            "settings-symbolic",
        ),
        "lock-open": (
            "lock_open",
            "lock_open_right",
            "lock-open-symbolic",
        ),
    },
}

CONTROL_BUTTON_ICON_FALLBACKS: dict[str, QStyle.StandardPixmap] = {
    "pause": QStyle.StandardPixmap.SP_MediaPause,
    "play": QStyle.StandardPixmap.SP_MediaPlay,
    "settings": QStyle.StandardPixmap.SP_FileDialogDetailedView,
    "lock-open": QStyle.StandardPixmap.SP_DialogResetButton,
}


def _load_icon_candidate(candidate: str) -> QIcon:
    """Load an icon from a theme name or from a file path."""
    path = Path(candidate).expanduser()
    if path.suffix or path.is_absolute() or "/" in candidate:
        if not path.is_absolute():
            path = Path(__file__).resolve().parent.parent / path
        if path.exists():
            return QIcon(str(path))
    return QIcon.fromTheme(candidate)


def _resolve_control_icon(icon_name: str, style: Optional[QStyle]) -> QIcon:
    """Resolve the configured icon for a logical tray-button icon name."""
    theme = CONTROL_BUTTON_ICON_THEMES.get(
        ACTIVE_CONTROL_ICON_THEME,
        CONTROL_BUTTON_ICON_THEMES["system-symbolic"],
    )

    for candidate in theme.get(icon_name, ()):
        icon = _load_icon_candidate(candidate)
        if not icon.isNull():
            return icon

    fallback = CONTROL_BUTTON_ICON_FALLBACKS.get(icon_name)
    if fallback is not None and style is not None:
        return style.standardIcon(fallback)

    return QIcon()


class ControlButton(QPushButton):
    """Push button with a fixed-size icon slot and centered label text."""

    _TEXT_COLORS = {
        "actionBtn": "#e0e0e0",
        "toggleOn": "#ffffff",
        "dangerBtn": "#ef5350",
        "disabledBtn": "#666666",
    }

    def __init__(self, icon_name: str, label: str, parent=None):
        super().__init__(parent)
        self._icon_name = icon_name
        self._label = label

        self.setText("")
        self.setFixedHeight(CONTROL_BUTTON_HEIGHT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(8)

        self._icon_label = QLabel(self)
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_label.setFixedWidth(CONTROL_BUTTON_ICON_WIDTH)
        self._icon_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._text_label = QLabel(label, self)
        self._text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._text_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self._text_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._right_spacer = QWidget(self)
        self._right_spacer.setFixedWidth(CONTROL_BUTTON_ICON_WIDTH)
        self._right_spacer.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        layout.addWidget(self._icon_label)
        layout.addWidget(self._text_label, 1)
        layout.addWidget(self._right_spacer)

        self._sync_label_appearance()
        self._sync_icon()

    def set_content(self, icon_name: str, label: str):
        self._icon_name = icon_name
        self._label = label
        self._text_label.setText(label)
        self.setAccessibleName(label)
        self._sync_icon()

    def setObjectName(self, name: str):
        super().setObjectName(name)
        if hasattr(self, "_text_label"):
            self._sync_label_appearance()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.EnabledChange and hasattr(self, "_icon_label"):
            self._sync_icon()

    def _sync_icon(self):
        icon = _resolve_control_icon(self._icon_name, self.style())
        mode = QIcon.Mode.Normal if self.isEnabled() else QIcon.Mode.Disabled
        pixmap = icon.pixmap(CONTROL_BUTTON_ICON_SIZE, mode)
        self._icon_label.setPixmap(pixmap)

    def _sync_label_appearance(self):
        color = self._TEXT_COLORS.get(self.objectName(), "#e0e0e0")

        font = self.font()
        self._text_label.setFont(font)

        label_style = f"color: {color}; background: transparent;"
        self._text_label.setStyleSheet(label_style)


class TrayWindow(QWidget):
    """
    Panel window shown from the system tray icon.

    Three switchable pages:
      0 – Upcoming  : next scheduled reminders sorted by time
      1 – Queue     : currently queued reminders in order
      2 – Controls  : snooze toggle, clear queue, lock status
    """

    PAGE_UPCOMING = 0
    PAGE_QUEUE = 1
    PAGE_CONTROLS = 2

    def __init__(self, app: "ReminderApp", parent=None):
        super().__init__(parent)
        self._app = app
        self._current_page = self.PAGE_UPCOMING
        self._last_hide_time: float = 0.0

        self.setWindowTitle("Reminder System")
        self.setWindowFlags(
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setFixedSize(340, 400)
        self.setObjectName("TrayWindow")
        self.setStyleSheet(STYLE)

        self._setup_ui()

        # Refresh visible page once per second while the window is shown
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(1000)
        self._refresh_timer.timeout.connect(self._refresh_current_page)

    def _compute_target_position(self, tray_geometry: Optional[QRect] = None) -> Optional[tuple[int, int]]:
        """Return the best available window position near the tray icon."""
        if tray_geometry and not tray_geometry.isNull() and tray_geometry.width() > 0:
            screen = QGuiApplication.screenAt(tray_geometry.center()) or QApplication.primaryScreen()
            if screen is None:
                return None

            sg = screen.availableGeometry()
            anchor_x = tray_geometry.center().x()
            anchor_top = tray_geometry.top()
            anchor_bottom = tray_geometry.bottom()
        else:
            cursor_pos = QCursor.pos()
            screen = QGuiApplication.screenAt(cursor_pos) or QApplication.primaryScreen()
            if screen is None:
                return None

            sg = screen.availableGeometry()
            anchor_x = cursor_pos.x()
            anchor_top = cursor_pos.y()
            anchor_bottom = cursor_pos.y()

        x = max(sg.left(), min(anchor_x - self.width() // 2, sg.right() - self.width()))

        y_above = anchor_top - self.height() - 4
        if y_above >= sg.top():
            y = y_above
        else:
            y = anchor_bottom + 4
        y = max(sg.top(), min(y, sg.bottom() - self.height()))
        return x, y

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
        for label, idx in [("Upcoming", 0), ("Queue", 1), ("Controls", 2)]:
            btn = QPushButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _checked, i=idx: self._switch_page(i))
            nav.addWidget(btn)
            self._nav_buttons.append(btn)
        root.addLayout(nav)

        # Page stack
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_upcoming_page())
        self._stack.addWidget(self._build_queue_page())
        self._stack.addWidget(self._build_controls_page())
        root.addWidget(self._stack)

        self._update_nav_style()

    # ── Page builders ────────────────────────────────────────────

    def _build_controls_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(8)

        # Snooze toggle button
        self._snooze_btn = ControlButton("pause", "Snooze  —  OFF")
        self._snooze_btn.setObjectName("actionBtn")
        self._snooze_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._snooze_btn.clicked.connect(self._toggle_snooze)
        layout.addWidget(self._snooze_btn)

        # ── Work session controls ────────────────────────────────
        ws_section = QLabel("Work Session")
        ws_section.setObjectName("section")
        layout.addWidget(ws_section)

        # Toggle 1: Operating mode (automatic / manual)
        self._ws_mode_btn = ControlButton("settings", "Mode  —  Automatic")
        self._ws_mode_btn.setObjectName("actionBtn")
        self._ws_mode_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ws_mode_btn.clicked.connect(self._toggle_ws_mode)
        layout.addWidget(self._ws_mode_btn)

        # Toggle 2: Manual work-session lock (only active in manual mode)
        self._ws_lock_btn = ControlButton("lock-open", "Work Session Lock  —  OFF")
        self._ws_lock_btn.setObjectName("disabledBtn")
        self._ws_lock_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ws_lock_btn.clicked.connect(self._toggle_ws_lock)
        layout.addWidget(self._ws_lock_btn)

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

    def refresh_contents(self):
        """Refresh the currently selected page immediately."""
        self._refresh_current_page()

    def _refresh_controls(self):
        # Snooze toggle visual state
        lock_dir = Path(self._app.config_manager.general.lock_dir)
        own_lock = lock_dir / "reminder-system_snooze.lock"
        is_on = own_lock.exists()

        if is_on:
            self._snooze_btn.set_content("pause", "Snooze  —  ON")
            self._snooze_btn.setObjectName("toggleOn")
        else:
            self._snooze_btn.set_content("pause", "Snooze  —  OFF")
            self._snooze_btn.setObjectName("actionBtn")
        self._snooze_btn.style().unpolish(self._snooze_btn)
        self._snooze_btn.style().polish(self._snooze_btn)

        # Queue count
        qsize = self._app._queue.size() if self._app._queue else 0

        # Lock status (cancel first, then snooze)
        cancel_names = getattr(self._app, "_cancel_lock_names", [])
        snooze_names = getattr(self._app, "_snooze_lock_names", [])

        lines: list[str] = []
        for name in sorted(cancel_names):
            label = name if name else "(unnamed)"
            lines.append(f"🚫 Cancel: {label}")
        for name in sorted(snooze_names):
            label = name if name else "(unnamed)"
            lines.append(f"⏸ Snooze: {label}")
        if not lines:
            lines.append("✅ No active locks")

        self._status_label.setText("\n".join(lines))

        # ── Work session controls ────────────────────────────────
        general = self._app.config_manager.general
        ws_enabled = general.work_session_enable
        state = self._app._state
        ws_mode = state.get("work_session_operating_mode", "automatic") if state else "automatic"
        is_manual = ws_mode == "manual"

        # Mode toggle
        if not ws_enabled:
            self._ws_mode_btn.set_content("settings", "Mode  —  (disabled in config)")
            self._ws_mode_btn.setObjectName("disabledBtn")
            self._ws_mode_btn.setEnabled(False)
        else:
            self._ws_mode_btn.setEnabled(True)
            if is_manual:
                self._ws_mode_btn.set_content("settings", "Mode  —  Manual")
                self._ws_mode_btn.setObjectName("toggleOn")
            else:
                self._ws_mode_btn.set_content("settings", "Mode  —  Automatic")
                self._ws_mode_btn.setObjectName("actionBtn")
        self._ws_mode_btn.style().unpolish(self._ws_mode_btn)
        self._ws_mode_btn.style().polish(self._ws_mode_btn)

        # Manual lock toggle (only active in manual mode)
        lock_dir = Path(general.lock_dir)
        ws_lock_file = lock_dir / "work-session_cancel.lock"
        ws_lock_exists = ws_lock_file.exists()

        if not ws_enabled or not is_manual:
            self._ws_lock_btn.setEnabled(False)
            self._ws_lock_btn.set_content("lock-open", "Work Session Lock  —  OFF")
            self._ws_lock_btn.setObjectName("disabledBtn")
        else:
            self._ws_lock_btn.setEnabled(True)
            if ws_lock_exists:
                self._ws_lock_btn.set_content("play", "Start Work Session")
                self._ws_lock_btn.setObjectName("toggleOn")
            else:
                self._ws_lock_btn.set_content("pause", "Stop Work Session")
                self._ws_lock_btn.setObjectName("actionBtn")
        self._ws_lock_btn.style().unpolish(self._ws_lock_btn)
        self._ws_lock_btn.style().polish(self._ws_lock_btn)

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

    def _apply_activation_token(self, activation_token: str) -> Optional[str]:
        """Seed Qt Wayland with a fresh activation token for the next show."""
        token = activation_token.strip()
        if not token or not QGuiApplication.platformName().lower().startswith("wayland"):
            return None

        previous = os.environ.get("XDG_ACTIVATION_TOKEN")
        os.environ["XDG_ACTIVATION_TOKEN"] = token
        return previous

    @staticmethod
    def _restore_activation_token(previous: Optional[str]):
        """Restore the activation-token environment after a show attempt."""
        if previous is None:
            os.environ.pop("XDG_ACTIVATION_TOKEN", None)
        else:
            os.environ["XDG_ACTIVATION_TOKEN"] = previous

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

        # Immediate rescan so the app reacts without waiting for the
        # next poll-timer tick.
        self._app._scan_lock_files()
        self._app._update_tray_icon_color()
        self._refresh_controls()

    def _toggle_ws_mode(self):
        """Switch work session operating mode between automatic and manual."""
        state = self._app._state
        if state is None:
            return
        current = state.get("work_session_operating_mode", "automatic")
        new_mode = "manual" if current == "automatic" else "automatic"
        state.set("work_session_operating_mode", new_mode)
        print(f"Tray: work session mode → {new_mode}")

        # When switching to automatic, remove the manual lock if present
        # and let _check_work_session take over.
        if new_mode == "automatic":
            lock_dir = Path(self._app.config_manager.general.lock_dir)
            ws_lock = lock_dir / "work-session_cancel.lock"
            if ws_lock.exists():
                ws_lock.unlink()
                print("Tray: removed manual work-session lock (now automatic)")
            # Trigger an immediate automatic check
            self._app._check_work_session()

        self._app._scan_lock_files()
        self._app._update_tray_icon_color()
        self._refresh_controls()

    def _toggle_ws_lock(self):
        """Toggle the work-session cancel lock file (manual mode only)."""
        lock_dir = Path(self._app.config_manager.general.lock_dir)
        lock_file = lock_dir / "work-session_cancel.lock"

        if lock_file.exists():
            lock_file.unlink()
            print("Tray: work-session cancel lock removed")
        else:
            lock_dir.mkdir(parents=True, exist_ok=True)
            lock_file.touch()
            print("Tray: work-session cancel lock created")
            self._app._clear_queue_for_cancel_lock("manual work session")

        self._app._scan_lock_files()
        self._app._update_tray_icon_color()
        self._refresh_controls()

    def _clear_queue(self):
        """Clear all queued reminders."""
        if self._app._queue:
            count = self._app._queue.size()
            self._app._queue.clear()
            print(f"Tray: cleared {count} queued reminder(s)")
        self._refresh_controls()

    # ── Visibility ───────────────────────────────────────────────

    def toggle_visibility(
        self,
        tray_geometry: Optional[QRect] = None,
        activation_token: str = "",
    ):
        """Show or hide the window, positioning near the tray icon."""
        if self.isVisible():
            self.hide()
            return

        # Avoid reopening immediately after an auto-hide triggered by
        # the same tray-icon click (deactivation arrives before the
        # activated signal).
        if time.monotonic() - self._last_hide_time < 0.3:
            return

        target = self._compute_target_position(tray_geometry)
        if target is not None:
            self.move(*target)

        previous_token = self._apply_activation_token(activation_token)
        try:
            self.show()
            self.raise_()

            window = self.windowHandle()
            if window is not None:
                window.requestActivate()
            else:
                self.activateWindow()
        finally:
            self._restore_activation_token(previous_token)

        self._refresh_current_page()
        self._refresh_timer.start()

    # ── Events ───────────────────────────────────────────────────

    def hideEvent(self, event):
        self._refresh_timer.stop()
        self._last_hide_time = time.monotonic()
        super().hideEvent(event)

    def changeEvent(self, event):
        """Let popup semantics handle dismissal on focus changes."""
        super().changeEvent(event)

    def keyPressEvent(self, event):
        """Close on Escape."""
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)
