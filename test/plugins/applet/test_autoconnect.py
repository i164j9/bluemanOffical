from types import SimpleNamespace
from unittest.mock import Mock, patch

from blueman.plugins.applet.AutoConnect import AutoConnect


class TestAutoConnect:
    def test_on_unload_marks_plugin_inactive(self) -> None:
        stop_timer = getattr(AutoConnect, "stop_timer")
        plugin = SimpleNamespace(_active=True, stop_timer=lambda: stop_timer(plugin))
        plugin.__dict__["_AutoConnect__event_source"] = None

        AutoConnect.on_unload(plugin)

        assert getattr(plugin, "_active") is False

    @patch("blueman.plugins.applet.AutoConnect.Notification")
    def test_late_reply_after_unload_does_not_show_notification(self, notification_cls: Mock) -> None:
        callbacks: dict[str, object] = {}
        device = SimpleNamespace(
            get=lambda key: False if key == "Connected" else None,
            get_object_path=lambda: "/dev/path",
            display_name="Phone",
            __getitem__=lambda self, key: "phone-icon",
        )
        plugin = SimpleNamespace(
            _active=True,
            parent=SimpleNamespace(
                Manager=SimpleNamespace(find_device=lambda _address: device),
                Plugins=SimpleNamespace(
                    DBusService=SimpleNamespace(
                        connect_service=lambda _path, _uuid, ok, err: callbacks.update(ok=ok, err=err)
                    )
                ),
            ),
            get_option=lambda key: [("AA:BB:CC:DD:EE:FF", "0000110b-0000-1000-8000-00805f9b34fb")]
            if key == "services" else True,
        )

        getattr(AutoConnect, "_run")(plugin)
        AutoConnect.on_unload(SimpleNamespace(_active=True, stop_timer=Mock()))
        plugin.__dict__["_active"] = False

        reply = callbacks["ok"]
        assert callable(reply)
        reply()

        notification_cls.assert_not_called()