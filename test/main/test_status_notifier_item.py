from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from gi.repository import GLib

from blueman.main.indicators.StatusNotifierItem import MenuService, StatusNotifierItem, IndicatorNotAvailable


class TestMenuService:
    @patch("blueman.main.indicators.StatusNotifierItem.GLib.source_remove")
    def test_destroy_removes_revision_source_and_unregisters(self, source_remove: Mock) -> None:
        service = SimpleNamespace(_revision_source_id=17, unregister=Mock())

        MenuService.destroy(service)

        source_remove.assert_called_once_with(17)
        service.unregister.assert_called_once_with()
        assert getattr(service, "_revision_source_id") is None


class TestStatusNotifierItem:
    @patch("blueman.main.indicators.StatusNotifierItem.Gio.bus_unwatch_name")
    def test_destroy_unwatches_name_and_destroys_service(self, bus_unwatch_name: Mock) -> None:
        item = SimpleNamespace(_destroyed=False, _watcher_watch_id=23, _sni=Mock())
        service = getattr(item, "_sni")

        StatusNotifierItem.destroy(item)
        StatusNotifierItem.destroy(item)

        bus_unwatch_name.assert_called_once_with(23)
        service.destroy.assert_called_once_with()
        assert getattr(item, "_destroyed") is True
        assert getattr(item, "_watcher_watch_id") is None

    @patch("blueman.main.indicators.StatusNotifierItem.Gio.bus_unwatch_name")
    @patch("blueman.main.indicators.StatusNotifierItem.Gio.bus_watch_name", return_value=41)
    @patch("blueman.main.indicators.StatusNotifierItem.Gio.bus_get_sync")
    @patch("blueman.main.indicators.StatusNotifierItem.StatusNotifierItemService")
    def test_init_failure_cleans_up_registered_service(
        self,
        service_cls: Mock,
        bus_get_sync: Mock,
        _bus_watch_name: Mock,
        bus_unwatch_name: Mock,
    ) -> None:
        service = Mock()
        service_cls.return_value = service
        bus = Mock()
        bus.call_sync.side_effect = GLib.Error("GDBus.Error:org.freedesktop.DBus.Error.ServiceUnknown: missing")
        bus_get_sync.return_value = bus

        with pytest.raises(IndicatorNotAvailable):
            StatusNotifierItem(SimpleNamespace(activate=Mock(), activate_menu_item=Mock(), activate_status_icon=Mock()),
                               "blueman")

        service.register.assert_called_once_with()
        service.destroy.assert_called_once_with()
        bus_unwatch_name.assert_called_once_with(41)
