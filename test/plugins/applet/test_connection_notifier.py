from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from blueman.plugins.applet.ConnectionNotifier import ConnectionNotifier


class TestConnectionNotifier:
    def test_on_unload_closes_active_notifications(self) -> None:
        notification = Mock()
        battery_watcher = Mock()
        plugin = SimpleNamespace(
            _notifications={"/dev": notification},
            _battery_watcher=battery_watcher,
        )
        close_notifications = getattr(ConnectionNotifier, "_close_notifications")
        plugin.__dict__["_close_notifications"] = lambda: close_notifications(plugin)

        ConnectionNotifier.on_unload(plugin)

        notification.close.assert_called_once_with()
        battery_watcher.destroy.assert_called_once_with()
        assert getattr(plugin, "_notifications") == {}

    @patch("blueman.plugins.applet.ConnectionNotifier.Notification")
    @patch("blueman.plugins.applet.ConnectionNotifier.Device")
    def test_disconnect_closes_existing_connected_notification(self, device_cls: Mock, notification_cls: Mock) -> None:
        device = MagicMock()
        device.display_name = "Phone"
        device.__getitem__.return_value = "phone-icon"
        device_cls.return_value = device
        stale_notification = Mock()
        disconnected_notification = Mock()
        notification_cls.return_value = disconnected_notification
        plugin = SimpleNamespace(_notifications={"/dev": stale_notification})

        ConnectionNotifier.on_device_property_changed(plugin, "/dev", "Connected", False)

        stale_notification.close.assert_called_once_with()
        notification_cls.assert_called_once_with(
            "Phone",
            "Disconnected",
            icon_name="phone-icon",
            transient=True,
        )
        disconnected_notification.show.assert_called_once_with()
        assert getattr(plugin, "_notifications") == {}