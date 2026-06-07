from types import SimpleNamespace
from unittest.mock import Mock

from blueman.bluez.obex.ObjectPush import ObjectPush


class TestObjectPush:
    def test_send_file_falls_back_to_local_basename(self) -> None:
        emit = Mock()
        reply_handlers: list[object] = []

        fake_push = SimpleNamespace(
            get_object_path=lambda: "/session/path",
            emit=emit,
            _call=lambda _method, _param, reply_handler, error_handler: reply_handlers.append(reply_handler),
        )

        ObjectPush.send_file(fake_push, "/tmp/example.txt")

        assert len(reply_handlers) == 1
        reply = reply_handlers[0]
        assert callable(reply)
        reply("/transfer/path", {})

        emit.assert_called_once_with("transfer-started", "/transfer/path", "example.txt")