from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from blueman.bluez.errors import BluezDBusException
from blueman.plugins.applet.TransferService import Agent, ObexErrorRejected, TransferService


class TestTransferService:
    def test_on_unload_disconnects_manager_handlers_and_resets_state(self) -> None:
        manager = Mock()
        notification = Mock()
        agent = Mock()
        service = SimpleNamespace(
            _watch=17,
            _manager=manager,
            _handlerids=[11, 12],
            _notification=notification,
            _agent=agent,
            _silent_transfers=2,
            _normal_transfers=1,
        )
        service.__dict__["_disconnect_manager"] = lambda: getattr(TransferService, "_disconnect_manager")(service)
        service.__dict__["_close_notification"] = lambda: getattr(TransferService, "_close_notification")(service)
        service.__dict__["_unregister_agent"] = Mock(side_effect=lambda: setattr(service, "_agent", None))
        service.__dict__["_reset_transfer_counters"] = lambda: getattr(TransferService, "_reset_transfer_counters")(service)

        with patch("blueman.plugins.applet.TransferService.Gio.bus_unwatch_name") as unwatch_name:
            TransferService.on_unload(service)

        unwatch_name.assert_called_once_with(17)
        manager.disconnect.assert_any_call(11)
        manager.disconnect.assert_any_call(12)
        notification.close.assert_called_once_with()
        getattr(service, "_unregister_agent").assert_called_once_with()
        assert getattr(service, "_watch") is None
        assert getattr(service, "_manager") is None
        assert getattr(service, "_handlerids") == []
        assert getattr(service, "_notification") is None
        assert getattr(service, "_agent") is None
        assert getattr(service, "_silent_transfers") == 0
        assert getattr(service, "_normal_transfers") == 0

    def test_name_vanished_disconnects_manager_and_resets_counters(self) -> None:
        manager = Mock()
        service = SimpleNamespace(
            _manager=manager,
            _handlerids=[11],
            _agent=None,
            _notification=None,
            _silent_transfers=2,
            _normal_transfers=1,
        )
        service.__dict__["_disconnect_manager"] = lambda: getattr(TransferService, "_disconnect_manager")(service)
        service.__dict__["_close_notification"] = lambda: getattr(TransferService, "_close_notification")(service)
        service.__dict__["_reset_transfer_counters"] = lambda: getattr(TransferService, "_reset_transfer_counters")(service)

        getattr(TransferService, "_on_dbus_name_vanished")(service, Mock(), "org.bluez.obex")

        manager.disconnect.assert_called_once_with(11)
        assert getattr(service, "_manager") is None
        assert getattr(service, "_handlerids") == []
        assert getattr(service, "_silent_transfers") == 0
        assert getattr(service, "_normal_transfers") == 0

    def test_on_transfer_started_treats_unknown_size_as_normal(self) -> None:
        service = SimpleNamespace(
            _agent=SimpleNamespace(transfers={"/transfer": {"size": None}}),
            _normal_transfers=0,
            _silent_transfers=0,
        )

        getattr(TransferService, "_on_transfer_started")(service, Mock(), "/transfer")

        assert getattr(service, "_normal_transfers") == 1
        assert getattr(service, "_silent_transfers") == 0

    @patch("blueman.plugins.applet.TransferService.Notification")
    def test_session_removed_resets_transfer_counters(self, notification_cls: Mock) -> None:
        notification = Mock()
        notification_cls.return_value = notification
        service = SimpleNamespace(
            _silent_transfers=2,
            _normal_transfers=1,
            _notification=None,
            _make_share_path=lambda: (Path("/tmp"), False),
            _close_notification=Mock(),
            _add_open=Mock(),
        )
        reset_transfer_counters = getattr(TransferService, "_reset_transfer_counters")
        service.__dict__["_reset_transfer_counters"] = lambda: reset_transfer_counters(service)

        getattr(TransferService, "_on_session_removed")(service, Mock(), "/session")

        notification.show.assert_called_once_with()
        assert getattr(service, "_silent_transfers") == 0
        assert getattr(service, "_normal_transfers") == 0


class TestTransferAgent:
    @patch("blueman.plugins.applet.TransferService.Transfer")
    def test_authorize_push_rejects_when_transfer_metadata_unavailable(self, transfer_cls: Mock) -> None:
        class BrokenTransfer:
            @property
            def session(self) -> str:
                raise BluezDBusException("missing session")

        transfer_cls.return_value = BrokenTransfer()
        err = Mock()
        agent = SimpleNamespace(
            _close_notification=Mock(),
            transfers={},
            _allowed_devices=[],
            _allowed_device_timeouts=set(),
            _config={"opp-accept": True},
            _applet=SimpleNamespace(Manager=Mock()),
            _pending_transfer=None,
            _notification=None,
        )

        getattr(Agent, "_authorize_push")(agent, "/transfer", Mock(), err)

        error = err.call_args.args[0]
        assert isinstance(error, ObexErrorRejected)
        assert getattr(agent, "_pending_transfer") is None