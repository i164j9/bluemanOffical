from unittest.mock import Mock, patch

import pytest
from gi.repository import GLib

from blueman.main.MechanismApplication import MechanismApplication


class TestMechanismApplication:
    @patch("blueman.main.MechanismApplication.POLKIT", True)
    @patch("blueman.main.MechanismApplication.MechanismPlugin.__subclasses__", return_value=[])
    @patch("blueman.main.MechanismApplication.plugin_names", return_value=[])
    @patch("blueman.main.MechanismApplication.Timer")
    @patch("blueman.main.MechanismApplication.GLib.MainLoop")
    @patch("blueman.main.MechanismApplication.DbusService.__init__", return_value=None)
    @patch("blueman.main.MechanismApplication.DbusService.register")
    @patch("blueman.main.MechanismApplication.Gio.DBusProxy.new_for_bus_sync")
    def test_polkit_glib_error_degrades_to_none(
        self,
        new_for_bus_sync: Mock,
        _register: Mock,
        _dbus_init: Mock,
        _main_loop: Mock,
        _timer: Mock,
        _plugin_names: Mock,
        _subclasses: Mock,
    ) -> None:
        new_for_bus_sync.side_effect = GLib.Error("policykit unavailable")

        app = MechanismApplication(stoptimer=False)

        assert app.pk is None

    @patch("blueman.main.MechanismApplication.POLKIT", True)
    @patch("blueman.main.MechanismApplication.MechanismPlugin.__subclasses__", return_value=[])
    @patch("blueman.main.MechanismApplication.plugin_names", return_value=[])
    @patch("blueman.main.MechanismApplication.Timer")
    @patch("blueman.main.MechanismApplication.GLib.MainLoop")
    @patch("blueman.main.MechanismApplication.DbusService.__init__", return_value=None)
    @patch("blueman.main.MechanismApplication.DbusService.register")
    @patch("blueman.main.MechanismApplication.Gio.DBusProxy.new_for_bus_sync")
    def test_unexpected_polkit_error_still_propagates(
        self,
        new_for_bus_sync: Mock,
        _register: Mock,
        _dbus_init: Mock,
        _main_loop: Mock,
        _timer: Mock,
        _plugin_names: Mock,
        _subclasses: Mock,
    ) -> None:
        new_for_bus_sync.side_effect = RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            MechanismApplication(stoptimer=False)