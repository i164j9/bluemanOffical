from types import SimpleNamespace

from blueman.plugins.applet.StandardItems import StandardItems


class TestStandardItems:
    def test_plugin_dialog_destroy_clears_cached_window(self) -> None:
        plugin = SimpleNamespace(_plugin_window=object())

        getattr(StandardItems, "_on_plugin_dialog_destroy")(plugin, object())

        assert getattr(plugin, "_plugin_window") is None