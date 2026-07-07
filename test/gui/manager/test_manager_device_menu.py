from types import SimpleNamespace
from unittest.mock import ANY, Mock, patch

from gi.repository import GLib

from blueman.gui.manager.ManagerDeviceMenu import ManagerDeviceMenu


class TestManagerDeviceMenu:
    def test_cleanup_disconnects_watchers_and_unregisters_instance(self) -> None:
        cleanup = getattr(ManagerDeviceMenu, "_cleanup")
        any_network = Mock()
        any_network.handler_is_connected.return_value = True
        any_device = Mock()
        any_device.handler_is_connected.return_value = True
        list_view = Mock()
        list_view.handler_is_connected.return_value = True
        menu = SimpleNamespace(
            _cleanup_done=False,
            Blueman=SimpleNamespace(List=list_view),
            _device_property_changed_signal=11,
            _any_network=any_network,
            _any_network_handler=22,
            _any_device=any_device,
            _any_device_handler=33,
        )
        original_instances = ManagerDeviceMenu.__instances__
        ManagerDeviceMenu.__instances__ = [menu]

        try:
            cleanup(menu)
            cleanup(menu)

            list_view.disconnect.assert_called_once_with(11)
            any_network.disconnect_signal.assert_called_once_with(22)
            any_network.destroy.assert_called_once_with()
            any_device.disconnect_signal.assert_called_once_with(33)
            any_device.destroy.assert_called_once_with()
            assert menu.__dict__["_cleanup_done"] is True
            assert ManagerDeviceMenu.__instances__ == []
        finally:
            ManagerDeviceMenu.__instances__ = original_instances

    def test_cleanup_skips_stale_watchers(self) -> None:
        cleanup = getattr(ManagerDeviceMenu, "_cleanup")
        any_network = Mock()
        any_network.handler_is_connected.return_value = False
        any_device = Mock()
        any_device.handler_is_connected.return_value = False
        list_view = Mock()
        list_view.handler_is_connected.return_value = False
        menu = SimpleNamespace(
            _cleanup_done=False,
            Blueman=SimpleNamespace(List=list_view),
            _device_property_changed_signal=11,
            _any_network=any_network,
            _any_network_handler=22,
            _any_device=any_device,
            _any_device_handler=33,
        )
        original_instances = ManagerDeviceMenu.__instances__
        ManagerDeviceMenu.__instances__ = [menu]

        try:
            cleanup(menu)

            list_view.disconnect.assert_not_called()
            any_network.disconnect_signal.assert_not_called()
            any_network.destroy.assert_called_once_with()
            any_device.disconnect_signal.assert_not_called()
            any_device.destroy.assert_called_once_with()
            assert menu.__dict__["_cleanup_done"] is True
            assert ManagerDeviceMenu.__instances__ == []
        finally:
            ManagerDeviceMenu.__instances__ = original_instances

    @patch("blueman.gui.manager.ManagerDeviceMenu.logging.debug")
    @patch("blueman.gui.manager.ManagerDeviceMenu.ManagerProgressbar")
    def test_connect_service_ignores_late_failure_after_success(self, progress_cls: Mock, logging_debug: Mock) -> None:
        progress = Mock()
        progress_cls.return_value = progress
        device = SimpleNamespace(get_object_path=lambda: "/org/bluez/hci0/dev_04_C8_B0_D5_4F_28")
        handle_error_message = Mock()

        def connect_service(_signature: str, _path: str, _uuid: str, *, result_handler, error_handler, timeout: int) -> None:
            del timeout
            result_handler(Mock(), None, None)
            error_handler(
                None,
                GLib.Error(
                    "GDBus.Error:org.freedesktop.DBus.Error.Failed: "
                    "blueman.bluez.errors.DBusFailedError:  br-connection-canceled"
                ),
                None,
            )

        menu = SimpleNamespace(
            GENERIC_CONNECT=ManagerDeviceMenu.GENERIC_CONNECT,
            Blueman=Mock(),
            _appl=SimpleNamespace(ConnectService=connect_service),
            set_op=Mock(),
            unset_op=Mock(),
            disconnect_service=Mock(),
            _handle_error_message=handle_error_message,
        )

        ManagerDeviceMenu.connect_service(menu, device)

        progress.message.assert_called_once_with("Success!")
        progress.finalize.assert_not_called()
        menu.unset_op.assert_called_once_with(device)
        handle_error_message.assert_not_called()
        logging_debug.assert_called_once_with("ignoring late connect failure %s", ANY)

    @patch("blueman.gui.manager.ManagerDeviceMenu.logging.debug")
    @patch("blueman.gui.manager.ManagerDeviceMenu.ManagerProgressbar")
    def test_connect_service_suppresses_canceled_error(self, progress_cls: Mock, logging_debug: Mock) -> None:
        progress = Mock()
        progress_cls.return_value = progress
        device = SimpleNamespace(get_object_path=lambda: "/org/bluez/hci0/dev_04_C8_B0_D5_4F_28")
        handle_error_message = Mock()

        def connect_service(_signature: str, _path: str, _uuid: str, *, result_handler, error_handler, timeout: int) -> None:
            del result_handler, timeout
            error_handler(
                None,
                GLib.Error(
                    "GDBus.Error:org.freedesktop.DBus.Error.Failed: "
                    "blueman.bluez.errors.DBusFailedError:  br-connection-canceled"
                ),
                None,
            )

        menu = SimpleNamespace(
            GENERIC_CONNECT=ManagerDeviceMenu.GENERIC_CONNECT,
            Blueman=Mock(),
            _appl=SimpleNamespace(ConnectService=connect_service),
            set_op=Mock(),
            unset_op=Mock(),
            disconnect_service=Mock(),
            _handle_error_message=handle_error_message,
        )

        ManagerDeviceMenu.connect_service(menu, device)

        progress.message.assert_not_called()
        progress.finalize.assert_called_once_with()
        menu.unset_op.assert_called_once_with(device)
        handle_error_message.assert_not_called()
        logging_debug.assert_called_once_with("connect canceled %s", ANY)