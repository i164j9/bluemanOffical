from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock

from gi.repository import GLib

from blueman.gobject import SingletonGObjectMeta
from blueman.main.DBusProxies import AppletDhcpClientService, AppletPowerManagerService, AppletService, ProxyBase


class TestAppletService:
    def test_get_bluetooth_status_uses_root_interface_method(self) -> None:
        proxy = SimpleNamespace(call_sync=Mock(return_value=GLib.Variant("(b)", (True,))))

        result = AppletService.get_bluetooth_status(proxy)

        assert result is True
        proxy.call_sync.assert_called_once_with("GetBluetoothStatus", None, 0, -1, None)

    def test_set_bluetooth_status_uses_root_interface_method(self) -> None:
        proxy = SimpleNamespace(call_sync=Mock())

        AppletPowerManagerService.set_bluetooth_status(proxy, True)

        method_name, params, flags, timeout, cancellable = proxy.call_sync.call_args.args
        assert method_name == "SetBluetoothStatus"
        assert params.unpack() == (True,)
        assert flags == 0
        assert timeout == -1
        assert cancellable is None

    def test_dhcp_client_uses_root_interface_method(self) -> None:
        proxy = SimpleNamespace(call_sync=Mock())

        AppletDhcpClientService.dchp_client(proxy, "/org/bluez/hci0/dev_00_11_22_33_44_55")

        method_name, params, flags, timeout, cancellable = proxy.call_sync.call_args.args
        assert method_name == "DhcpClient"
        assert params.unpack() == ("/org/bluez/hci0/dev_00_11_22_33_44_55",)
        assert flags == 0
        assert timeout == -1
        assert cancellable is None


class TestDBusProxies(TestCase):
    def test_metaclass(self):
        self.assertIsInstance(ProxyBase, SingletonGObjectMeta)
