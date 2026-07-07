from unittest.mock import Mock, patch

from blueman.main.BatteryWatcher import BatteryWatcher


class TestBatteryWatcher:
    @patch("blueman.main.BatteryWatcher.AnyBattery")
    @patch("blueman.main.BatteryWatcher.Manager")
    def test_destroy_disconnects_registered_signals(self, manager_cls: Mock, any_battery_cls: Mock) -> None:
        manager = Mock()
        manager.connect_signal.return_value = 11
        manager_cls.return_value = manager
        any_battery = Mock()
        any_battery.connect_signal.return_value = 22
        any_battery_cls.return_value = any_battery

        watcher = BatteryWatcher(lambda _path, _value: None)
        watcher.destroy()

        manager.disconnect_signal.assert_called_once_with(11)
        any_battery.disconnect_signal.assert_called_once_with(22)

    @patch("blueman.main.BatteryWatcher.AnyBattery")
    @patch("blueman.main.BatteryWatcher.Manager")
    def test_destroy_is_idempotent(self, manager_cls: Mock, any_battery_cls: Mock) -> None:
        manager = Mock()
        manager.connect_signal.return_value = 11
        manager_cls.return_value = manager
        any_battery = Mock()
        any_battery.connect_signal.return_value = 22
        any_battery_cls.return_value = any_battery

        watcher = BatteryWatcher(lambda _path, _value: None)
        watcher.destroy()
        watcher.destroy()

        manager.disconnect_signal.assert_called_once_with(11)
        any_battery.disconnect_signal.assert_called_once_with(22)