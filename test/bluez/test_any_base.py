from unittest.mock import Mock, patch

from blueman.bluez.AnyBase import AnyBase


class TestAnyBase:
    @patch("blueman.bluez.AnyBase.Gio.bus_get_sync")
    def test_destroy_unsubscribes_signal(self, bus_get_sync: Mock) -> None:
        bus = Mock()
        bus.signal_subscribe.return_value = 17
        bus_get_sync.return_value = bus

        any_base = AnyBase("org.bluez.Network1")
        any_base.destroy()

        bus.signal_unsubscribe.assert_called_once_with(17)

    @patch("blueman.bluez.AnyBase.Gio.bus_get_sync")
    def test_destroy_is_idempotent(self, bus_get_sync: Mock) -> None:
        bus = Mock()
        bus.signal_subscribe.return_value = 17
        bus_get_sync.return_value = bus

        any_base = AnyBase("org.bluez.Network1")
        any_base.destroy()
        any_base.destroy()

        bus.signal_unsubscribe.assert_called_once_with(17)