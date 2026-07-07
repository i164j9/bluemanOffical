from unittest.mock import Mock, patch

import pytest

from blueman.main.DhcpClient import DhcpClient, DhcpClientError


class TestDhcpClient:
    @patch("blueman.main.DhcpClient.have", return_value=None)
    def test_run_raises_specific_error_when_no_client_found(self, _have: Mock) -> None:
        client = DhcpClient("bnep0")

        with pytest.raises(DhcpClientError, match="No DHCP client found"):
            client.run()

    @patch("blueman.main.DhcpClient.have", return_value="/usr/bin/dhclient")
    def test_run_raises_specific_error_when_interface_already_querying(self, _have: Mock) -> None:
        client = DhcpClient("bnep0")
        DhcpClient.querying.append("bnep0")

        try:
            with pytest.raises(DhcpClientError, match="DHCP already running"):
                client.run()
        finally:
            DhcpClient.querying.clear()

    @patch("blueman.main.DhcpClient.GLib.timeout_add")
    @patch("blueman.main.DhcpClient.subprocess.Popen", side_effect=OSError("spawn failed"))
    @patch("blueman.main.DhcpClient.have", return_value="/usr/bin/dhclient")
    def test_run_clears_querying_when_process_spawn_fails(
        self,
        _have: Mock,
        _popen: Mock,
        timeout_add: Mock,
    ) -> None:
        client = DhcpClient("bnep0")

        with pytest.raises(OSError, match="spawn failed"):
            client.run()

        assert DhcpClient.querying == []
        timeout_add.assert_not_called()

    @patch("blueman.main.DhcpClient.GLib.source_remove")
    def test_check_client_clears_timeout_on_success(self, source_remove: Mock) -> None:
        check_client = getattr(DhcpClient, "_check_client")
        client = DhcpClient("bnep0")
        client.__dict__["_client"] = Mock()
        client.__dict__["_client"].poll.return_value = 0
        client.__dict__["_timeout_source_id"] = 77
        DhcpClient.querying[:] = ["bnep0"]

        with patch("blueman.main.DhcpClient.get_local_interfaces", return_value={"bnep0": ("10.0.0.2",)}), \
                patch("blueman.main.DhcpClient.GLib.timeout_add") as timeout_add:
            keep_running = check_client(client)

        assert keep_running is False
        source_remove.assert_called_once_with(77)
        assert client.__dict__["_timeout_source_id"] is None
        assert DhcpClient.querying == []
        timeout_add.assert_called_once()

    def test_on_timeout_ignores_already_exited_client(self) -> None:
        on_timeout = getattr(DhcpClient, "_on_timeout")
        client = DhcpClient("bnep0")
        process = Mock()
        process.poll.return_value = 0
        client.__dict__["_client"] = process
        client.__dict__["_timeout_source_id"] = 55

        result = on_timeout(client)

        assert result is False
        process.terminate.assert_not_called()
        assert client.__dict__["_timeout_source_id"] is None