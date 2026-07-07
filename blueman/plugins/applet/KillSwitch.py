from gettext import gettext as _
import os
from typing import Any, cast
from collections.abc import Callable
from enum import IntEnum

from gi.repository import GLib, Gio
import struct
import logging

from blueman.main.DBusProxies import Mechanism
from blueman.plugins.AppletPlugin import AppletPlugin
from blueman.plugins.applet.PowerManager import PowerManager, PowerStateHandler
from blueman.plugins.applet.StatusIcon import StatusIconVisibilityHandler

RFKILL_TYPE_BLUETOOTH = 2
RFKILL_EVENT_SIZE_V1 = 8


class RFKillOp(IntEnum):
    ADD = 0
    DEL = 1
    CHANGE = 2
    CHANGE_ALL = 3


class Switch:
    def __init__(self, idx: int, switch_type: int, soft: int, hard: int):
        self.idx = idx
        self.type = switch_type
        self.soft = soft
        self.hard = hard


class KillSwitch(AppletPlugin, PowerStateHandler, StatusIconVisibilityHandler):
    __author__ = "Walmis"
    __description__ = _("Switches Bluetooth killswitch status to match Bluetooth power state. "
                        "Allows turning Bluetooth back on from an icon that shows its status; "
                        "provided it isn't unplugged by the system, or physically.")
    __depends__ = ["PowerManager"]
    __icon__ = "system-shutdown-symbolic"

    __gsettings__ = {
        "schema": "org.blueman.plugins.killswitch",
        "path": None
    }
    __options__ = {
        "checked": {"type": bool, "default": False}
    }

    _switches: dict[int, Switch] = {}
    _iom: int | None = None
    _monitor_handler_id: int | None = None
    _monitor: Gio.FileMonitor | None
    _rfkill: Gio.File | None
    _connman_proxy: Gio.DBusProxy | None = None
    _connman_watch_id: int | None = None
    _enabled: bool = True
    _hardblocked: bool = False
    _active: bool

    def on_load(self) -> None:
        self._active = True
        self._rfkill = Gio.File.new_for_path("/dev/rfkill")
        start_event = Gio.FileMonitorEvent.CREATED if self._rfkill.query_exists() else Gio.FileMonitorEvent.DELETED

        self._monitor = self._rfkill.monitor(cast(Gio.FileMonitorFlags, 0), None)
        self._monitor_handler_id = self._monitor.connect("changed", self.__on_file_changed)
        self.__on_file_changed(self._monitor, self._rfkill, None, start_event)

        self._connman_watch_id = Gio.bus_watch_name(
            Gio.BusType.SYSTEM,
            "net.connman",
            cast(Gio.BusNameWatcherFlags, 0),
            self._on_connman_appeared,
            self._on_connman_vanished,
        )

    def on_unload(self) -> None:
        self._active = False
        Gio.bus_unwatch_name(self._connman_watch_id)
        self._connman_proxy = None
        if self._monitor is not None:
            if self._monitor_handler_id is not None:
                self._monitor.disconnect(self._monitor_handler_id)
                self._monitor_handler_id = None
            self._monitor.cancel()
            self._monitor = None
        self._rfkill = None

        if self._iom:
            GLib.source_remove(self._iom)
            self._iom = None

    def __on_file_changed(self, _monitor: Gio.FileMonitor, _gfile: Gio.File, _other: Gio.File | None,
                          _event: Gio.FileMonitorEvent) -> None:
        if self._iom:
            GLib.source_remove(self._iom)
            self._iom = None

        try:
            channel = GLib.IOChannel.new_file("/dev/rfkill", "r")
            self._iom = GLib.io_add_watch(channel, GLib.IO_IN | GLib.IO_ERR | GLib.IO_HUP, self.io_event)
        except GLib.Error as e:
            logging.debug("Could not open rfkill device: %s", e)
            # At this point we have no idea if there even is a working killswitch
            self._enabled = False
            self._hardblocked = False

    def _on_connman_appeared(self, _connection: Gio.DBusConnection, name: str, _owner: str) -> None:
        logging.info("%s appeared", name)
        self._connman_proxy = Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SYSTEM,
            Gio.DBusProxyFlags.DO_NOT_AUTO_START,
            None,
            'net.connman',
            '/net/connman/technology/bluetooth',
            'net.connman.Technology',
            None)

    def _on_connman_vanished(self, _connection: Gio.DBusConnection, name: str) -> None:
        logging.info("%s vanished", name)
        self._connman_proxy = None

    def io_event(self, channel: GLib.IOChannel, condition: GLib.IOCondition) -> bool:
        if condition & GLib.IO_ERR or condition & GLib.IO_HUP:
            return False

        fd = channel.unix_get_fd()
        data = os.read(fd, RFKILL_EVENT_SIZE_V1)

        if len(data) != RFKILL_EVENT_SIZE_V1:
            logging.warning("Bad rfkill event size: %s", len(data))
            return True

        (idx, switch_type, op, soft, hard) = struct.unpack("IBBBB", data)

        if switch_type != RFKILL_TYPE_BLUETOOTH:
            return True

        match RFKillOp(op):
            case RFKillOp.ADD:
                self._switches[idx] = Switch(idx, switch_type, soft, hard)
                logging.info("killswitch registered %s", idx)
            case RFKillOp.DEL:
                del self._switches[idx]
                logging.info("killswitch removed %s", idx)
            case RFKillOp.CHANGE:
                self._switches[idx] = Switch(idx, switch_type, soft, hard)
                logging.info("killswitch changed %s", idx)
            case _:
                return True

        self._enabled = True
        self._hardblocked = False
        for s in self._switches.values():
            self._hardblocked |= s.hard == 1
            self._enabled &= (s.soft == 0 and s.hard == 0)

        logging.info("State: %s", self._enabled)

        if "StatusIcon" in self.parent.Plugins.get_loaded():
            self.parent.Plugins.StatusIcon.query_visibility(delay_hiding=not self._hardblocked)
        self.parent.Plugins.PowerManager.update_power_state()

        return True

    def on_power_state_query(self) -> PowerManager.State:
        if self._hardblocked:
            return PowerManager.State.OFF_FORCED
        elif self._enabled:
            return PowerManager.State.ON
        else:
            return PowerManager.State.OFF

    def on_power_state_change_requested(self, _: PowerManager, state: bool, cb: Callable[[bool], None]) -> None:
        logging.info(state)

        def reply(*_: Any) -> None:
            if not self._active:
                return
            cb(True)

        def error(*_: Any) -> None:
            if not self._active:
                return
            cb(False)

        if self._connman_proxy:
            logging.debug("Using connman to set state: %s", state)
            self._connman_proxy.SetProperty('(sv)', 'Powered', GLib.Variant.new_boolean(state),
                                            result_handler=reply, error_handler=error)
        else:
            logging.debug("Using mechanism to set state: %s", state)
            Mechanism().SetRfkillState('(b)', state, result_handler=reply, error_handler=error)

    def on_query_force_status_icon_visibility(self) -> bool:
        # Force status icon to show if Bluetooth is soft-blocked
        return not self._hardblocked and not self._enabled
