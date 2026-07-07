from gettext import gettext as _
from typing import Any, Union, TYPE_CHECKING
from collections.abc import Callable
from blueman.bluemantyping import ObjectPath

from gi.repository import GLib

from blueman.Service import Service
from blueman.bluez.errors import BluezDBusException
if TYPE_CHECKING:
    from _blueman import RFCOMMError
    from blueman.main.NetworkManager import NMConnectionError
else:
    RFCOMMError = Any
from blueman.plugins.AppletPlugin import AppletPlugin
from blueman.bluez.Device import Device
from blueman.services.Functions import get_service
from blueman.Sdp import ADVANCED_AUDIO_SVCLASS_ID, AUDIO_SOURCE_SVCLASS_ID, AUDIO_SINK_SVCLASS_ID, ServiceUUID

import logging

from blueman.services.meta import SerialService, NetworkService


GENERIC_CONNECT = '00000000-0000-0000-0000-000000000000'


class RFCOMMConnectedListener:
    def on_rfcomm_connected(self, _service: SerialService, _port: str) -> None:
        ...

    def on_rfcomm_disconnect(self, _port: int) -> None:
        ...


class RFCOMMConnectHandler:
    def rfcomm_connect_handler(self, _service: SerialService, _reply: Callable[[str], None],
                               _err: Callable[[RFCOMMError | GLib.Error], None]) -> bool:
        return False


class ServiceConnectHandler:
    def service_connect_handler(self, _service: Service, _ok: Callable[[], None],
                                _err: Callable[[Union["NMConnectionError", GLib.Error]], None]) -> bool:
        return False

    def service_disconnect_handler(self, _service: Service, _ok: Callable[[], None],
                                   _err: Callable[[Union["NMConnectionError", GLib.Error]], None]) -> bool:
        return False


class DBusService(AppletPlugin):
    __unloadable__ = False
    __description__ = _("Provides DBus API for other Blueman components")
    __author__ = "Walmis"
    __dbus_iface_name__ = "org.blueman.Applet"

    _plugin_handler_ids: list[int]

    def on_load(self) -> None:
        self._plugin_handler_ids = []
        self._add_dbus_method("QueryPlugins", (), "as", self.parent.Plugins.get_loaded)
        self._add_dbus_method("QueryAvailablePlugins", (), "as", lambda: list(self.parent.Plugins.get_classes()))
        self._add_dbus_method("SetPluginConfig", ("s", "b"), "", self.parent.Plugins.set_config)
        self._add_dbus_method("ConnectService", ("o", "s"), "", self.connect_service, is_async=True)
        self._add_dbus_method("DisconnectService", ("o", "s", "d"), "", self._disconnect_service, is_async=True)
        self._add_dbus_method("OpenPluginDialog", (), "", self._open_plugin_dialog)

        self._add_dbus_signal("PluginsChanged", "")
        self._plugin_handler_ids.append(self.parent.Plugins.connect("plugin-loaded", lambda *args: self._plugins_changed()))
        self._plugin_handler_ids.append(self.parent.Plugins.connect("plugin-unloaded", lambda *args: self._plugins_changed()))

    def on_delete(self) -> None:
        for handler_id in self._plugin_handler_ids:
            self.parent.Plugins.disconnect(handler_id)
        self._plugin_handler_ids = []

    def _plugins_changed(self) -> None:
        self._emit_dbus_signal("PluginsChanged")

    @staticmethod
    def _get_preferred_generic_connect_uuid(device: Device) -> str | None:
        try:
            uuids = list(device["UUIDs"])
        except BluezDBusException:
            logging.debug("Falling back to generic connect because UUIDs are unavailable", exc_info=True)
            return None

        advanced_audio_uuid: str | None = None
        audio_source_uuid: str | None = None
        has_audio_sink = False

        for uuid in uuids:
            short_uuid = ServiceUUID(uuid).short_uuid
            if short_uuid == ADVANCED_AUDIO_SVCLASS_ID:
                advanced_audio_uuid = uuid
            elif short_uuid == AUDIO_SOURCE_SVCLASS_ID:
                audio_source_uuid = uuid
            elif short_uuid == AUDIO_SINK_SVCLASS_ID:
                has_audio_sink = True

        if advanced_audio_uuid is not None and not has_audio_sink:
            return advanced_audio_uuid

        if audio_source_uuid is not None and not has_audio_sink:
            return audio_source_uuid

        return None

    @staticmethod
    def _should_treat_profile_unavailable_as_success(device: Device, exception: BluezDBusException) -> bool:
        message = str(exception)
        if "ProfileUnavailable" not in message or "No more profiles to connect to" not in message:
            return False

        try:
            return bool(device["Connected"])
        except BluezDBusException:
            logging.debug("Unable to read Connected while handling profile connect failure", exc_info=True)
            return False

    def connect_service(self, object_path: ObjectPath, uuid: str, ok: Callable[[], None],
                        err: Callable[[Union[BluezDBusException, "NMConnectionError",
                                             RFCOMMError, GLib.Error, str]], None]) -> None:
        try:
            self.parent.Plugins.RecentConns
        except KeyError:
            logging.warning("RecentConns plugin is unavailable")
        else:
            self.parent.Plugins.RecentConns.notify(object_path, uuid)

        if uuid == GENERIC_CONNECT:
            device = Device(obj_path=object_path)
            preferred_uuid = self._get_preferred_generic_connect_uuid(device)
            if preferred_uuid is None:
                device.connect_device(reply_handler=ok, error_handler=err)
            else:
                def on_generic_profile_error(exception: BluezDBusException) -> None:
                    if self._should_treat_profile_unavailable_as_success(device, exception):
                        logging.info(
                            "Treating targeted profile connect failure as success for %s: %s",
                            object_path,
                            exception,
                        )
                        ok()
                    else:
                        err(exception)

                logging.info(
                    "Using targeted profile connect for %s via %s instead of Device.Connect",
                    object_path,
                    preferred_uuid,
                )
                device.connect_profile(preferred_uuid, reply_handler=ok, error_handler=on_generic_profile_error)
        else:
            service = get_service(Device(obj_path=object_path), uuid)
            assert service is not None

            if any(plugin.service_connect_handler(service, ok, err)
                   for plugin in self.parent.Plugins.get_loaded_plugins(ServiceConnectHandler)):
                pass
            elif isinstance(service, SerialService):
                def reply(rfcomm: str) -> None:
                    assert isinstance(service, SerialService)  # https://github.com/python/mypy/issues/2608
                    for plugin in self.parent.Plugins.get_loaded_plugins(RFCOMMConnectedListener):
                        plugin.on_rfcomm_connected(service, rfcomm)
                    ok()

                if not any(plugin.rfcomm_connect_handler(service, reply, err)
                           for plugin in self.parent.Plugins.get_loaded_plugins(RFCOMMConnectHandler)):
                    service.connect(reply_handler=lambda port: ok(), error_handler=err)
            elif isinstance(service, NetworkService):
                service.connect(reply_handler=lambda interface: ok(), error_handler=err)
            else:
                logging.info("No handler registered")
                err("Service not supported\nPossibly the plugin that handles this service is not loaded")

    def _disconnect_service(self, object_path: ObjectPath, uuid: str, port: int, ok: Callable[[], None],
                            err: Callable[[Union[BluezDBusException, "NMConnectionError",
                                                 GLib.Error, str]], None]) -> None:
        if uuid == GENERIC_CONNECT:
            device = Device(obj_path=object_path)
            device.disconnect_device(reply_handler=ok, error_handler=err)
        else:
            service = get_service(Device(obj_path=object_path), uuid)
            assert service is not None

            if any(plugin.service_disconnect_handler(service, ok, err)
                   for plugin in self.parent.Plugins.get_loaded_plugins(ServiceConnectHandler)):
                pass
            elif isinstance(service, SerialService):
                service.disconnect(port, reply_handler=ok, error_handler=err)

                for plugin in self.parent.Plugins.get_loaded_plugins(RFCOMMConnectedListener):
                    plugin.on_rfcomm_disconnect(port)

                logging.info("Disconnecting rfcomm device")
            elif isinstance(service, NetworkService):
                service.disconnect(reply_handler=ok, error_handler=err)

    def _open_plugin_dialog(self) -> None:
        self.parent.Plugins.StandardItems.on_plugins()
