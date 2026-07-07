from types import SimpleNamespace
from unittest.mock import Mock, patch

from blueman.main.PulseAudioUtils import EventType
from blueman.plugins.applet.PulseAudioProfile import AudioProfiles


class TestAudioProfiles:
    def test_on_unload_marks_plugin_inactive(self) -> None:
        pa = Mock()
        pa.handler_is_connected.return_value = True
        plugin = SimpleNamespace(
            _active=True,
            _pa=pa,
            _pa_event_handler_id=3,
            _pa_connected_handler_id=5,
            clear_menu=Mock(),
        )

        AudioProfiles.on_unload(plugin)

        assert getattr(plugin, "_active") is False
        pa.disconnect.assert_any_call(3)
        pa.disconnect.assert_any_call(5)
        plugin.clear_menu.assert_called_once_with()

    def test_on_unload_ignores_stale_handler_ids(self) -> None:
        pa = Mock()
        pa.handler_is_connected.return_value = False
        plugin = SimpleNamespace(
            _active=True,
            _pa=pa,
            _pa_event_handler_id=3,
            _pa_connected_handler_id=5,
            clear_menu=Mock(),
        )

        AudioProfiles.on_unload(plugin)

        assert getattr(plugin, "_active") is False
        pa.disconnect.assert_not_called()
        assert getattr(plugin, "_pa_event_handler_id") is None
        assert getattr(plugin, "_pa_connected_handler_id") is None
        plugin.clear_menu.assert_called_once_with()

    @patch("blueman.plugins.applet.PulseAudioProfile.PulseAudioUtils")
    def test_late_query_pa_callback_after_unload_does_not_add_menu(self, pa_cls: Mock) -> None:
        callbacks: dict[str, object] = {}
        pa = Mock()
        pa.list_cards.side_effect = lambda callback: callbacks.update(list_cb=callback)
        pa_cls.return_value = pa
        plugin = SimpleNamespace(_active=True, _devices={}, add_device_profile_menu=Mock())
        device = {"Address": "AA:BB:CC:DD:EE:FF"}

        AudioProfiles.query_pa(plugin, device)
        plugin.__dict__["_active"] = False

        list_cb = callbacks["list_cb"]
        assert callable(list_cb)
        list_cb({"card0": {"proplist": {"device.string": "AA:BB:CC:DD:EE:FF"}}})

        assert getattr(plugin, "_devices") == {}
        plugin.add_device_profile_menu.assert_not_called()

    def test_late_get_card_callback_after_unload_does_not_rebuild_menu(self) -> None:
        callbacks: dict[str, object] = {}
        utils = SimpleNamespace(get_card=lambda _idx, callback: callbacks.update(get_card_cb=callback))
        plugin = SimpleNamespace(
            _active=True,
            _devices={},
            clear_menu=Mock(),
            generate_menu=Mock(),
        )

        AudioProfiles.on_pa_event(plugin, utils, int(EventType.CARD | EventType.CHANGE), 7)
        plugin.__dict__["_active"] = False

        get_card_cb = callbacks["get_card_cb"]
        assert callable(get_card_cb)
        get_card_cb({
            "driver": "module-bluetooth-device.c",
            "proplist": {"device.string": "AA:BB:CC:DD:EE:FF"},
        })

        assert getattr(plugin, "_devices") == {}
        plugin.clear_menu.assert_not_called()
        plugin.generate_menu.assert_not_called()