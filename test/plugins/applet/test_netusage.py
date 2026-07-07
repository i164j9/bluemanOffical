from types import SimpleNamespace
from unittest.mock import Mock, patch

from blueman.plugins.applet.NetUsage import Dialog, Monitor, NetUsage


class TestNetUsageDialog:
    def teardown_method(self) -> None:
        Dialog.active_dialog = None

    def test_present_existing_returns_false_without_dialog(self) -> None:
        assert Dialog.present_existing() is False

    def test_present_existing_presents_active_dialog(self) -> None:
        dialog = object.__new__(Dialog)
        dialog.present = Mock()
        Dialog.active_dialog = dialog

        assert Dialog.present_existing() is True
        dialog.present.assert_called_once_with()


class TestMonitor:
    @patch("blueman.plugins.applet.NetUsage.GLib.source_remove")
    def test_destroy_removes_poller(self, source_remove: Mock) -> None:
        monitor = SimpleNamespace(poller=19, ppp_port="ppp0")

        Monitor.destroy(monitor)

        source_remove.assert_called_once_with(19)
        assert getattr(monitor, "poller") is None
        assert getattr(monitor, "ppp_port") is None


class TestNetUsage:
    def teardown_method(self) -> None:
        Dialog.active_dialog = None

    def test_on_unload_destroys_runtime_state(self) -> None:
        menu = SimpleNamespace(unregister=Mock())
        any_network = Mock()
        monitors = [Mock(), Mock()]
        plugin = SimpleNamespace(
            _any_network=any_network,
            monitors=monitors,
            parent=SimpleNamespace(Plugins=SimpleNamespace(Menu=menu)),
        )
        dialog = SimpleNamespace(plugin=plugin, on_response=Mock())
        Dialog.active_dialog = dialog

        NetUsage.on_unload(plugin)

        dialog.on_response.assert_called_once_with(None, None)
        any_network.destroy.assert_called_once_with()
        assert getattr(plugin, "_any_network") is None
        for monitor in monitors:
            monitor.destroy.assert_called_once_with()
        assert getattr(plugin, "monitors") == []
        menu.unregister.assert_called_once_with(plugin)