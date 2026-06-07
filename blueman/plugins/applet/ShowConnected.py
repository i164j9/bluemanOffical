from gettext import gettext as _
import logging
from typing import Any
from blueman.bluemantyping import ObjectPath

from gi.repository import GLib

from blueman.bluez.Battery import Battery
from blueman.bluez.Device import Device
from blueman.bluez.errors import BluezDBusException
from blueman.main.BatteryWatcher import BatteryWatcher
from blueman.plugins.AppletPlugin import AppletPlugin

from blueman.plugins.applet.StatusIcon import StatusIconProvider
from blueman.main.PluginManager import PluginManager


class ShowConnected(AppletPlugin, StatusIconProvider):
    __author__ = "Walmis"
    __depends__ = ["StatusIcon"]
    __icon__ = "bluetooth-symbolic"
    __description__ = _("Adds an indication on the status icon when Bluetooth is active and shows the "
                        "connections in the tooltip.")

    _connections: set[ObjectPath]
    active: bool
    initialized: bool
    _handlers: list[int]
    _enumerate_source_id: int | None = None
    _battery_watcher: BatteryWatcher

    def on_load(self) -> None:
        self._connections: set[ObjectPath] = set()
        self.active = False
        self.initialized = False
        self._handlers: list[int] = []
        self._enumerate_source_id: int | None = None
        self._handlers.append(self.parent.Plugins.connect('plugin-loaded', self._on_plugins_changed))
        self._handlers.append(self.parent.Plugins.connect('plugin-unloaded', self._on_plugins_changed))
        self._battery_watcher = BatteryWatcher(lambda *args: self.update_statusicon())

    def on_unload(self) -> None:
        self.parent.Plugins.StatusIcon.set_tooltip_text(None)
        self._connections = set()
        self.parent.Plugins.StatusIcon.icon_should_change()
        for handler in self._handlers:
            self.parent.Plugins.disconnect(handler)
        self._handlers = []
        if self._enumerate_source_id is not None:
            GLib.source_remove(self._enumerate_source_id)
            self._enumerate_source_id = None
        del self._battery_watcher

    def on_status_icon_query_icon(self) -> str | None:
        if self._connections:
            self.active = True
            return "blueman-active"
        else:
            self.active = False
            return None

    def enumerate_connections(self) -> bool:
        self._connections = {device.get_object_path()
                             for device in self.parent.Manager.get_devices()
                             if device["Connected"]}

        logging.info("Found %d existing connections", len(self._connections))
        if (self._connections and not self.active) or (not self._connections and self.active):
            self.parent.Plugins.StatusIcon.icon_should_change()

        self.update_statusicon()

        return False

    def update_statusicon(self) -> None:
        if self._connections:
            def build_line(obj_path: ObjectPath) -> str:
                line: str = Device(obj_path=obj_path)["Alias"]
                try:
                    return f"{line} 🔋{Battery(obj_path=obj_path)['Percentage']}%"
                except BluezDBusException:
                    return line

            self.parent.Plugins.StatusIcon.set_tooltip_title(_("Bluetooth Active"))
            self.parent.Plugins.StatusIcon.set_tooltip_text("\n".join(map(build_line, self._connections)))
        else:
            self.parent.Plugins.StatusIcon.set_tooltip_text(None)
            if 'PowerManager' in self.parent.Plugins.get_loaded():
                status = self.parent.Plugins.PowerManager.get_bluetooth_status()
                if status:
                    self.parent.Plugins.StatusIcon.set_tooltip_title(_("Bluetooth Enabled"))
                else:
                    self.parent.Plugins.StatusIcon.set_tooltip_title(_("Bluetooth Disabled"))
            else:
                self.parent.Plugins.StatusIcon.set_tooltip_title("Blueman")

    def on_manager_state_changed(self, state: bool) -> None:
        if state:
            if self._enumerate_source_id is not None:
                GLib.source_remove(self._enumerate_source_id)
            if not self.initialized:
                self._enumerate_source_id = GLib.timeout_add(0, self._run_enumerate_connections)
                self.initialized = True
            else:
                self._enumerate_source_id = GLib.timeout_add(1000, self._run_enumerate_connections)
        else:
            if self._enumerate_source_id is not None:
                GLib.source_remove(self._enumerate_source_id)
                self._enumerate_source_id = None
            self._connections = set()
            self.update_statusicon()

    def _run_enumerate_connections(self) -> bool:
        self._enumerate_source_id = None
        return self.enumerate_connections()

    def on_device_property_changed(self, path: ObjectPath, key: str, value: Any) -> None:
        if key == "Connected":
            if value:
                self._connections.add(path)
            else:
                self._connections.discard(path)

            if (self._connections and not self.active) or (not self._connections and self.active):
                self.parent.Plugins.StatusIcon.icon_should_change()

            self.update_statusicon()

    def on_adapter_added(self, _path: str) -> None:
        self.enumerate_connections()

    def on_adapter_removed(self, _path: str) -> None:
        self.enumerate_connections()

    def _on_plugins_changed(self, _pluginmngr: PluginManager[AppletPlugin], name: str) -> None:
        if name == "PowerManager":
            self.update_statusicon()
