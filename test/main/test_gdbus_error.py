from typing import cast

import pytest
from gi.repository import GLib, Gio

from blueman.main.indicators.StatusNotifierItem import is_service_unknown


dbusmock = pytest.importorskip("dbusmock")


class TestGDbusError(dbusmock.DBusTestCase):
    def test_is_service_unknown(self):
        self.start_session_bus()
        no_dbus_call_flags = cast(Gio.DBusCallFlags, 0)

        error = None

        try:
            Gio.bus_get_sync(Gio.BusType.SESSION).call_sync(
                "some.name", "/some/path", "some.Interface",
                "SomeMethod", GLib.Variant("()", ()),
                None, no_dbus_call_flags, -1)
        except GLib.Error as e:
            error = e

        self.assertTrue(is_service_unknown(error))
