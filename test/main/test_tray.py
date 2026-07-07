from types import SimpleNamespace
from unittest.mock import Mock

from blueman.main.Tray import BluemanTray


class TestTray:
    def test_name_vanished_destroys_indicator_before_quit(self) -> None:
        destroy_indicator = getattr(BluemanTray, "_destroy_indicator")
        indicator = Mock()
        tray = SimpleNamespace(indicator=indicator, quit=Mock(), _active=True)
        tray.__dict__["_destroy_indicator"] = lambda: destroy_indicator(tray)

        getattr(BluemanTray, "_on_name_vanished")(tray, Mock(), "org.blueman.Applet")

        indicator.destroy.assert_called_once_with()
        tray.quit.assert_called_once_with()
        assert getattr(tray, "_active") is False
        assert getattr(tray, "indicator") is None