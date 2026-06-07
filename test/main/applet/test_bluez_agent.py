from types import SimpleNamespace
from unittest.mock import Mock
from unittest.mock import patch

from blueman.main.applet.BluezAgent import BluezAgent, BluezErrorCanceled


class TestBluezAgent:
    def test_ask_passkey_returns_when_dialog_already_active(self) -> None:
        err = Mock()
        fake_agent = SimpleNamespace(
            dialog=object(),
            get_device_string=lambda _path: "device",
            build_passkey_dialog=Mock(),
        )

        BluezAgent.ask_passkey(fake_agent, "msg", False, "/path", Mock(), err)

        fake_agent.build_passkey_dialog.assert_not_called()
        error = err.call_args.args[0]
        assert isinstance(error, BluezErrorCanceled)

    def test_ask_passkey_returns_when_dialog_build_fails(self) -> None:
        err = Mock()
        fake_agent = SimpleNamespace(
            dialog=None,
            get_device_string=lambda _path: "device",
            build_passkey_dialog=Mock(return_value=(None, Mock())),
        )

        BluezAgent.ask_passkey(fake_agent, "msg", False, "/path", Mock(), err)

        fake_agent.build_passkey_dialog.assert_called_once()
        error = err.call_args.args[0]
        assert isinstance(error, BluezErrorCanceled)

    def test_close_closes_service_notifications(self) -> None:
        notification = Mock()
        service_notification = Mock()
        fake_agent = SimpleNamespace(
            _notification=notification,
            _service_notifications=[service_notification],
        )

        getattr(BluezAgent, "_close")(fake_agent)

        notification.close.assert_called_once_with()
        service_notification.close.assert_called_once_with()
        assert getattr(fake_agent, "_notification") is None
        assert getattr(fake_agent, "_service_notifications") == []

    @patch("blueman.main.applet.BluezAgent.Notification")
    def test_authorize_service_action_tolerates_precleared_notifications(self, notification_cls: Mock) -> None:
        ok = Mock()
        err = Mock()
        notification = Mock()
        notification_cls.return_value = notification
        fake_agent = SimpleNamespace(
            _service_notifications=[],
            get_device_string=lambda _path: "device",
        )

        getattr(BluezAgent, "_on_authorize_service")(
            fake_agent,
            "/path",
            "00001105-0000-1000-8000-00805f9b34fb",
            ok,
            err,
        )

        getattr(fake_agent, "_service_notifications").clear()
        actions_cb = notification_cls.call_args.kwargs["actions_cb"]
        actions_cb("accept")

        ok.assert_called_once_with()
        err.assert_not_called()