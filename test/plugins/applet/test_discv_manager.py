from unittest.mock import Mock

from blueman.plugins.applet.DiscvManager import DiscvManager


class TestDiscvManager:
    def test_adapter_removed_ignores_stale_event(self) -> None:
        plugin = object.__new__(DiscvManager)
        plugin.adapter = None
        plugin.init_adapter = Mock()
        plugin.update_menuitems = Mock()

        plugin.on_adapter_removed("/org/bluez/hci0")

        plugin.init_adapter.assert_not_called()
        plugin.update_menuitems.assert_not_called()

    def test_adapter_removed_ignores_other_adapter(self) -> None:
        plugin = object.__new__(DiscvManager)
        plugin.adapter = Mock()
        plugin.adapter.get_object_path.return_value = "/org/bluez/hci0"
        plugin.init_adapter = Mock()
        plugin.update_menuitems = Mock()

        plugin.on_adapter_removed("/org/bluez/hci1")

        plugin.init_adapter.assert_not_called()
        plugin.update_menuitems.assert_not_called()

    def test_adapter_removed_refreshes_current_adapter(self) -> None:
        plugin = object.__new__(DiscvManager)
        plugin.adapter = Mock()
        plugin.adapter.get_object_path.return_value = "/org/bluez/hci0"
        plugin.init_adapter = Mock()
        plugin.update_menuitems = Mock()

        plugin.on_adapter_removed("/org/bluez/hci0")

        plugin.init_adapter.assert_called_once_with()
        plugin.update_menuitems.assert_called_once_with()