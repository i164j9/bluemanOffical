from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from blueman.bluez.obex.Client import Client
from blueman.bluez.errors import BluezDBusException
from blueman.bluemantyping import ObjectPath
from blueman.main.Sendto import (
    Sender,
    build_session_failure_message,
    build_session_failure_title,
    describe_session_attempt,
)
from blueman.Sdp import OBEX_FILETRANS_SVCLASS_ID, OBEX_OBJPUSH_SVCLASS_ID


class TestClient:
    def test_create_session_omits_source_when_none(self) -> None:
        client = SimpleNamespace(_call=Mock(), emit=Mock())

        Client.create_session(client, "AA:BB:CC:DD:EE:FF", None)

        _method, param = getattr(client, "_call").call_args.args[:2]
        assert param.unpack() == (
            "AA:BB:CC:DD:EE:FF",
            {"Target": "opp"},
        )

    def test_create_session_includes_channel_when_provided(self) -> None:
        client = SimpleNamespace(_call=Mock(), emit=Mock())

        Client.create_session(client, "AA:BB:CC:DD:EE:FF", None, channel=9)

        _method, param = getattr(client, "_call").call_args.args[:2]
        assert param.unpack() == (
            "AA:BB:CC:DD:EE:FF",
            {"Target": "opp", "Channel": 9},
        )


class TestSendtoMessages:
    def test_describe_session_attempt_formats_source_and_channel(self) -> None:
        assert describe_session_attempt("11:22:33:44:55:66", 7) == "source 11:22:33:44:55:66, channel 7"

    def test_build_session_failure_message_explains_connection_refused(self) -> None:
        message = build_session_failure_message(
            BluezDBusException("org.bluez.obex.Error.Failed connect to 04:C8:B0:D5:4F:28: Connection refused (111)"),
            [("11:22:33:44:55:66", None), (None, 7)],
        )

        assert "refused the OBEX file transfer connection" in message
        assert "source 11:22:33:44:55:66" in message
        assert "without Source, channel 7" in message

    def test_build_session_failure_message_preserves_generic_reason(self) -> None:
        message = build_session_failure_message(
            BluezDBusException("org.bluez.obex.Error.Failed some other failure"),
            [],
        )

        assert message == "some other failure"

    def test_build_session_failure_message_handles_empty_obex_failure_reason(self) -> None:
        message = build_session_failure_message(
            BluezDBusException("org.bluez.obex.Error.Failed "),
            [(None, 7)],
        )

        assert "could not be established with the remote device" in message
        assert "without Source, channel 7" in message

    def test_build_session_failure_title_explains_connection_refused(self) -> None:
        title = build_session_failure_title(
            BluezDBusException("org.bluez.obex.Error.Failed connect to 04:C8:B0:D5:4F:28: Connection refused (111)")
        )

        assert title == "Remote device refused file transfer"

    def test_build_session_failure_title_preserves_generic_title(self) -> None:
        title = build_session_failure_title(BluezDBusException("org.bluez.obex.Error.Failed some other failure"))

        assert title == "Error occurred"


class TestSender:
    def test_ensure_session_fallbacks_adds_no_source_before_channel_variants(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("blueman.main.Sendto._blueman.get_rfcomm_channel", lambda _uuid, _addr: 12)
        sender = SimpleNamespace(
            _preferred_session_source_addr="11:22:33:44:55:66",
            _session_attempts=[("11:22:33:44:55:66", None, "opp")],
            device={
                "Address": "AA:BB:CC:DD:EE:FF",
                "UUIDs": [],
            },
        )

        getattr(Sender, "_ensure_session_fallbacks")(sender)

        assert getattr(sender, "_session_attempts") == [
            ("11:22:33:44:55:66", None, "opp"),
            (None, None, "opp"),
            ("11:22:33:44:55:66", 12, "opp"),
            (None, 12, "opp"),
        ]

    def test_ensure_session_fallbacks_adds_ftp_variants_when_supported(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_channel(uuid: int, _addr: str) -> int | None:
            return {OBEX_OBJPUSH_SVCLASS_ID: 7, OBEX_FILETRANS_SVCLASS_ID: 9}.get(uuid)

        monkeypatch.setattr("blueman.main.Sendto._blueman.get_rfcomm_channel", fake_channel)
        sender = SimpleNamespace(
            _preferred_session_source_addr="11:22:33:44:55:66",
            _session_attempts=[("11:22:33:44:55:66", None, "opp")],
            device={
                "Address": "AA:BB:CC:DD:EE:FF",
                "UUIDs": ["00001106-0000-1000-8000-00805f9b34fb"],
            },
        )

        getattr(Sender, "_ensure_session_fallbacks")(sender)

        assert getattr(sender, "_session_attempts") == [
            ("11:22:33:44:55:66", None, "opp"),
            (None, None, "opp"),
            ("11:22:33:44:55:66", 7, "opp"),
            (None, 7, "opp"),
            ("11:22:33:44:55:66", None, "ftp"),
            (None, None, "ftp"),
            ("11:22:33:44:55:66", 9, "ftp"),
            (None, 9, "ftp"),
        ]

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

    def test_start_send_session_creates_session_when_device_ready(self) -> None:
        start_send_session = getattr(Sender, "_start_send_session")
        sender = SimpleNamespace(
            _awaiting_device_ready=False,
            device={"Connected": True, "ServicesResolved": True},
            _device_ready_for_transfer=lambda: True,
            create_session=Mock(),
            pb=SimpleNamespace(props=SimpleNamespace(text="")),
        )

        start_send_session(sender)

        assert getattr(sender, "_awaiting_device_ready") is False
        sender.create_session.assert_called_once_with()

    def test_start_send_session_waits_for_device_resolution(self) -> None:
        start_send_session = getattr(Sender, "_start_send_session")
        device = MagicMock()
        device.__getitem__.side_effect = {"Connected": False}.__getitem__
        sender = SimpleNamespace(
            _awaiting_device_ready=False,
            device=device,
            _device_ready_for_transfer=lambda: False,
            create_session=Mock(),
            pb=SimpleNamespace(props=SimpleNamespace(text="")),
            on_device_connect_failed=Mock(),
        )

        start_send_session(sender)

        assert getattr(sender, "_awaiting_device_ready") is True
        assert sender.pb.props.text == "Preparing"
        device.connect.assert_called_once_with(error_handler=sender.on_device_connect_failed)
        sender.create_session.assert_not_called()

    def test_device_property_change_starts_session_when_ready(self) -> None:
        on_device_property_changed = getattr(Sender, "_on_device_property_changed")
        sender = SimpleNamespace(
            _awaiting_device_ready=True,
            _device_ready_for_transfer=lambda: True,
            pb=SimpleNamespace(props=SimpleNamespace(text="Preparing")),
            create_session=Mock(),
        )

        on_device_property_changed(sender, Mock(), "ServicesResolved", True, "/path")

        assert getattr(sender, "_awaiting_device_ready") is False
        assert sender.pb.props.text == "Connecting"
        sender.create_session.assert_called_once_with()

    def test_on_session_added_uses_file_transfer_for_ftp_target(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ftp_sender = Mock()
        ftp_sender.connect.side_effect = [11, 12]
        file_transfer_cls = Mock(return_value=ftp_sender)
        object_push_cls = Mock()
        monkeypatch.setattr("blueman.main.Sendto.FileTransfer", file_transfer_cls)
        monkeypatch.setattr("blueman.main.Sendto.ObjectPush", object_push_cls)

        sender = SimpleNamespace(
            _session_target="ftp",
            object_push=None,
            object_push_handlers=[],
            _clear_session_retry=Mock(),
            _clear_object_push=Mock(),
            on_transfer_started=Mock(),
            on_transfer_failed=Mock(),
            process_queue=Mock(),
        )

        Sender.on_session_added(sender, Mock(), ObjectPath("/session/path"))

        file_transfer_cls.assert_called_once_with(obj_path="/session/path")
        object_push_cls.assert_not_called()
        ftp_sender.connect.assert_any_call("transfer-started", sender.on_transfer_started)
        ftp_sender.connect.assert_any_call("transfer-failed", sender.on_transfer_failed)
        sender.process_queue.assert_called_once_with()

    def test_on_session_failed_retries_without_source_once(self) -> None:
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr("blueman.main.Sendto._blueman.get_rfcomm_channel", lambda _uuid, _addr: None)
        ensure_session_fallbacks = getattr(Sender, "_ensure_session_fallbacks")
        sender = SimpleNamespace(
            _preferred_session_source_addr="11:22:33:44:55:66",
            _session_source_addr="11:22:33:44:55:66",
            _session_channel=None,
            _session_attempts=[("11:22:33:44:55:66", None, "opp")],
            _session_attempt_index=0,
            device={"Address": "AA:BB:CC:DD:EE:FF", "UUIDs": []},
            pb=SimpleNamespace(props=SimpleNamespace(text="")),
            create_session=Mock(),
            _schedule_session_retry=Mock(),
            get_toplevel=Mock(),
            emit=Mock(),
        )
        sender.__dict__["_ensure_session_fallbacks"] = lambda: ensure_session_fallbacks(sender)

        try:
            Sender.on_session_failed(sender, Mock(), BluezDBusException("org.bluez.obex.Error.Failed first failure"))
        finally:
            monkeypatch.undo()

        assert getattr(sender, "_session_attempt_index") == 1
        getattr(sender, "_schedule_session_retry").assert_called_once_with()
        sender.create_session.assert_not_called()
        sender.emit.assert_not_called()

    def test_on_session_failed_retries_with_explicit_opp_channel_before_dropping_source(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("blueman.main.Sendto._blueman.get_rfcomm_channel", lambda _uuid, _addr: 12)
        ensure_session_fallbacks = getattr(Sender, "_ensure_session_fallbacks")
        sender = SimpleNamespace(
            _preferred_session_source_addr="11:22:33:44:55:66",
            _session_source_addr="11:22:33:44:55:66",
            _session_channel=None,
            _session_attempts=[
                ("11:22:33:44:55:66", None, "opp"),
                (None, None, "opp"),
                ("11:22:33:44:55:66", 12, "opp"),
                (None, 12, "opp"),
            ],
            _session_attempt_index=1,
            device={"Address": "AA:BB:CC:DD:EE:FF"},
            pb=SimpleNamespace(props=SimpleNamespace(text="")),
            create_session=Mock(),
            _schedule_session_retry=Mock(),
            get_toplevel=Mock(),
            emit=Mock(),
        )
        sender.__dict__["_ensure_session_fallbacks"] = lambda: ensure_session_fallbacks(sender)

        Sender.on_session_failed(sender, Mock(), BluezDBusException("org.bluez.obex.Error.Failed first failure"))

        assert getattr(sender, "_session_attempt_index") == 2
        getattr(sender, "_schedule_session_retry").assert_called_once_with()
        sender.create_session.assert_not_called()
        sender.emit.assert_not_called()

    def test_on_session_failed_retries_with_explicit_opp_channel(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("blueman.main.Sendto._blueman.get_rfcomm_channel", lambda _uuid, _addr: 12)
        ensure_session_fallbacks = getattr(Sender, "_ensure_session_fallbacks")
        sender = SimpleNamespace(
            _preferred_session_source_addr="11:22:33:44:55:66",
            _session_source_addr=None,
            _session_channel=None,
            _session_attempts=[
                ("11:22:33:44:55:66", None, "opp"),
                (None, None, "opp"),
                ("11:22:33:44:55:66", 12, "opp"),
                (None, 12, "opp"),
            ],
            _session_attempt_index=2,
            device={"Address": "AA:BB:CC:DD:EE:FF"},
            pb=SimpleNamespace(props=SimpleNamespace(text="")),
            create_session=Mock(),
            _schedule_session_retry=Mock(),
            get_toplevel=Mock(),
            emit=Mock(),
        )
        sender.__dict__["_ensure_session_fallbacks"] = lambda: ensure_session_fallbacks(sender)

        Sender.on_session_failed(sender, Mock(), BluezDBusException("org.bluez.obex.Error.Failed second failure"))

        assert getattr(sender, "_session_attempt_index") == 3
        getattr(sender, "_schedule_session_retry").assert_called_once_with()
        sender.create_session.assert_not_called()
        sender.emit.assert_not_called()