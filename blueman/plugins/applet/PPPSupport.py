from gettext import gettext as _
from typing import TYPE_CHECKING, Any
from collections.abc import Callable

from blueman.services.meta.SerialService import SerialService

from blueman.bluez.Device import Device
from blueman.plugins.AppletPlugin import AppletPlugin
from blueman.gui.Notification import Notification
from blueman.main.DBusProxies import DBus, DBusProxyFailed, Mechanism

from gi.repository import GLib
from gi.repository import Gio

import logging

from blueman.plugins.applet.DBusService import RFCOMMConnectHandler
from blueman.services import DialupNetwork

if TYPE_CHECKING:
    from _blueman import RFCOMMError
    from blueman.main.Applet import BluemanApplet
else:
    RFCOMMError = Any


class PPPConnectedListener:
    def on_ppp_connected(self, _device: Device, _rfcomm: str, _ppp_port: str) -> None:
        ...


class Connection:
    def __init__(self, applet: "BluemanApplet", service: DialupNetwork, port: int,
                 ok: Callable[[str], None], err: Callable[[GLib.Error], None],
                 done: Callable[["Connection"], None]):
        self.reply_handler = ok
        self.error_handler = err
        self.service = service
        self.port = port
        self.parent = applet
        self._done = done
        self._connect_source_id: int | None = None
        self._disconnect_source_id: int | None = None
        self._closed = False

        if self._modem_manager_running():
            timeout = 10
            logging.info("ModemManager is running, delaying connection %s sec for it to complete probing", timeout)
            self._connect_source_id = GLib.timeout_add_seconds(timeout, self.connect)
        else:
            self.connect()

    @staticmethod
    def _modem_manager_running() -> bool:
        try:
            return DBus().NameHasOwner("(s)", "org.freedesktop.ModemManager1")
        except DBusProxyFailed:
            logging.debug("Failed to query ModemManager owner", exc_info=True)
            return False

    def connect(self) -> bool:
        self._connect_source_id = None
        if self._closed:
            return False

        c = Gio.Settings(schema_id="org.blueman.gsmsetting",
                         path=f"/org/blueman/gsmsettings/{self.service.device['Address']}/")

        m = Mechanism()
        m.PPPConnect('(uss)', self.port, c["number"], c["apn"], result_handler=self.on_connected,
                     error_handler=self.on_error)

        return False

    def on_error(self, _obj: Mechanism, result: GLib.Error, _user_data: None) -> None:
        if self._closed:
            return

        logging.info("Failed %s", result)
        self.error_handler(result)

        def _connect() -> bool:
            self._disconnect_source_id = None
            self.service.disconnect(self.port)
            self._finish()
            return False

        self._disconnect_source_id = GLib.timeout_add(1000, _connect)

    def on_connected(self, _obj: Mechanism, result: str, _user_data: None) -> None:
        if self._closed:
            self.service.disconnect(self.port)
            return

        rfcomm_dev = f"/dev/rfcomm{self.port:d}"
        self.reply_handler(rfcomm_dev)
        for plugin in self.parent.Plugins.get_loaded_plugins(PPPConnectedListener):
            plugin.on_ppp_connected(self.service.device, rfcomm_dev, result)

        msg = _("Successfully connected to <b>DUN</b> service on <b>%(0)s.</b>\n"
                "Network is now available through <b>%(1)s</b>") % \
            {"0": self.service.device.display_name, "1": result}

        Notification(_("Connected"), msg, icon_name="network-wireless-symbolic").show()
        self._finish()

    def _finish(self) -> None:
        if self._connect_source_id is not None:
            GLib.source_remove(self._connect_source_id)
            self._connect_source_id = None
        if self._disconnect_source_id is not None:
            GLib.source_remove(self._disconnect_source_id)
            self._disconnect_source_id = None
        self._done(self)

    def cancel(self) -> None:
        if self._closed:
            return

        self._closed = True

        if self._connect_source_id is not None:
            GLib.source_remove(self._connect_source_id)
            self._connect_source_id = None

        if self._disconnect_source_id is not None:
            GLib.source_remove(self._disconnect_source_id)
            self._disconnect_source_id = None
            self.service.disconnect(self.port)

        self._done(self)


class PPPSupport(AppletPlugin, RFCOMMConnectHandler):
    __depends__ = ["DBusService"]
    __description__ = _("Provides basic support for connecting to the internet via DUN profile.")
    __author__ = "Walmis"
    __icon__ = "modem-symbolic"
    __priority__ = 0
    _connections: set[Connection]
    _active: bool

    def on_load(self) -> None:
        self._active = True
        self._connections: set[Connection] = set()

    def on_unload(self) -> None:
        self._active = False
        for connection in list(self._connections):
            connection.cancel()
        self._connections.clear()

    def _track_connection(self, connection: Connection) -> None:
        self._connections.add(connection)

    def _forget_connection(self, connection: Connection) -> None:
        self._connections.discard(connection)

    def rfcomm_connect_handler(self, service: SerialService, reply: Callable[[str], None],
                               err: Callable[[RFCOMMError | GLib.Error], None]) -> bool:
        if isinstance(service, DialupNetwork):
            def local_reply(port: int) -> None:
                if not self._active:
                    service.disconnect(port)
                    return

                assert isinstance(service, DialupNetwork)  # https://github.com/python/mypy/issues/2608
                connection = Connection(self.parent, service, port, reply, err, self._forget_connection)
                self._track_connection(connection)

            service.connect(reply_handler=local_reply, error_handler=err)
            logging.info("Connecting rfcomm device")

            return True
        else:
            return False
