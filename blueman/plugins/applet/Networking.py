from gettext import gettext as _
from blueman.bluemantyping import ObjectPath

from gi.repository import GLib
from gi.repository import Gio

from blueman.bluez.NetworkServer import NetworkServer
from blueman.main.DBusProxies import Mechanism
from blueman.main.DNSServerProvider import DNSServerProvider

from blueman.plugins.AppletPlugin import AppletPlugin
from blueman.gui.CommonUi import ErrorDialog
import logging


class Networking(AppletPlugin):
    __icon__ = "network-workgroup-symbolic"
    __description__ = _("Manages local network services, like NAP bridges")
    __author__ = "Walmis"

    _dns_server_provider: DNSServerProvider | None = None
    _dns_server_provider_handler_id: int | None = None
    _config_handler_id: int | None = None
    _registered: dict[ObjectPath, bool]
    Config: Gio.Settings
    _active: bool

    def on_load(self) -> None:
        self._active = True
        self._registered: dict[ObjectPath, bool] = {}

        self.Config = Gio.Settings(schema_id="org.blueman.network")
        self._config_handler_id = self.Config.connect("changed", self.on_config_changed)

        self._apply_nap_settings()

        self._dns_server_provider = DNSServerProvider()
        self._dns_server_provider_handler_id = self._dns_server_provider.connect(
            "changed", lambda _provider: self._apply_nap_settings()
        )

    def on_manager_state_changed(self, state: bool) -> None:
        if state:
            self.update_status()

    def _apply_nap_settings(self) -> None:
        if not self.Config["nap-enable"] or self.Config["ip4-address"] is None:
            return

        def reply(_obj: Mechanism, _result: None, _user_data: None) -> None:
            if not self._active:
                return

        def err(_obj: Mechanism, result: GLib.Error, _user_data: None) -> None:
            if not self._active:
                return

            d = ErrorDialog("<b>Failed to apply network settings</b>",
                            "You might not be able to connect to the Bluetooth network via this machine",
                            result,
                            margin_left=9)

            d.run()
            d.destroy()

        m = Mechanism()
        m.EnableNetwork('(sssb)', self.Config["ip4-address"], self.Config["ip4-netmask"], self.Config["dhcp-handler"],
                        False, result_handler=reply, error_handler=err)

    def on_unload(self) -> None:
        self._active = False
        for adapter_path in self._registered:
            s = NetworkServer(obj_path=adapter_path)
            s.unregister("nap")

        self._registered = {}
        if self._dns_server_provider is not None:
            if self._dns_server_provider_handler_id is not None:
                self._dns_server_provider.disconnect(self._dns_server_provider_handler_id)
                self._dns_server_provider_handler_id = None
            self._dns_server_provider.destroy()
            self._dns_server_provider = None
        if self._config_handler_id is not None:
            self.Config.disconnect(self._config_handler_id)
            self._config_handler_id = None
        del self.Config

    def on_adapter_added(self, path: str) -> None:
        self.update_status()

    def update_status(self) -> None:
        self.set_nap(self.Config["nap-enable"])

    def on_config_changed(self, config: Gio.Settings, key: str) -> None:
        if key == "nap-enable":
            self.set_nap(config[key])

    def set_nap(self, on: bool) -> None:
        logging.info("set nap %s", on)
        if self.parent.manager_state:
            adapters = self.parent.Manager.get_adapters()
            for adapter in adapters:
                object_path = adapter.get_object_path()

                registered = self._registered.setdefault(object_path, False)

                s = NetworkServer(obj_path=object_path)
                if on and not registered:
                    s.register("nap", "pan1")
                    self._registered[object_path] = True
                elif not on and registered:
                    s.unregister("nap")
                    self._registered[object_path] = False
