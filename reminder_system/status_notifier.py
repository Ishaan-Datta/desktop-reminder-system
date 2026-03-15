"""Custom StatusNotifierItem backend for Linux tray integration.

This backend is used on Linux Wayland sessions where ``QSystemTrayIcon``
does not expose reliable activation coordinates.  The tray host sends the
click position directly to the ``Activate`` / ``ContextMenu`` D-Bus methods,
which lets the app position the tray panel precisely.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Callable, Optional

from PyQt6.QtCore import (
    QObject,
    QPoint,
    QRect,
    pyqtClassInfo,
    pyqtProperty,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtGui import QGuiApplication, QIcon
from PyQt6.QtDBus import (
    QDBusConnection,
    QDBusMessage,
    QDBusObjectPath,
    QDBusServiceWatcher,
)


WATCHER_SERVICE = "org.kde.StatusNotifierWatcher"
WATCHER_PATH = "/StatusNotifierWatcher"
WATCHER_INTERFACE = "org.kde.StatusNotifierWatcher"
ITEM_PATH = "/StatusNotifierItem"
MENU_PATH = "/MenuBar"


def is_wayland_session() -> bool:
    """Return ``True`` when the current Qt session is Wayland."""
    platform_name = QGuiApplication.platformName().lower()
    return (
        platform_name.startswith("wayland")
        or os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"
        or bool(os.environ.get("WAYLAND_DISPLAY"))
    )


@pyqtClassInfo("D-Bus Interface", "org.kde.StatusNotifierItem")
class StatusNotifierItem(QObject):
    """D-Bus object implementing a minimal StatusNotifierItem."""

    NewTitle = pyqtSignal()
    NewIcon = pyqtSignal()
    NewAttentionIcon = pyqtSignal()
    NewOverlayIcon = pyqtSignal()
    NewMenu = pyqtSignal()
    NewToolTip = pyqtSignal()
    NewStatus = pyqtSignal(str)

    def __init__(
        self,
        *,
        app_id: str,
        title: str,
        on_activate: Callable[[QRect], None],
        on_context_menu: Callable[[QPoint], None],
        parent: Optional[QObject] = None,
    ):
        """Initialise the exported StatusNotifierItem object."""
        super().__init__(parent)
        self._app_id = app_id
        self._title = title
        self._status = "Active"
        self._icon_name = ""
        self._icon_theme_path = ""
        self._last_activation_token = ""
        self._on_activate = on_activate
        self._on_context_menu = on_context_menu

    @pyqtProperty(str)
    def Category(self) -> str:
        """Return the StatusNotifier category for the item."""
        return "ApplicationStatus"

    @pyqtProperty(str)
    def Id(self) -> str:
        """Return the stable identifier advertised on D-Bus."""
        return self._app_id

    @pyqtProperty(str)
    def Title(self) -> str:
        """Return the human-readable tray item title."""
        return self._title

    @pyqtProperty(str)
    def Status(self) -> str:
        """Return the current StatusNotifier status string."""
        return self._status

    @pyqtProperty(int)
    def WindowId(self) -> int:
        """Return the associated window id when one exists."""
        return 0

    @pyqtProperty(str)
    def IconName(self) -> str:
        """Return the active icon name inside the generated theme."""
        return self._icon_name

    @pyqtProperty(str)
    def IconThemePath(self) -> str:
        """Return the filesystem path for the generated icon theme."""
        return self._icon_theme_path

    @pyqtProperty(bool)
    def ItemIsMenu(self) -> bool:
        """Return whether the tray item behaves like a menu."""
        return False

    @pyqtProperty("QDBusObjectPath")
    def Menu(self) -> QDBusObjectPath:
        """Return the exported menu object path."""
        return QDBusObjectPath(MENU_PATH)

    @pyqtProperty(str)
    def AttentionIconName(self) -> str:
        """Return the optional attention icon name."""
        return ""

    @pyqtProperty(str)
    def OverlayIconName(self) -> str:
        """Return the optional overlay icon name."""
        return ""

    @pyqtProperty(str)
    def AttentionMovieName(self) -> str:
        """Return the optional attention animation name."""
        return ""

    @pyqtSlot(int, int)
    def Activate(self, x: int, y: int):
        """Forward a primary activation request from the tray host."""
        self._on_activate(QRect(x, y, 1, 1))

    @pyqtSlot(int, int)
    def ContextMenu(self, x: int, y: int):
        """Forward a context-menu request from the tray host."""
        self._on_context_menu(QPoint(x, y))

    @pyqtSlot(int, int)
    def SecondaryActivate(self, x: int, y: int):
        """Treat secondary activation the same as primary activation."""
        self._on_activate(QRect(x, y, 1, 1))

    @pyqtSlot(int, str)
    def Scroll(self, delta: int, orientation: str):
        """Accept scroll events even though the item does not use them."""
        _ = (delta, orientation)

    @pyqtSlot(str)
    def ProvideXdgActivationToken(self, token: str):
        """Store the latest XDG activation token sent by the tray host."""
        self._last_activation_token = token

    def take_activation_token(self) -> str:
        """Return and clear the most recent XDG activation token."""
        token = self._last_activation_token
        self._last_activation_token = ""
        return token

    def update_icon(self, icon_name: str, icon_theme_path: str):
        """Publish an updated icon name and theme path to watchers."""
        if self._icon_name == icon_name and self._icon_theme_path == icon_theme_path:
            return
        self._icon_name = icon_name
        self._icon_theme_path = icon_theme_path
        self.NewIcon.emit()

    def update_status(self, status: str):
        """Publish an updated StatusNotifier status string."""
        if self._status == status:
            return
        self._status = status
        self.NewStatus.emit(status)


class StatusNotifierBackend(QObject):
    """Linux tray backend using the StatusNotifierItem D-Bus protocol."""

    def __init__(
        self,
        *,
        icon_factory: Callable[[str, str], QIcon],
        on_activate: Callable[[QRect], None],
        on_context_menu: Callable[[QPoint], None],
        parent: Optional[QObject] = None,
    ):
        """Initialise the Linux tray backend and its temporary icon theme."""
        super().__init__(parent)
        self._connection = QDBusConnection.sessionBus()
        self._icon_factory = icon_factory
        self._item = StatusNotifierItem(
            app_id="desktop-reminder-system",
            title="Reminder System",
            on_activate=on_activate,
            on_context_menu=on_context_menu,
            parent=self,
        )
        self._menu_placeholder = QObject(self)
        self._service_watcher = QDBusServiceWatcher(
            WATCHER_SERVICE,
            self._connection,
            QDBusServiceWatcher.WatchModeFlag.WatchForRegistration
            | QDBusServiceWatcher.WatchModeFlag.WatchForOwnerChange,
            self,
        )
        self._service_watcher.serviceRegistered.connect(self._register_with_watcher)
        self._service_watcher.serviceOwnerChanged.connect(
            self._on_watcher_owner_changed
        )
        self._started = False
        self._icon_dir = Path(tempfile.mkdtemp(prefix="reminder-system-tray-"))
        self._theme_dir = self._icon_dir / "hicolor"
        self._icon_state = "green"
        self._prepare_icon_theme()

    @staticmethod
    def is_supported() -> bool:
        """Whether this backend should be used for the current session."""
        return os.name == "posix" and is_wayland_session()

    def start(self):
        """Register the item on D-Bus and with the watcher."""
        if self._started:
            return

        flags = (
            QDBusConnection.RegisterOption.ExportAllSlots
            | QDBusConnection.RegisterOption.ExportAllProperties
            | QDBusConnection.RegisterOption.ExportAllSignals
        )
        self._connection.registerObject(ITEM_PATH, self._item, flags)
        self._connection.registerObject(MENU_PATH, self._menu_placeholder)
        self._started = True
        self._register_with_watcher()

    def stop(self):
        """Unregister the item and clean up generated icon files."""
        if not self._started:
            return

        self._connection.unregisterObject(ITEM_PATH)
        self._connection.unregisterObject(MENU_PATH)
        self._started = False
        for file_path in self._icon_dir.rglob("*"):
            try:
                if file_path.is_file() or file_path.is_symlink():
                    file_path.unlink()
            except FileNotFoundError:
                pass
        for dir_path in sorted(self._icon_dir.rglob("*"), reverse=True):
            if dir_path.is_dir():
                try:
                    dir_path.rmdir()
                except OSError:
                    pass
        try:
            self._icon_dir.rmdir()
        except OSError:
            pass

    def set_icon_state(self, state: str, fill: str, border: str):
        """Update the tray icon that the watcher exposes."""
        if not self._started:
            return

        self._icon_state = state
        icon = self._icon_factory(fill, border)
        icon_name = f"reminder-system-{state}"
        for size in (22, 32):
            size_dir = self._theme_dir / f"{size}x{size}" / "status"
            size_dir.mkdir(parents=True, exist_ok=True)
            icon.pixmap(size, size).save(str(size_dir / f"{icon_name}.png"), "PNG")
        self._item.update_icon(icon_name, str(self._icon_dir))

    def set_status(self, status: str):
        """Expose the current SNI status string."""
        self._item.update_status(status)

    def take_activation_token(self) -> str:
        """Return the freshest XDG activation token captured from the tray host."""
        return self._item.take_activation_token()

    def _on_watcher_owner_changed(self, _service: str, _old_owner: str, new_owner: str):
        """Re-register the item when the watcher service owner changes."""
        if new_owner:
            self._register_with_watcher()

    def _register_with_watcher(self):
        """Register the exported item with the StatusNotifier watcher."""
        if not self._started:
            return

        message = QDBusMessage.createMethodCall(
            WATCHER_SERVICE,
            WATCHER_PATH,
            WATCHER_INTERFACE,
            "RegisterStatusNotifierItem",
        )
        message.setArguments([ITEM_PATH])
        self._connection.call(message)

    def _prepare_icon_theme(self):
        """Create a minimal icon theme directory for the custom tray icons."""
        self._theme_dir.mkdir(parents=True, exist_ok=True)
        index_theme = self._theme_dir / "index.theme"
        index_theme.write_text(
            "[Icon Theme]\n"
            "Name=Reminder System Tray\n"
            "Comment=Generated tray icons for Reminder System\n"
            "Directories=22x22/status,32x32/status\n\n"
            "[22x22/status]\n"
            "Size=22\n"
            "Context=Status\n"
            "Type=Fixed\n\n"
            "[32x32/status]\n"
            "Size=32\n"
            "Context=Status\n"
            "Type=Fixed\n",
            encoding="utf-8",
        )
