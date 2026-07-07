from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from blueman.main.PulseAudioUtils import PulseAudioUtils, ContextState
from blueman.gobject import SingletonGObjectMeta


class TestPulseaudioUtils(TestCase):
    def test_metaclass(self):
        self.assertIsInstance(PulseAudioUtils, SingletonGObjectMeta)

    @patch("blueman.main.PulseAudioUtils.GLib.timeout_add", return_value=17)
    def test_schedule_reconnect_is_idempotent(self, timeout_add: Mock) -> None:
        clear_reconnect_timer = getattr(PulseAudioUtils, "clear_reconnect_timer")
        schedule_reconnect = getattr(PulseAudioUtils, "schedule_reconnect")
        utils = SimpleNamespace(_reconnect_source_id=None)
        utils.__dict__["clear_reconnect_timer"] = lambda: clear_reconnect_timer(utils)
        utils.__dict__["connect_pulseaudio"] = Mock(return_value=False)

        schedule_reconnect(utils)
        schedule_reconnect(utils)

        timeout_add.assert_called_once()
        assert getattr(utils, "_reconnect_source_id") == 17

    @patch("blueman.main.PulseAudioUtils.pa_context_set_subscribe_callback")
    @patch("blueman.main.PulseAudioUtils.pa_context_connect")
    @patch("blueman.main.PulseAudioUtils.pa_context_set_state_callback")
    @patch("blueman.main.PulseAudioUtils.pa_context_new", return_value=object())
    @patch("blueman.main.PulseAudioUtils.pa_context_unref")
    @patch("blueman.main.PulseAudioUtils.weakref.proxy", side_effect=lambda obj: obj)
    @patch("blueman.main.PulseAudioUtils.GLib.source_remove")
    def test_connect_pulseaudio_clears_pending_reconnect_timer(
        self,
        source_remove: Mock,
        _weakref_proxy: Mock,
        _pa_context_unref: Mock,
        _pa_context_new: Mock,
        _pa_context_set_state_callback: Mock,
        _pa_context_connect: Mock,
        _pa_context_set_subscribe_callback: Mock,
    ) -> None:
        clear_reconnect_timer = getattr(PulseAudioUtils, "clear_reconnect_timer")
        utils = SimpleNamespace(
            _reconnect_source_id=19,
            connected=False,
            pa_context=None,
            pa_mainloop_api=object(),
            ctx_cb=object(),
            event_cb=object(),
        )
        utils.__dict__["clear_reconnect_timer"] = lambda: clear_reconnect_timer(utils)

        result = PulseAudioUtils.connect_pulseaudio(utils)

        assert result is False
        source_remove.assert_called_once_with(19)
        assert getattr(utils, "_reconnect_source_id") is None
        assert getattr(utils, "pa_context") is not None

    @patch("blueman.main.PulseAudioUtils.pa_context_unref")
    @patch("blueman.main.PulseAudioUtils.pa_context_disconnect")
    @patch("blueman.main.PulseAudioUtils.GLib.source_remove")
    def test_on_delete_clears_reconnect_timer_and_context(
        self,
        source_remove: Mock,
        pa_context_disconnect: Mock,
        pa_context_unref: Mock,
    ) -> None:
        clear_reconnect_timer = getattr(PulseAudioUtils, "clear_reconnect_timer")
        utils = SimpleNamespace(
            _reconnect_source_id=23,
            pa_context=object(),
            pa_mainloop_api=object(),
            ctx_cb=object(),
        )
        context = utils.pa_context
        utils.__dict__["clear_reconnect_timer"] = lambda: clear_reconnect_timer(utils)

        getattr(PulseAudioUtils, "_on_delete")(utils)

        source_remove.assert_called_once_with(23)
        pa_context_disconnect.assert_called_once_with(context)
        pa_context_unref.assert_called_once_with(context)
        assert getattr(utils, "_reconnect_source_id") is None
        assert getattr(utils, "pa_context") is None

    @patch("blueman.main.PulseAudioUtils.logging.debug")
    @patch("blueman.main.PulseAudioUtils.pa_context_get_state", return_value=ContextState.READY)
    @patch("blueman.main.PulseAudioUtils.pa_context_subscribe")
    @patch("blueman.main.PulseAudioUtils.pa_operation_unref")
    @patch("blueman.main.PulseAudioUtils.pythonapi")
    @patch("blueman.main.PulseAudioUtils.GLib.source_remove")
    def test_ready_state_clears_pending_reconnect_timer(
        self,
        source_remove: Mock,
        _pythonapi: Mock,
        _pa_operation_unref: Mock,
        pa_context_subscribe: Mock,
        _pa_context_get_state: Mock,
        logging_debug: Mock,
    ) -> None:
        pa_context_subscribe.return_value = object()
        clear_reconnect_timer = getattr(PulseAudioUtils, "clear_reconnect_timer")
        utils = SimpleNamespace(
            _reconnect_source_id=29,
            connected=False,
            emit=Mock(),
            simple_callback=Mock(),
            prev_state=ContextState.FAILED,
        )
        utils.__dict__["clear_reconnect_timer"] = lambda: clear_reconnect_timer(utils)

        PulseAudioUtils.pa_context_event(object(), utils)

        source_remove.assert_called_once_with(29)
        assert getattr(utils, "_reconnect_source_id") is None
        assert getattr(utils, "connected") is True
        logging_debug.assert_called_once_with(ContextState.READY)
        assert utils.simple_callback.call_args[0][0] is logging_debug
        assert utils.simple_callback.call_args[0][1] is pa_context_subscribe

    @patch("blueman.main.PulseAudioUtils.logging.debug")
    def test_event_callback_logs_debug(self, logging_debug: Mock) -> None:
        utils = SimpleNamespace(emit=Mock())

        getattr(PulseAudioUtils, "_PulseAudioUtils__event_callback")(utils, object(), 25, 170, object())

        logging_debug.assert_called_once_with("%s %s", 25, 170)
        utils.emit.assert_called_once_with("event", 25, 170)

    @patch("blueman.main.PulseAudioUtils.pa_operation_unref")
    def test_init_list_callback_skips_unref_when_operation_creation_fails(self, pa_operation_unref: Mock) -> None:
        init_list_callback = getattr(PulseAudioUtils, "_PulseAudioUtils__init_list_callback")

        class CallbackType:
            def __call__(self, callback: object) -> object:
                return callback

        utils = SimpleNamespace(pa_context=object())
        utils.__dict__["_PulseAudioUtils__list_callback"] = Mock()

        def fake_func(_context: object, *_args: object) -> object:
            return None

        init_list_callback(utils, fake_func, CallbackType(), Mock())

        pa_operation_unref.assert_not_called()

    @patch("blueman.main.PulseAudioUtils.pa_operation_unref")
    def test_simple_callback_skips_unref_when_operation_creation_fails(self, pa_operation_unref: Mock) -> None:
        simple_callback = getattr(PulseAudioUtils, "simple_callback")
        utils = SimpleNamespace(pa_context=object())

        def fake_func(_context: object, *_args: object) -> object:
            return None

        simple_callback(utils, Mock(), fake_func)

        pa_operation_unref.assert_not_called()
