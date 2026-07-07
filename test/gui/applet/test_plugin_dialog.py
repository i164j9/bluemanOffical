from types import SimpleNamespace
from unittest.mock import Mock

from blueman.gui.applet.PluginDialog import PluginDialog


class TestPluginDialog:
    def test_disconnect_plugin_handlers_is_idempotent(self) -> None:
        plugins = SimpleNamespace(disconnect=Mock())
        dialog = SimpleNamespace(
            applet=SimpleNamespace(Plugins=plugins),
            sig_a=3,
            sig_b=5,
        )

        disconnect_handlers = getattr(PluginDialog, "_disconnect_plugin_handlers")
        disconnect_handlers(dialog)
        disconnect_handlers(dialog)

        plugins.disconnect.assert_any_call(3)
        plugins.disconnect.assert_any_call(5)
        assert plugins.disconnect.call_count == 2
        assert getattr(dialog, "sig_a") is None
        assert getattr(dialog, "sig_b") is None

    def test_on_destroy_disconnects_plugin_handlers(self) -> None:
        disconnect_handlers = Mock()
        dialog = SimpleNamespace(_disconnect_plugin_handlers=disconnect_handlers)

        getattr(PluginDialog, "_on_destroy")(dialog, object())

        disconnect_handlers.assert_called_once_with()