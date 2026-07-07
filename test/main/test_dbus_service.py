from unittest.mock import Mock, patch

from gi.repository import Gio, GLib

from blueman.main.DbusService import DbusService


class TestDbusService:
    @patch("blueman.main.DbusService.Gio.bus_get_sync")
    def test_unknown_method_returns_unknown_method_error_once(self, bus_get_sync: Mock) -> None:
        handle_method_call = getattr(DbusService, "_handle_method_call")
        bus_get_sync.return_value = Mock()
        service = DbusService(None, "org.blueman.Test", "/org/blueman/test", Gio.BusType.SESSION)
        service.__dict__["_return_dbus_error"] = Mock()
        invocation = Mock()

        handle_method_call(
            service,
            Mock(),
            "sender",
            "/org/blueman/test",
            "org.blueman.Test",
            "MissingMethod",
            GLib.Variant("()", ()),
            invocation,
        )

        invocation.return_error_literal.assert_called_once_with(
            Gio.dbus_error_quark(),
            Gio.DBusError.UNKNOWN_METHOD,
            "No such method on interface: org.blueman.Test.MissingMethod",
        )
        service.__dict__["_return_dbus_error"].assert_not_called()
        invocation.return_value.assert_not_called()