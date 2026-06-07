from unittest.mock import Mock

from blueman.gui.manager.ManagerDeviceList import (
    build_power_tooltip_lines,
    get_power_level_values,
    get_unavailable_power_columns,
)


class TestManagerDeviceList:
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