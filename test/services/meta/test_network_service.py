from importlib import import_module
from typing import cast
from unittest import TestCase
from unittest.mock import patch, MagicMock

from blueman.bluemantyping import ObjectPath
from blueman.bluez.Device import Device
from blueman.services.meta.NetworkService import NetworkService

# The package re-exports the NetworkService *class* under the name
# ``blueman.services.meta.NetworkService``, shadowing the submodule. Grab the
# actual module object so we can patch the proxy it imports.
network_service_module = import_module("blueman.services.meta.NetworkService")


def _make_service(object_path: ObjectPath) -> NetworkService:
    device = MagicMock()
    device.get_object_path.return_value = object_path

    with patch.object(network_service_module, "Network"):
        return NetworkService(cast(Device, device), "")


class TestNetworkService(TestCase):
    def test_renew_dispatches_to_dhcp_client_proxy(self):
        path = ObjectPath("/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF")
        service = _make_service(path)
        action = next(iter(service.common_actions))

        with patch.object(network_service_module, "AppletDhcpClientService") as proxy_cls:
            action.callback()

        proxy_cls.assert_called_once_with()
        proxy_cls.return_value.dchp_client.assert_called_once_with(path)
