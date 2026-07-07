from types import SimpleNamespace
from unittest.mock import Mock, patch

from gi.repository import GLib

from blueman.main.PPPConnection import PPPConnection, PPPException


class TestPPPConnection:
    @patch("blueman.main.PPPConnection.subprocess.Popen", side_effect=OSError("spawn failed"))
    def test_connect_callback_converts_pppd_spawn_failure_to_ppp_exception(self, _popen: Mock) -> None:
        connect_callback = getattr(PPPConnection, "connect_callback")
        connection = SimpleNamespace(port="/dev/rfcomm0", cleanup=Mock())

        with patch("blueman.main.PPPConnection.GLib.io_add_watch") as io_add_watch, \
                patch("blueman.main.PPPConnection.GLib.timeout_add") as timeout_add:
            try:
                connect_callback(connection, ["CONNECT"])
            except PPPException as exc:
                assert str(exc) == "Failed to start pppd: spawn failed"
            else:
                raise AssertionError("PPPException was not raised")

        connection.cleanup.assert_called_once_with()
        io_add_watch.assert_not_called()
        timeout_add.assert_not_called()

    @patch("blueman.main.PPPConnection.GLib.source_remove")
    def test_data_ready_clears_timeout_when_reply_is_complete(self, source_remove: Mock) -> None:
        on_data_ready = getattr(PPPConnection, "on_data_ready")
        clear_timeout = getattr(PPPConnection, "_clear_timeout")
        connection = SimpleNamespace(
            file=5,
            buffer="OK\r\n",
            commands=["ATE0"],
            timeout=17,
            io_watch=23,
            cleanup=Mock(),
            _clear_timeout=lambda: clear_timeout(connection),
        )
        connection.__dict__["_PPPConnection__cmd_response_cb"] = Mock()

        with patch("blueman.main.PPPConnection.os.read", return_value=b""):
            keep_running = on_data_ready(connection, 0, GLib.IO_IN, 0)

        assert keep_running is False
        source_remove.assert_called_once_with(17)
        assert connection.timeout is None
        assert connection.io_watch is None
        connection.__dict__["_PPPConnection__cmd_response_cb"].assert_called_once_with(["OK"], None, 0)
        connection.cleanup.assert_not_called()

    @patch("blueman.main.PPPConnection.GLib.source_remove")
    def test_data_ready_clears_timeout_on_socket_error(self, source_remove: Mock) -> None:
        on_data_ready = getattr(PPPConnection, "on_data_ready")
        clear_timeout = getattr(PPPConnection, "_clear_timeout")
        connection = SimpleNamespace(
            timeout=17,
            io_watch=23,
            cleanup=Mock(),
            _clear_timeout=lambda: clear_timeout(connection),
        )
        connection.__dict__["_PPPConnection__cmd_response_cb"] = Mock()

        keep_running = on_data_ready(connection, 0, GLib.IO_ERR, 0)

        assert keep_running is False
        source_remove.assert_called_once_with(17)
        assert connection.timeout is None
        assert connection.io_watch is None
        connection.__dict__["_PPPConnection__cmd_response_cb"].assert_called_once()
        connection.cleanup.assert_called_once_with()

    @patch("blueman.main.PPPConnection.GLib.source_remove")
    def test_timeout_callback_clears_io_watch(self, source_remove: Mock) -> None:
        clear_io_watch = getattr(PPPConnection, "_clear_io_watch")
        callbacks: list[object] = []

        def fake_timeout_add(_interval: int, callback: object) -> int:
            callbacks.append(callback)
            return 17

        connection = SimpleNamespace(
            file=5,
            buffer="",
            term_found=False,
            io_watch=23,
            timeout=None,
            on_data_ready=Mock(),
            cleanup=Mock(),
            _clear_io_watch=lambda: clear_io_watch(connection),
        )
        connection.__dict__["_PPPConnection__cmd_response_cb"] = Mock()

        with patch("blueman.main.PPPConnection.GLib.io_add_watch", return_value=23), \
                patch("blueman.main.PPPConnection.GLib.timeout_add", side_effect=fake_timeout_add):
            PPPConnection.wait_for_reply(connection, 4)

        timeout_callback = callbacks[0]
        assert callable(timeout_callback)
        result = timeout_callback()

        assert result is False
        source_remove.assert_called_once_with(23)
        assert connection.io_watch is None
        assert connection.timeout is None
        callback_args = connection.__dict__["_PPPConnection__cmd_response_cb"].call_args.args
        assert callback_args[0] is None
        assert isinstance(callback_args[1], PPPException)
        assert str(callback_args[1]) == "Modem initialization timed out"
        assert callback_args[2] == 4
        connection.cleanup.assert_called_once_with()