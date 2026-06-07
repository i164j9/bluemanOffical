from unittest.mock import Mock

from blueman.plugins.manager.Services import get_connect_handler, get_disconnect_handler


class TestServicesHandlers:
    def test_connect_handler_uses_bound_device_and_uuid(self) -> None:
        manager_menu = Mock()
        device = Mock()

        handler = get_connect_handler(manager_menu, device, "uuid-a")
        handler(Mock())

        manager_menu.connect_service.assert_called_once_with(device, "uuid-a")

    def test_disconnect_handler_uses_bound_device_uuid_and_port(self) -> None:
        manager_menu = Mock()
        device = Mock()

        handler = get_disconnect_handler(manager_menu, device, "uuid-b", 7)
        handler(Mock())

        manager_menu.disconnect_service.assert_called_once_with(device, "uuid-b", 7)