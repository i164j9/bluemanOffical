from types import SimpleNamespace
from unittest.mock import Mock, patch

from blueman.plugins.applet.Networking import Networking


class TestNetworking:
    def test_on_unload_marks_plugin_inactive_and_cleans_up(self) -> None:
        dns_provider = Mock()
        config = Mock()
        plugin = SimpleNamespace(
            _active=True,
            _registered={},
            _dns_server_provider=dns_provider,
            _dns_server_provider_handler_id=7,
            _config_handler_id=9,
            Config=config,
        )

        Networking.on_unload(plugin)

        assert getattr(plugin, "_active") is False
        dns_provider.disconnect.assert_called_once_with(7)
        dns_provider.destroy.assert_called_once_with()
        config.disconnect.assert_called_once_with(9)
        assert getattr(plugin, "_dns_server_provider") is None
        assert getattr(plugin, "_registered") == {}

    @patch("blueman.plugins.applet.Networking.ErrorDialog")
    @patch("blueman.plugins.applet.Networking.Mechanism")
    def test_late_enable_network_error_after_unload_is_ignored(self, mechanism_cls: Mock, error_dialog_cls: Mock) -> None:
        callbacks: dict[str, object] = {}
        mechanism = Mock()
        mechanism.EnableNetwork.side_effect = (
            lambda _sig, _addr, _mask, _handler, _flag, result_handler, error_handler:
            callbacks.update(result=result_handler, error=error_handler)
        )
        mechanism_cls.return_value = mechanism
        plugin = SimpleNamespace(
            _active=True,
            Config={
                "nap-enable": True,
                "ip4-address": "10.0.0.1",
                "ip4-netmask": "255.255.255.0",
                "dhcp-handler": "dnsmasq",
            },
        )

        getattr(Networking, "_apply_nap_settings")(plugin)
        plugin.__dict__["_active"] = False

        error = Mock()
        err = callbacks["error"]
        assert callable(err)
        err(Mock(), error, None)

        error_dialog_cls.assert_not_called()