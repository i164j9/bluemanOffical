from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from blueman.main.DhcpClient import DhcpClientError
from blueman.plugins.mechanism.Network import Network


class TestNetwork:
    @patch("blueman.plugins.mechanism.Network.BluezNetwork")
    @patch("blueman.main.DhcpClient.DhcpClient")
    def test_run_dhcp_client_resumes_timer_on_immediate_startup_error(
        self,
        dhcp_client_cls: Mock,
        bluez_network_cls: Mock,
    ) -> None:
        run_dhcp_client = getattr(Network, "_run_dhcp_client")
        bluez_network = MagicMock()
        bluez_network.__getitem__.return_value = "bnep0"
        bluez_network_cls.return_value = bluez_network
        dhcp_client = Mock()
        dhcp_client.run.side_effect = DhcpClientError("No DHCP client found")
        dhcp_client_cls.return_value = dhcp_client
        plugin = SimpleNamespace(timer=Mock(), confirm_authorization=Mock())
        ok = Mock()
        err = Mock()

        run_dhcp_client(plugin, "/org/bluez/hci0/dev_00_11_22_33_44_55", "caller", ok, err)

        plugin.timer.stop.assert_called_once_with()
        plugin.timer.resume.assert_called_once_with()
        plugin.confirm_authorization.assert_called_once_with("caller", "org.blueman.dhcp.client")
        err.assert_called_once()
        ok.assert_not_called()