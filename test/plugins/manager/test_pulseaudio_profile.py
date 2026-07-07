from types import SimpleNamespace
from unittest.mock import Mock, patch

from blueman.main.PulseAudioUtils import EventType
from blueman.plugins.manager.PulseAudioProfile import PulseAudioProfile


class TestPulseAudioProfile:
    def test_on_unload_marks_plugin_inactive(self) -> None:
        pa = Mock()
        pa.handler_is_connected.return_value = True
        plugin = SimpleNamespace(
            _active=True,
            _pa=pa,
            _pa_event_handler_id=3,
            _pa_connected_handler_id=5,
        )

        PulseAudioProfile.on_unload(plugin)

        assert getattr(plugin, "_active") is False
        pa.disconnect.assert_any_call(3)
        pa.disconnect.assert_any_call(5)

    def test_on_unload_ignores_stale_handler_ids(self) -> None:
        pa = Mock()
        pa.handler_is_connected.return_value = False
        plugin = SimpleNamespace(
            _active=True,
            _pa=pa,
            _pa_event_handler_id=3,
            _pa_connected_handler_id=5,
        )

        PulseAudioProfile.on_unload(plugin)

        assert getattr(plugin, "_active") is False
        pa.disconnect.assert_not_called()
        assert getattr(plugin, "_pa_event_handler_id") is None
        assert getattr(plugin, "_pa_connected_handler_id") is None

    @patch("blueman.plugins.manager.PulseAudioProfile.PulseAudioUtils")
    def test_late_query_pa_callback_after_unload_does_not_generate_menu(self, pa_cls: Mock) -> None:
        callbacks: dict[str, object] = {}
        pa = Mock()
        pa.list_cards.side_effect = lambda callback: callbacks.update(list_cb=callback)
        pa_cls.return_value = pa
        plugin = SimpleNamespace(_active=True, devices={}, generate_menu=Mock())
        device = {"Address": "AA:BB:CC:DD:EE:FF"}
        item = Mock()

        PulseAudioProfile.query_pa(plugin, device, item)
        plugin.__dict__["_active"] = False

        list_cb = callbacks["list_cb"]
        assert callable(list_cb)
        list_cb({"card0": {"proplist": {"device.string": "AA:BB:CC:DD:EE:FF"}}})

        assert getattr(plugin, "devices") == {}
        plugin.generate_menu.assert_not_called()

    def test_late_get_card_callback_after_unload_does_not_regenerate_menu(self) -> None:
        callbacks: dict[str, object] = {}
        utils = SimpleNamespace(get_card=lambda _idx, callback: callbacks.update(get_card_cb=callback))
        plugin = SimpleNamespace(
            _active=True,
            devices={},
            regenerate_with_device=Mock(),
        )

        PulseAudioProfile.on_pa_event(plugin, utils, int(EventType.CARD | EventType.CHANGE), 7)
        plugin.__dict__["_active"] = False

        get_card_cb = callbacks["get_card_cb"]
        assert callable(get_card_cb)
        get_card_cb({
            "driver": "module-bluetooth-device.c",
            "proplist": {"device.string": "AA:BB:CC:DD:EE:FF"},
        })

        assert getattr(plugin, "devices") == {}
        plugin.regenerate_with_device.assert_not_called()

    def test_non_card_event_does_not_query_card(self) -> None:
        utils = SimpleNamespace(get_card=Mock())
        plugin = SimpleNamespace(
            _active=True,
            devices={},
            regenerate_with_device=Mock(),
        )

        PulseAudioProfile.on_pa_event(plugin, utils, int(EventType.SOURCE_OUTPUT | EventType.CHANGE), 7)

        utils.get_card.assert_not_called()
        plugin.regenerate_with_device.assert_not_called()