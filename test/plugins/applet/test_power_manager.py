from types import SimpleNamespace
from unittest.mock import Mock, patch

from blueman.plugins.applet.PowerManager import PowerManager


class TestPowerManagerCallback:
    @patch("blueman.plugins.applet.PowerManager.GLib.timeout_add", return_value=17)
    @patch("blueman.plugins.applet.PowerManager.GLib.source_remove")
    def test_cancel_ignores_late_callback_and_timeout(self, source_remove: Mock, _timeout_add: Mock) -> None:
        parent = SimpleNamespace(
            track_callback=Mock(),
            forget_callback=Mock(),
            set_adapter_state=Mock(),
            update_power_state=Mock(),
            request_in_progress=True,
        )

        callback = PowerManager.Callback(parent, True)
        callback.num_cb = 1

        callback.cancel()
        callback(True)
        result = callback.timeout()

        assert result is False
        source_remove.assert_called_once_with(17)
        parent.forget_callback.assert_called_once_with(callback)
        parent.set_adapter_state.assert_not_called()
        parent.update_power_state.assert_not_called()
        assert parent.request_in_progress is True

    @patch("blueman.plugins.applet.PowerManager.GLib.timeout_add", return_value=29)
    @patch("blueman.plugins.applet.PowerManager.GLib.source_remove")
    def test_completed_callback_updates_parent_once(self, source_remove: Mock, _timeout_add: Mock) -> None:
        parent = SimpleNamespace(
            track_callback=Mock(),
            forget_callback=Mock(),
            set_adapter_state=Mock(),
            update_power_state=Mock(),
            request_in_progress=True,
        )

        callback = PowerManager.Callback(parent, False)
        callback.num_cb = 1

        callback(True)

        source_remove.assert_called_once_with(29)
        parent.forget_callback.assert_called_once_with(callback)
        parent.set_adapter_state.assert_called_once_with(False)
        parent.update_power_state.assert_called_once_with()
        assert parent.request_in_progress is False