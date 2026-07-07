from unittest.mock import Mock
import pytest

from blueman.gui.manager.ManagerDeviceList import (
    apply_row_state_update,
    build_power_tooltip_lines,
    get_power_level_values,
    get_unavailable_power_columns,
    should_monitor_power_levels,
    ManagerDeviceList,
)
from blueman.Sdp import AUDIO_SINK_SVCLASS_ID, OBEX_OBJPUSH_SVCLASS_ID


class TestManagerDeviceList:
    def test_apply_row_state_update_suppresses_stale_row_errors(self) -> None:
        row_update = Mock(side_effect=ValueError("invalid iter"))

        updated = apply_row_state_update(row_update, Mock(), "Connected", True)

        assert updated is False
        row_update.assert_called_once()

    def test_apply_row_state_update_reraises_unexpected_errors(self) -> None:
        row_update = Mock(side_effect=RuntimeError("boom"))

        with pytest.raises(RuntimeError, match="boom"):
            apply_row_state_update(row_update, Mock(), "Connected", True)

    def test_failed_conn_info_does_not_fake_signal_levels(self) -> None:
        device = Mock()
        device.get_object_path.return_value = "/org/bluez/hci0/dev_00_11_22_33_44_55"

        cinfo = Mock()
        cinfo.failed = True

        bars = get_power_level_values({}, device, cinfo)

        assert bars == {}
        cinfo.get_rssi.assert_not_called()
        cinfo.get_tpl.assert_not_called()

    def test_failed_conn_info_keeps_available_battery_level(self) -> None:
        object_path = "/org/bluez/hci0/dev_00_11_22_33_44_55"

        device = Mock()
        device.get_object_path.return_value = object_path

        cinfo = Mock()
        cinfo.failed = True

        bars = get_power_level_values({object_path: {"Percentage": 73.0}}, device, cinfo)

        assert bars == {"battery": 73.0}

    def test_tooltip_explains_unavailable_signal_levels(self) -> None:
        lines = build_power_tooltip_lines("rssi_pb", True, 0.0, 0.0, 0.0, False)

        assert lines == [
            "<b>Connected</b>",
            "Received signal strength is not available for this device.",
        ]

    def test_unavailable_signal_levels_show_placeholder_columns(self) -> None:
        assert get_unavailable_power_columns(False) == ("rssi_pb", "tpl_pb")
        assert get_unavailable_power_columns(True) == ()

    def test_audio_devices_skip_legacy_power_level_monitoring(self) -> None:
        device = {
            "UUIDs": [f"0000{AUDIO_SINK_SVCLASS_ID:04x}-0000-1000-8000-00805F9B34FB"],
        }

        assert should_monitor_power_levels(device) is False

    def test_non_audio_devices_still_use_legacy_power_level_monitoring(self) -> None:
        device = {
            "UUIDs": [f"0000{OBEX_OBJPUSH_SVCLASS_ID:04x}-0000-1000-8000-00805F9B34FB"],
        }

        assert should_monitor_power_levels(device) is True

    def test_monitor_power_levels_skips_conn_info_for_audio_devices(self, monkeypatch: pytest.MonkeyPatch) -> None:
        conn_info_mock = Mock()
        monkeypatch.setattr("blueman.gui.manager.ManagerDeviceList.conn_info", conn_info_mock)

        list_view = Mock()
        list_view.__dict__["_monitored_devices"] = set()
        list_view.__dict__["_update_power_levels"] = Mock()

        device = {
            "Address": "AA:BB:CC:DD:EE:FF",
            "UUIDs": [f"0000{AUDIO_SINK_SVCLASS_ID:04x}-0000-1000-8000-00805F9B34FB"],
        }

        getattr(ManagerDeviceList, "_monitor_power_levels")(list_view, Mock(), device)

        conn_info_mock.assert_not_called()
        getattr(list_view, "_update_power_levels").assert_called_once()

    def test_monitor_power_levels_logs_debug_for_conn_info_read_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cinfo = Mock()

        class FakeConnInfoReadError(Exception):
            pass

        cinfo.init.side_effect = FakeConnInfoReadError()
        conn_info_mock = Mock(return_value=cinfo)
        debug_mock = Mock()
        monkeypatch.setattr("blueman.gui.manager.ManagerDeviceList.conn_info", conn_info_mock)
        monkeypatch.setattr("blueman.gui.manager.ManagerDeviceList.ConnInfoReadError", FakeConnInfoReadError)
        monkeypatch.setattr("blueman.gui.manager.ManagerDeviceList.logging.debug", debug_mock)
        tree_path = Mock()

        class FakeTreeModel:
            def get_path(self, _tree_iter: object) -> object:
                return tree_path

        monkeypatch.setattr("blueman.gui.manager.ManagerDeviceList.Gtk.TreeModel", FakeTreeModel)
        tree_row_reference_new = Mock(return_value=Mock())
        monkeypatch.setattr("blueman.gui.manager.ManagerDeviceList.Gtk.TreeRowReference.new", tree_row_reference_new)
        timeout_add_mock = Mock()
        monkeypatch.setattr("blueman.gui.manager.ManagerDeviceList.GLib.timeout_add", timeout_add_mock)

        list_view = Mock()
        list_view.__dict__["_monitored_devices"] = set()
        list_view.__dict__["_update_power_levels"] = Mock()
        list_view.__dict__["liststore"] = FakeTreeModel()
        list_view.__dict__["Adapter"] = Mock(get_object_path=Mock(return_value="/org/bluez/hci0"))

        device = {
            "Address": "AA:BB:CC:DD:EE:FF",
            "UUIDs": [f"0000{OBEX_OBJPUSH_SVCLASS_ID:04x}-0000-1000-8000-00805F9B34FB"],
        }

        getattr(ManagerDeviceList, "_monitor_power_levels")(list_view, Mock(), device)

        debug_mock.assert_called_once_with(
            "Power levels unavailable for %s, probably a LE device.",
            "AA:BB:CC:DD:EE:FF",
        )
        tree_row_reference_new.assert_called_once_with(list_view.liststore, tree_path)
        timeout_add_mock.assert_called_once()

    def test_uuid_update_stops_monitoring_for_connected_audio_devices(self) -> None:
        tree_iter = Mock()
        address = "AA:BB:CC:DD:EE:FF"
        device = {
            "Address": address,
            "Connected": True,
            "UUIDs": [f"0000{AUDIO_SINK_SVCLASS_ID:04x}-0000-1000-8000-00805F9B34FB"],
        }

        list_view = Mock()
        list_view.__dict__["_monitored_devices"] = {address}
        list_view.__dict__["_has_objpush"] = Mock(return_value=False)
        list_view.__dict__["_disable_power_levels"] = Mock()
        list_view.get.return_value = {"device": device}

        getattr(ManagerDeviceList, "row_update_event")(list_view, tree_iter, "UUIDs", device["UUIDs"])

        list_view.set.assert_called_once_with(tree_iter, objpush=False)
        getattr(list_view, "_disable_power_levels").assert_called_once_with(tree_iter)
        assert address not in getattr(list_view, "_monitored_devices")

    def test_services_resolved_stops_monitoring_for_connected_audio_devices(self) -> None:
        tree_iter = Mock()
        address = "AA:BB:CC:DD:EE:FF"
        device = {
            "Address": address,
            "Connected": True,
            "UUIDs": [f"0000{AUDIO_SINK_SVCLASS_ID:04x}-0000-1000-8000-00805F9B34FB"],
        }

        list_view = Mock()
        list_view.__dict__["_monitored_devices"] = {address}
        list_view.__dict__["_disable_power_levels"] = Mock()
        list_view.get.return_value = {"device": device}

        getattr(ManagerDeviceList, "row_update_event")(list_view, tree_iter, "ServicesResolved", True)

        getattr(list_view, "_disable_power_levels").assert_called_once_with(tree_iter)
        assert address not in getattr(list_view, "_monitored_devices")

    def test_check_power_levels_stops_when_device_resolves_to_audio(self) -> None:
        tree_iter = Mock()
        row_ref = Mock()
        row_ref.valid.return_value = True
        row_ref.get_path.return_value = Mock()
        cinfo = Mock()
        address = "AA:BB:CC:DD:EE:FF"
        device = {
            "Address": address,
            "Connected": True,
            "UUIDs": [f"0000{AUDIO_SINK_SVCLASS_ID:04x}-0000-1000-8000-00805F9B34FB"],
        }

        list_view = Mock()
        list_view.__dict__["_monitored_devices"] = {address}
        list_view.__dict__["_disable_power_levels"] = Mock()
        list_view.get_iter.return_value = tree_iter
        list_view.get.return_value = {"device": device}

        keep_monitoring = getattr(ManagerDeviceList, "_check_power_levels")(list_view, row_ref, cinfo, address)

        assert keep_monitoring is False
        cinfo.deinit.assert_called_once_with()
        getattr(list_view, "_disable_power_levels").assert_called_once_with(tree_iter)
        assert address not in getattr(list_view, "_monitored_devices")

    def test_row_update_event_logs_state_changes_at_debug(self, monkeypatch: pytest.MonkeyPatch) -> None:
        debug_mock = Mock()
        monkeypatch.setattr("blueman.gui.manager.ManagerDeviceList.logging.debug", debug_mock)

        list_view = Mock()
        device = {
            "Icon": "blueman",
            "Paired": False,
            "Connected": False,
            "Trusted": False,
            "Blocked": False,
        }
        list_view.get.return_value = {"device": device}

        getattr(ManagerDeviceList, "row_update_event")(list_view, Mock(), "ServicesResolved", True)

        debug_mock.assert_called_once_with("%s %s", "ServicesResolved", True)