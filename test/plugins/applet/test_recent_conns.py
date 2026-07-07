from types import SimpleNamespace
from unittest.mock import Mock, patch

from blueman.plugins.applet.RecentConns import RecentConns


class TestRecentConns:
    def test_rebuild_clears_stale_menu_items_when_connections_disappear(self) -> None:
        clear_menu_items = getattr(RecentConns, "_clear_menu_items")
        rebuild = getattr(RecentConns, "_rebuild")
        plugin = SimpleNamespace(
            parent=SimpleNamespace(Plugins=SimpleNamespace(get_loaded=lambda: [])),
            _mitems=[Mock(), Mock()],
            _RecentConns__menuitems=[{"text": "Old"}],
        )
        plugin.__dict__["_get_items"] = lambda: []
        plugin.__dict__["_rebuild_menu"] = Mock()
        plugin.__dict__["_clear_menu_items"] = lambda: clear_menu_items(plugin)

        rebuild(plugin)

        assert plugin.__dict__["_RecentConns__menuitems"] == []
        plugin.__dict__["_rebuild_menu"].assert_called_once_with()

    def test_rebuild_clears_stale_menu_items_when_bluetooth_is_off(self) -> None:
        clear_menu_items = getattr(RecentConns, "_clear_menu_items")
        rebuild = getattr(RecentConns, "_rebuild")
        plugin = SimpleNamespace(
            parent=SimpleNamespace(
                Plugins=SimpleNamespace(
                    get_loaded=lambda: ["PowerManager"],
                    PowerManager=SimpleNamespace(get_bluetooth_status=lambda: False),
                )
            ),
            _mitems=[Mock()],
            _RecentConns__menuitems=[{"text": "Old"}],
        )
        plugin.__dict__["_rebuild_menu"] = Mock()
        plugin.__dict__["_clear_menu_items"] = lambda: clear_menu_items(plugin)

        rebuild(plugin)

        assert plugin.__dict__["_RecentConns__menuitems"] == []
        plugin.__dict__["_rebuild_menu"].assert_called_once_with()

    def test_build_menu_item_uses_no_tooltip_for_available_device(self) -> None:
        build_menu_item = getattr(RecentConns, "_build_menu_item")
        plugin = SimpleNamespace(on_item_activated=Mock())
        item = {
            "adapter": "00:11:22:33:44:55",
            "address": "AA:BB:CC:DD:EE:FF",
            "alias": "Phone",
            "icon": "phone-icon",
            "name": "Audio Sink",
            "uuid": "0000110b-0000-1000-8000-00805f9b34fb",
            "time": 1.0,
            "device": "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF",
            "mitem": None,
        }

        menu_item = build_menu_item(plugin, item)

        assert menu_item["tooltip"] is None

    def test_manager_state_change_clears_stale_menu_items(self) -> None:
        clear_menu_items = getattr(RecentConns, "_clear_menu_items")
        plugin = SimpleNamespace(
            _RecentConns__menuitems=[{"text": "Old"}],
        )
        plugin.__dict__["_rebuild_menu"] = Mock()
        plugin.__dict__["_clear_menu_items"] = lambda: clear_menu_items(plugin)

        RecentConns.on_manager_state_changed(plugin, False)

        assert plugin.__dict__["_RecentConns__menuitems"] == []
        plugin.__dict__["_rebuild_menu"].assert_called_once_with()

    def test_on_unload_marks_plugin_inactive(self) -> None:
        plugin = SimpleNamespace(
            _active=True,
            parent=SimpleNamespace(Plugins=SimpleNamespace(Menu=SimpleNamespace(unregister=Mock()))),
        )

        RecentConns.on_unload(plugin)

        assert getattr(plugin, "_active") is False
        plugin.parent.Plugins.Menu.unregister.assert_called_once_with(plugin)

    @patch("blueman.plugins.applet.RecentConns.Notification")
    def test_late_reply_after_unload_does_not_notify_or_refresh_menu(self, notification_cls: Mock) -> None:
        callbacks: dict[str, object] = {}
        menu = SimpleNamespace(on_menu_changed=Mock())
        item = {
            "adapter": "00:11:22:33:44:55",
            "address": "AA:BB:CC:DD:EE:FF",
            "alias": "Phone",
            "icon": "phone-icon",
            "name": "Audio Sink",
            "uuid": "0000110b-0000-1000-8000-00805f9b34fb",
            "time": 1.0,
            "device": "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF",
            "mitem": {"text": "Audio Sink on Phone", "sensitive": True},
        }
        plugin = SimpleNamespace(
            _active=True,
            parent=SimpleNamespace(
                Plugins=SimpleNamespace(
                    Menu=menu,
                    DBusService=SimpleNamespace(
                        connect_service=lambda _path, _uuid, ok, err: callbacks.update(ok=ok, err=err)
                    ),
                )
            ),
        )

        RecentConns.on_item_activated(plugin, item)
        plugin.__dict__["_active"] = False

        reply = callbacks["ok"]
        assert callable(reply)
        reply()

        notification_cls.assert_not_called()
        assert item["mitem"]["sensitive"] is False
        menu.on_menu_changed.assert_called_once_with()