from types import SimpleNamespace
from unittest.mock import Mock, patch

from blueman.plugins.applet.PPPSupport import Connection, PPPSupport


class TestConnection:
    def test_cancel_removes_pending_connect_source(self) -> None:
        service = SimpleNamespace(device={"Address": "AA:BB:CC:DD:EE:FF"}, disconnect=Mock())
        applet = SimpleNamespace(Plugins=Mock())
        done = Mock()

        with patch("blueman.plugins.applet.PPPSupport.Connection._modem_manager_running", return_value=True), \
                patch("blueman.plugins.applet.PPPSupport.GLib.timeout_add_seconds", return_value=17), \
                patch("blueman.plugins.applet.PPPSupport.GLib.source_remove") as source_remove:
            connection = Connection(applet, service, 3, Mock(), Mock(), done)
            connection.cancel()

        source_remove.assert_called_once_with(17)
        service.disconnect.assert_not_called()
        done.assert_called_once_with(connection)

    def test_connected_after_cancel_disconnects_service_without_notifying(self) -> None:
        service = SimpleNamespace(device=SimpleNamespace(display_name="Phone"), disconnect=Mock())
        applet = SimpleNamespace(Plugins=SimpleNamespace(get_loaded_plugins=lambda _iface: []))
        reply = Mock()
        err = Mock()
        done = Mock()

        with patch("blueman.plugins.applet.PPPSupport.Connection._modem_manager_running", return_value=True), \
                patch("blueman.plugins.applet.PPPSupport.GLib.timeout_add_seconds", return_value=17), \
                patch("blueman.plugins.applet.PPPSupport.GLib.source_remove"):
            connection = Connection(applet, service, 3, reply, err, done)

        done.reset_mock()
        with patch("blueman.plugins.applet.PPPSupport.GLib.source_remove"):
            connection.cancel()
        service.disconnect.reset_mock()
        done.reset_mock()

        connection.on_connected(Mock(), "ppp0", None)

        service.disconnect.assert_called_once_with(3)
        reply.assert_not_called()
        done.assert_not_called()


class TestPPPSupport:
    def test_on_unload_cancels_tracked_connections(self) -> None:
        connection = Mock()
        plugin = SimpleNamespace(_connections={connection}, _active=True)

        PPPSupport.on_unload(plugin)

        connection.cancel.assert_called_once_with()
        assert getattr(plugin, "_active") is False
        assert getattr(plugin, "_connections") == set()

    @patch("blueman.plugins.applet.PPPSupport.Connection")
    @patch("blueman.plugins.applet.PPPSupport.DialupNetwork", new=SimpleNamespace)
    def test_late_rfcomm_reply_after_unload_disconnects_without_creating_connection(self, connection_cls: Mock) -> None:
        callbacks: dict[str, object] = {}
        service = SimpleNamespace()
        service.connect = lambda reply_handler, error_handler: callbacks.update(reply=reply_handler, error=error_handler)
        service.disconnect = Mock()
        track_connection = Mock()
        plugin = SimpleNamespace(
            _active=True,
            parent=SimpleNamespace(),
            _track_connection=track_connection,
            _forget_connection=Mock(),
        )

        handled = PPPSupport.rfcomm_connect_handler(plugin, service, Mock(), Mock())
        assert handled is True

        plugin.__dict__["_active"] = False
        reply = callbacks["reply"]
        assert callable(reply)
        reply(4)

        service.disconnect.assert_called_once_with(4)
        connection_cls.assert_not_called()
        track_connection.assert_not_called()