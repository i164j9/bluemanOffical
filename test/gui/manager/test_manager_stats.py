from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from blueman.gui.manager.ManagerStats import ManagerStats, has_connected_audio_device
from blueman.Sdp import AUDIO_SINK_SVCLASS_ID, OBEX_OBJPUSH_SVCLASS_ID


class TestManagerStats:
    def test_has_connected_audio_device_detects_connected_audio_rows(self) -> None:
        tree_iter = Mock()
        list_view = Mock()
        list_view.__dict__["liststore"] = [SimpleNamespace(iter=tree_iter)]
        list_view.get.return_value = {
            "device": {
                "Connected": True,
                "UUIDs": [f"0000{AUDIO_SINK_SVCLASS_ID:04x}-0000-1000-8000-00805F9B34FB"],
            }
        }

        assert has_connected_audio_device(list_view) is True

    def test_has_connected_audio_device_ignores_non_audio_rows(self) -> None:
        tree_iter = Mock()
        list_view = Mock()
        list_view.__dict__["liststore"] = [SimpleNamespace(iter=tree_iter)]
        list_view.get.return_value = {
            "device": {
                "Connected": True,
                "UUIDs": [f"0000{OBEX_OBJPUSH_SVCLASS_ID:04x}-0000-1000-8000-00805F9B34FB"],
            }
        }

        assert has_connected_audio_device(list_view) is False

    def test_update_skips_device_info_poll_for_connected_audio(self, monkeypatch: pytest.MonkeyPatch) -> None:
        device_info_mock = Mock()
        monkeypatch.setattr("blueman.gui.manager.ManagerStats.device_info", device_info_mock)

        stats = SimpleNamespace(
            hci="hci0",
            List=Mock(),
            up_speed=Mock(),
            down_speed=Mock(),
            set_blinker_by_speed=Mock(),
            up_blinker=Mock(),
            down_blinker=Mock(),
            set_data=Mock(),
        )
        monkeypatch.setattr("blueman.gui.manager.ManagerStats.has_connected_audio_device", Mock(return_value=True))

        keep_running = ManagerStats._update(stats)

        assert keep_running is True
        device_info_mock.assert_not_called()
        stats.set_data.assert_not_called()
