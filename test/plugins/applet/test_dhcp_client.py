from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from blueman.plugins.applet.DhcpClient import DhcpClient


class TestDhcpClient:
    @patch("blueman.plugins.applet.DhcpClient.AnyNetwork")
    def test_on_unload_destroys_network_and_clears_querying(self, any_network_cls: Mock) -> None:
        any_network = Mock()
        any_network_cls.return_value = any_network
        plugin = SimpleNamespace(_add_dbus_method=Mock())
        plugin.__dict__["_on_network_prop_changed"] = (
            lambda _network, key, value, object_path:
            DhcpClient.dhcp_acquire(plugin, object_path) if key == "Interface" and value != "" else None
        )
        plugin.__dict__["dhcp_acquire"] = lambda object_path: DhcpClient.dhcp_acquire(plugin, object_path)

        DhcpClient.on_load(plugin)
        plugin.querying.add("bnep0")
        DhcpClient.on_unload(plugin)

        any_network.destroy.assert_called_once_with()
        assert plugin.querying == set()
        assert plugin.__dict__["_any_network"] is None
        assert plugin.__dict__["_unloading"] is True

    @patch("blueman.plugins.applet.DhcpClient.Network")
    @patch("blueman.plugins.applet.DhcpClient.Mechanism")
    @patch("blueman.plugins.applet.DhcpClient.Notification")
    def test_late_reply_after_unload_is_ignored(
        self,
        notification_cls: Mock,
        mechanism_cls: Mock,
        network_cls: Mock,
    ) -> None:
        network = MagicMock()
        network.__getitem__.return_value = "bnep0"
        network_cls.return_value = network
        mechanism = Mock()
        mechanism_cls.return_value = mechanism
        plugin = SimpleNamespace(_unloading=False, querying=set(), _any_network=Mock())

        DhcpClient.dhcp_acquire(plugin, "/net/dev0")
        DhcpClient.on_unload(plugin)

        reply = mechanism.DhcpClient.call_args.kwargs["result_handler"]
        reply(Mock(), "10.0.0.2", None)

        assert notification_cls.call_count == 1
        assert plugin.querying == set()

    @patch("blueman.plugins.applet.DhcpClient.Network")
    @patch("blueman.plugins.applet.DhcpClient.Mechanism")
    @patch("blueman.plugins.applet.DhcpClient.Notification")
    def test_empty_interface_is_ignored(self, notification_cls: Mock, mechanism_cls: Mock, network_cls: Mock) -> None:
        network = MagicMock()
        network.__getitem__.return_value = ""
        network_cls.return_value = network
        plugin = SimpleNamespace(_unloading=False, querying=set())

        DhcpClient.dhcp_acquire(plugin, "/net/dev0")

        mechanism_cls.assert_not_called()
        notification_cls.assert_not_called()
        assert plugin.querying == set()