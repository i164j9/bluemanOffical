from types import SimpleNamespace
from unittest.mock import Mock

from blueman.plugins.applet.ShowConnected import ShowConnected


class TestShowConnected:
    def test_on_unload_restores_default_tooltip_state(self) -> None:
        status_icon = Mock()
        battery_watcher = Mock()
        plugins = SimpleNamespace(
            StatusIcon=status_icon,
            PowerManager=SimpleNamespace(get_bluetooth_status=lambda: True),
            get_loaded=lambda: ["PowerManager"],
            disconnect=Mock(),
        )
        plugin = SimpleNamespace(
            parent=SimpleNamespace(Plugins=plugins),
            _connections={"/dev"},
            active=True,
            initialized=True,
            _handlers=[11, 12],
            _enumerate_source_id=None,
            _battery_watcher=battery_watcher,
        )
        plugin.__dict__["_set_default_tooltip_title"] = lambda: getattr(ShowConnected, "_set_default_tooltip_title")(
            plugin
        )

        ShowConnected.on_unload(plugin)

        status_icon.set_tooltip_text.assert_called_once_with(None)
        status_icon.set_tooltip_title.assert_called_once_with("Bluetooth Enabled")
        status_icon.icon_should_change.assert_called_once_with()
        plugins.disconnect.assert_any_call(11)
        plugins.disconnect.assert_any_call(12)
        battery_watcher.destroy.assert_called_once_with()
        assert getattr(plugin, "_connections") == set()
        assert getattr(plugin, "active") is False
        assert getattr(plugin, "initialized") is False