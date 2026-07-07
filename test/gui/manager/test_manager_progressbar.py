from types import SimpleNamespace
from unittest.mock import Mock

from blueman.gui.manager.ManagerProgressbar import ManagerProgressbar


class TestManagerProgressbar:
    def test_finalize_clears_signal_bookkeeping_without_manual_disconnect(self) -> None:
        window = SimpleNamespace(set_cursor=Mock())
        progress = SimpleNamespace(
            finalized=False,
            hide=Mock(),
            stop=Mock(),
            _get_window=Mock(return_value=window),
            hbox=Mock(),
            eventbox=Mock(),
            progressbar=Mock(),
            Blueman=SimpleNamespace(
                Config={"show-statusbar": True},
                builder=Mock(),
                Stats=SimpleNamespace(hbox=Mock()),
            ),
            _signals=[1206],
            disconnect=Mock(),
            handler_is_connected=Mock(return_value=True),
        )
        original_instances = ManagerProgressbar.__instances__
        ManagerProgressbar.__instances__ = [progress]

        try:
            finalized = ManagerProgressbar.finalize(progress)
        finally:
            ManagerProgressbar.__instances__ = original_instances

        assert finalized is False
        assert getattr(progress, "finalized") is True
        progress.hide.assert_called_once_with()
        progress.stop.assert_called_once_with()
        window.set_cursor.assert_called_once_with(None)
        progress.hbox.remove.assert_any_call(progress.eventbox)
        progress.hbox.remove.assert_any_call(progress.progressbar)
        progress.disconnect.assert_not_called()
        assert getattr(progress, "_signals") == []