from types import SimpleNamespace
from typing import Any
from unittest.mock import ANY, Mock, patch

from blueman.bluemantyping import ObjectPath
from blueman.bluez.errors import BluezDBusException
from blueman.plugins.applet.DBusService import DBusService, GENERIC_CONNECT


class _FakeDevice:
    def __init__(self, uuids: list[str], *, connected: bool = False) -> None:
        self._uuids = uuids
        self._connected = connected
        self.connect_device = Mock()
        self.connect_profile = Mock()
        self.disconnect_device = Mock()

    def __getitem__(self, key: str) -> list[str] | bool:
        if key == "UUIDs":
            return self._uuids
        if key == "Connected":
            return self._connected
        raise KeyError(key)


_preferred_generic_connect_uuid = getattr(DBusService, "_get_preferred_generic_connect_uuid")
_should_treat_profile_unavailable_as_success = getattr(DBusService, "_should_treat_profile_unavailable_as_success")


class TestDBusService:
    @patch("blueman.plugins.applet.DBusService.Device")
    def test_generic_connect_prefers_targeted_advanced_audio_profile_for_phone_audio(self, device_cls: Mock) -> None:
        advanced_audio_uuid = "0000110d-0000-1000-8000-00805f9b34fb"
        audio_source_uuid = "0000110a-0000-1000-8000-00805f9b34fb"
        fake_device = _FakeDevice([
            advanced_audio_uuid,
            audio_source_uuid,
            "0000111f-0000-1000-8000-00805f9b34fb",
        ])
        device_cls.return_value = fake_device
        plugin = SimpleNamespace(
            parent=SimpleNamespace(Plugins=SimpleNamespace(RecentConns=SimpleNamespace(notify=Mock()))),
            _get_preferred_generic_connect_uuid=_preferred_generic_connect_uuid,
        )
        ok = Mock()
        err = Mock()

        DBusService.connect_service(plugin, ObjectPath("/org/bluez/hci0/dev_04_C8_B0_D5_4F_28"), GENERIC_CONNECT, ok, err)

        fake_device.connect_profile.assert_called_once_with(advanced_audio_uuid, reply_handler=ok, error_handler=ANY)
        fake_device.connect_device.assert_not_called()

    @patch("blueman.plugins.applet.DBusService.Device")
    def test_generic_connect_falls_back_to_audio_source_when_advanced_audio_is_absent(self, device_cls: Mock) -> None:
        audio_source_uuid = "0000110a-0000-1000-8000-00805f9b34fb"
        fake_device = _FakeDevice([
            audio_source_uuid,
            "0000111f-0000-1000-8000-00805f9b34fb",
        ])
        device_cls.return_value = fake_device
        plugin = SimpleNamespace(
            parent=SimpleNamespace(Plugins=SimpleNamespace(RecentConns=SimpleNamespace(notify=Mock()))),
            _get_preferred_generic_connect_uuid=_preferred_generic_connect_uuid,
        )
        ok = Mock()
        err = Mock()

        DBusService.connect_service(plugin, ObjectPath("/org/bluez/hci0/dev_04_C8_B0_D5_4F_28"), GENERIC_CONNECT, ok, err)

        fake_device.connect_profile.assert_called_once_with(audio_source_uuid, reply_handler=ok, error_handler=ANY)
        fake_device.connect_device.assert_not_called()

    @patch("blueman.plugins.applet.DBusService.Device")
    def test_generic_connect_falls_back_to_device_connect_for_audio_sinks(self, device_cls: Mock) -> None:
        fake_device = _FakeDevice([
            "0000110b-0000-1000-8000-00805f9b34fb",
            "0000110d-0000-1000-8000-00805f9b34fb",
        ])
        device_cls.return_value = fake_device
        plugin = SimpleNamespace(
            parent=SimpleNamespace(Plugins=SimpleNamespace(RecentConns=SimpleNamespace(notify=Mock()))),
            _get_preferred_generic_connect_uuid=_preferred_generic_connect_uuid,
        )
        ok = Mock()
        err = Mock()

        DBusService.connect_service(plugin, ObjectPath("/org/bluez/hci0/dev_00_11_22_33_44_55"), GENERIC_CONNECT, ok, err)

        fake_device.connect_device.assert_called_once_with(reply_handler=ok, error_handler=err)
        fake_device.connect_profile.assert_not_called()

    @patch("blueman.plugins.applet.DBusService.Device")
    def test_generic_connect_treats_profile_unavailable_as_success_when_connected(self, device_cls: Mock) -> None:
        advanced_audio_uuid = "0000110d-0000-1000-8000-00805f9b34fb"
        fake_device = _FakeDevice([
            advanced_audio_uuid,
            "0000110a-0000-1000-8000-00805f9b34fb",
        ], connected=True)

        def fail_with_profile_unavailable(_uuid: str, **kwargs: Any) -> None:
            kwargs["error_handler"](
                BluezDBusException("org.bluez.Error.BREDR.ProfileUnavailable No more profiles to connect to")
            )

        fake_device.connect_profile.side_effect = fail_with_profile_unavailable
        device_cls.return_value = fake_device
        plugin = SimpleNamespace(
            parent=SimpleNamespace(Plugins=SimpleNamespace(RecentConns=SimpleNamespace(notify=Mock()))),
            _get_preferred_generic_connect_uuid=_preferred_generic_connect_uuid,
            _should_treat_profile_unavailable_as_success=_should_treat_profile_unavailable_as_success,
        )
        ok = Mock()
        err = Mock()

        DBusService.connect_service(plugin, ObjectPath("/org/bluez/hci0/dev_04_C8_B0_D5_4F_28"), GENERIC_CONNECT, ok, err)

        ok.assert_called_once_with()
        err.assert_not_called()

    @patch("blueman.plugins.applet.DBusService.Device")
    def test_generic_connect_keeps_profile_unavailable_as_error_when_disconnected(self, device_cls: Mock) -> None:
        advanced_audio_uuid = "0000110d-0000-1000-8000-00805f9b34fb"
        error = BluezDBusException("org.bluez.Error.BREDR.ProfileUnavailable No more profiles to connect to")
        fake_device = _FakeDevice([
            advanced_audio_uuid,
            "0000110a-0000-1000-8000-00805f9b34fb",
        ], connected=False)

        def fail_with_profile_unavailable(_uuid: str, **kwargs: Any) -> None:
            kwargs["error_handler"](error)

        fake_device.connect_profile.side_effect = fail_with_profile_unavailable
        device_cls.return_value = fake_device
        plugin = SimpleNamespace(
            parent=SimpleNamespace(Plugins=SimpleNamespace(RecentConns=SimpleNamespace(notify=Mock()))),
            _get_preferred_generic_connect_uuid=_preferred_generic_connect_uuid,
            _should_treat_profile_unavailable_as_success=_should_treat_profile_unavailable_as_success,
        )
        ok = Mock()
        err = Mock()

        DBusService.connect_service(plugin, ObjectPath("/org/bluez/hci0/dev_04_C8_B0_D5_4F_28"), GENERIC_CONNECT, ok, err)

        ok.assert_not_called()
        err.assert_called_once_with(error)