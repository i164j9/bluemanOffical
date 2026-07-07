from types import SimpleNamespace
from unittest.mock import Mock

from blueman.plugins.applet.KillSwitch import KillSwitch


class TestKillSwitch:
    def test_on_unload_marks_plugin_inactive(self) -> None:
        monitor = Mock()
        plugin = SimpleNamespace(
            _active=True,
            _connman_watch_id=11,
            _connman_proxy=Mock(),
            _monitor=monitor,
            _monitor_handler_id=7,
            _rfkill=Mock(),
            _iom=None,
        )

        KillSwitch.on_unload(plugin)

        assert getattr(plugin, "_active") is False
        monitor.disconnect.assert_called_once_with(7)
        monitor.cancel.assert_called_once_with()
        assert getattr(plugin, "_connman_proxy") is None
        assert getattr(plugin, "_monitor") is None
        assert getattr(plugin, "_rfkill") is None

    def test_late_reply_after_unload_does_not_invoke_power_callback(self) -> None:
        callbacks: dict[str, object] = {}
        connman_proxy = SimpleNamespace(
            SetProperty=lambda _sig, _name, _value, result_handler, error_handler:
            callbacks.update(reply=result_handler, error=error_handler)
        )
        callback = Mock()
        plugin = SimpleNamespace(_active=True, _connman_proxy=connman_proxy)

        KillSwitch.on_power_state_change_requested(plugin, Mock(), True, callback)
        plugin.__dict__["_active"] = False

        reply = callbacks["reply"]
        assert callable(reply)
        reply()

        callback.assert_not_called()

    def test_late_error_after_unload_does_not_invoke_power_callback(self) -> None:
        callbacks: dict[str, object] = {}
        connman_proxy = SimpleNamespace(
            SetProperty=lambda _sig, _name, _value, result_handler, error_handler:
            callbacks.update(reply=result_handler, error=error_handler)
        )
        callback = Mock()
        plugin = SimpleNamespace(_active=True, _connman_proxy=connman_proxy)

        KillSwitch.on_power_state_change_requested(plugin, Mock(), False, callback)
        plugin.__dict__["_active"] = False

        error = callbacks["error"]
        assert callable(error)
        error()

        callback.assert_not_called()