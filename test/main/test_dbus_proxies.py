from typing import TypeVar
from unittest import TestCase
from unittest.mock import MagicMock, Mock, patch

from gi.repository import GLib  # pyright: ignore[reportMissingModuleSource]

from blueman.bluemantyping import ObjectPath
from blueman.gobject import SingletonGObjectMeta
from blueman.main.DBusProxies import AppletDhcpClientService, AppletPowerManagerService, AppletService, ProxyBase

TProxy = TypeVar("TProxy", bound=ProxyBase)


def _make_proxy(cls: type[TProxy]) -> TProxy:
    """Instantiate a ProxyBase subclass without touching a real D-Bus bus.

    ProxyBase.__init__ would call Gio.DBusProxy.init() which needs a live bus.
    We bypass it and reset the singleton cache so other tests are unaffected.
    """
    with patch.object(ProxyBase, "__init__", return_value=None):
        setattr(cls, "_instance", None)
        instance = cls()
    setattr(cls, "_instance", None)
    return instance


class TestAppletService:
    def test_get_bluetooth_status_uses_root_interface_method(self) -> None:
        proxy = _make_proxy(AppletService)
        proxy.call_sync = Mock(return_value=GLib.Variant("(b)", (True,)))

        result = proxy.get_bluetooth_status()

        assert result is True
        proxy.call_sync.assert_called_once_with("GetBluetoothStatus", None, 0, -1, None)

    def test_set_bluetooth_status_uses_root_interface_method(self) -> None:
        proxy = _make_proxy(AppletPowerManagerService)
        proxy.call_sync = Mock()

        proxy.set_bluetooth_status(True)

        method_name, params, flags, timeout, cancellable = proxy.call_sync.call_args.args
        assert method_name == "SetBluetoothStatus"
        assert params.unpack() == (True,)
        assert flags == 0
        assert timeout == -1
        assert cancellable is None

    def test_dhcp_client_uses_root_interface_method(self) -> None:
        proxy = _make_proxy(AppletDhcpClientService)
        proxy.call_sync = Mock()
        path = ObjectPath("/org/bluez/hci0/dev_00_11_22_33_44_55")

        proxy.dchp_client(path)

        method_name, params, flags, timeout, cancellable = proxy.call_sync.call_args.args
        assert method_name == "DhcpClient"
        assert params.unpack() == (path,)
        assert flags == 0
        assert timeout == -1
        assert cancellable is None


class TestDBusProxies(TestCase):
    def test_metaclass(self) -> None:
        self.assertIsInstance(ProxyBase, SingletonGObjectMeta)

    def test_dhcp_client_dispatches_to_dbus(self) -> None:
        proxy = _make_proxy(AppletDhcpClientService)
        proxy.call_sync = MagicMock()

        path = ObjectPath("/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF")
        proxy.dchp_client(path)

        proxy.call_sync.assert_called_once()
        args = proxy.call_sync.call_args.args
        self.assertEqual(args[0], "DhcpClient")
        self.assertEqual(args[1].get_type_string(), "(o)")
        self.assertEqual(args[1].unpack(), (path,))
        self.assertEqual(args[2:], (0, -1, None))
