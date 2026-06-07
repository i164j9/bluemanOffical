from unittest.mock import Mock

from blueman.plugins.applet.NetUsage import Dialog


class TestNetUsageDialog:
    def teardown_method(self) -> None:
        Dialog.active_dialog = None

    def test_present_existing_returns_false_without_dialog(self) -> None:
        assert Dialog.present_existing() is False

    def test_present_existing_presents_active_dialog(self) -> None:
        dialog = object.__new__(Dialog)
        dialog.present = Mock()
        Dialog.active_dialog = dialog

        assert Dialog.present_existing() is True
        dialog.present.assert_called_once_with()