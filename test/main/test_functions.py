from unittest.mock import Mock, patch

from gi.repository import GLib
from gi.repository import Gtk

from blueman.Functions import check_bluetooth_status


class TestFunctions:
    @patch("blueman.Functions.AppletPowerManagerService")
    @patch("blueman.Functions.AppletService")
    def test_check_bluetooth_status_ignores_missing_power_manager_interface_on_get(
        self,
        applet_cls: Mock,
        power_manager_cls: Mock,
    ) -> None:
        applet = Mock()
        applet.QueryPlugins.return_value = ["PowerManager"]
        applet_cls.return_value = applet

        power_manager = Mock()
        power_manager.get_bluetooth_status.side_effect = GLib.Error(
            "GDBus.Error:org.freedesktop.DBus.Error.UnknownMethod: "
            "No such interface \"org.blueman.Applet.PowerManager\" on object at path /org/blueman/Applet"
        )
        power_manager_cls.return_value = power_manager

        exitfunc = Mock()

        check_bluetooth_status("message", exitfunc)

        exitfunc.assert_not_called()
        power_manager.set_bluetooth_status.assert_not_called()

    @patch("blueman.Functions.Gtk.MessageDialog")
    @patch("blueman.Functions.AppletPowerManagerService")
    @patch("blueman.Functions.AppletService")
    def test_check_bluetooth_status_ignores_missing_power_manager_interface_on_set(
        self,
        applet_cls: Mock,
        power_manager_cls: Mock,
        message_dialog_cls: Mock,
    ) -> None:
        applet = Mock()
        applet.QueryPlugins.return_value = ["PowerManager"]
        applet_cls.return_value = applet

        dialog = Mock()
        dialog.run.return_value = Gtk.ResponseType.YES
        message_dialog_cls.return_value = dialog

        power_manager = Mock()
        power_manager.get_bluetooth_status.return_value = False
        power_manager.set_bluetooth_status.side_effect = GLib.Error(
            "GDBus.Error:org.freedesktop.DBus.Error.UnknownMethod: "
            "No such interface \"org.blueman.Applet.PowerManager\" on object at path /org/blueman/Applet"
        )
        power_manager_cls.return_value = power_manager

        exitfunc = Mock()

        check_bluetooth_status("message", exitfunc)

        exitfunc.assert_not_called()