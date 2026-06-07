from types import SimpleNamespace
from unittest.mock import Mock

from blueman.main.Sendto import Sender


class TestSender:
    def test_on_session_removed_ignores_unrelated_session(self) -> None:
        object_push = SimpleNamespace(
            get_session_path=lambda: "/current/session",
            disconnect=Mock(),
        )
        sender = SimpleNamespace(
            object_push=object_push,
            object_push_handlers=[11, 12],
            transfer=object(),
            transferred=10,
            total_transferred=40,
            _last_bytes=10,
            speed=Mock(),
            cancelling=False,
            error_dialog=None,
            files=[Mock()],
            create_session=Mock(),
            pb=SimpleNamespace(props=SimpleNamespace(text="")),
        )
        clear_object_push = getattr(Sender, "_clear_object_push")
        reset_transfer_state = getattr(Sender, "_reset_transfer_state")
        sender.__dict__["_clear_object_push"] = lambda session_path=None: clear_object_push(sender, session_path)
        sender.__dict__["_reset_transfer_state"] = lambda: reset_transfer_state(sender)

        Sender.on_session_removed(sender, Mock(), "/other/session")

        object_push.disconnect.assert_not_called()
        sender.create_session.assert_not_called()
        assert sender.object_push is object_push
        assert sender.object_push_handlers == [11, 12]

    def test_on_session_removed_recreates_active_session(self) -> None:
        object_push = SimpleNamespace(
            get_session_path=lambda: "/current/session",
            disconnect=Mock(),
        )
        sender = SimpleNamespace(
            object_push=object_push,
            object_push_handlers=[11, 12],
            transfer=object(),
            transferred=10,
            total_transferred=40,
            _last_bytes=10,
            speed=Mock(reset=Mock()),
            cancelling=False,
            error_dialog=None,
            files=[Mock()],
            create_session=Mock(),
            pb=SimpleNamespace(props=SimpleNamespace(text="")),
        )
        clear_object_push = getattr(Sender, "_clear_object_push")
        reset_transfer_state = getattr(Sender, "_reset_transfer_state")
        sender.__dict__["_clear_object_push"] = lambda session_path=None: clear_object_push(sender, session_path)
        sender.__dict__["_reset_transfer_state"] = lambda: reset_transfer_state(sender)

        Sender.on_session_removed(sender, Mock(), "/current/session")

        object_push.disconnect.assert_any_call(11)
        object_push.disconnect.assert_any_call(12)
        sender.speed.reset.assert_called_once_with()
        sender.create_session.assert_called_once_with()
        assert sender.object_push is None
        assert sender.object_push_handlers == []
        assert sender.transfer is None
        assert sender.transferred == 0
        assert sender.total_transferred == 30
        assert getattr(sender, "_last_bytes") == 0
        assert sender.pb.props.text == "Connecting"