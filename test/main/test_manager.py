from types import SimpleNamespace
from unittest.mock import Mock, patch

from gi.repository import GLib

from blueman.main.Manager import Blueman, POWER_MANAGER_STATUS_RETRY_LIMIT


class TestManager:
    def test_get_power_manager_status_ignores_missing_interface(self) -> None:
        get_power_manager_status = getattr(Blueman, "_get_power_manager_status")
        manager = SimpleNamespace(
            PowerManager=Mock(
                get_bluetooth_status=Mock(
                    side_effect=GLib.Error(
                        "GDBus.Error:org.freedesktop.DBus.Error.UnknownMethod: "
                        "No such interface \"org.blueman.Applet.PowerManager\" on object at path /org/blueman/Applet"
                    )
                )
            )
        )

        status = get_power_manager_status(manager)

        assert status is False

    def test_get_initial_bluetooth_action_state_retries_missing_interface(self) -> None:
        try_get_power_manager_status = getattr(Blueman, "_try_get_power_manager_status")
        get_initial_bluetooth_action_state = getattr(Blueman, "_get_initial_bluetooth_action_state")
        schedule_retry = Mock()
        manager = SimpleNamespace(
            Applet=Mock(QueryPlugins=Mock(return_value=["PowerManager"])),
            PowerManager=Mock(
                get_bluetooth_status=Mock(
                    side_effect=GLib.Error(
                        "GDBus.Error:org.freedesktop.DBus.Error.UnknownMethod: "
                        "No such interface \"org.blueman.Applet.PowerManager\" on object at path /org/blueman/Applet"
                    )
                )
            ),
            _schedule_power_manager_status_retry=schedule_retry,
        )
        manager.__dict__["_try_get_power_manager_status"] = (
            lambda log_missing=True: try_get_power_manager_status(manager, log_missing=log_missing)
        )

        status = get_initial_bluetooth_action_state(manager)

        assert status is False
        schedule_retry.assert_called_once_with()

    def test_get_initial_bluetooth_action_state_uses_ready_interface(self) -> None:
        try_get_power_manager_status = getattr(Blueman, "_try_get_power_manager_status")
        get_initial_bluetooth_action_state = getattr(Blueman, "_get_initial_bluetooth_action_state")
        schedule_retry = Mock()
        manager = SimpleNamespace(
            Applet=Mock(QueryPlugins=Mock(return_value=["PowerManager"])),
            PowerManager=Mock(get_bluetooth_status=Mock(return_value=True)),
            _schedule_power_manager_status_retry=schedule_retry,
        )
        manager.__dict__["_try_get_power_manager_status"] = (
            lambda log_missing=True: try_get_power_manager_status(manager, log_missing=log_missing)
        )

        status = get_initial_bluetooth_action_state(manager)

        assert status is True
        schedule_retry.assert_not_called()

    @patch("blueman.main.Manager.GLib.timeout_add")
    def test_schedule_power_manager_status_retry_stops_at_limit(self, timeout_add_mock: Mock) -> None:
        schedule_retry = getattr(Blueman, "_schedule_power_manager_status_retry")
        manager = SimpleNamespace(
            _power_manager_retry_source_id=None,
            _power_manager_retry_attempts=POWER_MANAGER_STATUS_RETRY_LIMIT,
        )

        schedule_retry(manager)

        timeout_add_mock.assert_not_called()
        assert getattr(manager, "_power_manager_retry_attempts") == POWER_MANAGER_STATUS_RETRY_LIMIT

    def test_plugins_changed_uses_power_manager_fallback(self) -> None:
        get_initial_bluetooth_action_state = getattr(Blueman, "_get_initial_bluetooth_action_state")
        action = Mock()
        schedule_retry = Mock()
        update_buttons = Mock()
        manager = SimpleNamespace(
            lookup_action=Mock(return_value=action),
            Applet=Mock(QueryPlugins=Mock(return_value=["PowerManager"])),
            PowerManager=Mock(
                get_bluetooth_status=Mock(
                    side_effect=GLib.Error(
                        "GDBus.Error:org.freedesktop.DBus.Error.UnknownMethod: "
                        "No such interface \"org.blueman.Applet.PowerManager\" on object at path /org/blueman/Applet"
                    )
                )
            ),
            Toolbar=SimpleNamespace(),
            List=SimpleNamespace(Adapter=Mock()),
            _schedule_power_manager_status_retry=schedule_retry,
        )
        manager.__dict__["_get_initial_bluetooth_action_state"] = lambda: get_initial_bluetooth_action_state(manager)
        manager.Toolbar.__dict__["_update_buttons"] = update_buttons

        Blueman.on_applet_signal(manager, Mock(), "sender", "PluginsChanged", GLib.Variant("()", ()))

        action.set_state.assert_called_once()
        schedule_retry.assert_called_once_with()
        update_buttons.assert_called_once_with(manager.List.Adapter)

    def test_bluetooth_status_signal_only_updates_action_state(self) -> None:
        action = Mock()
        manager = SimpleNamespace(lookup_action=Mock(return_value=action))

        Blueman.on_applet_signal(
            manager,
            Mock(),
            "sender",
            "BluetoothStatusChanged",
            GLib.Variant("(b)", (True,)),
        )

        action.set_state.assert_called_once()
        action.change_state.assert_not_called()

    @patch("blueman.main.Manager.launch")
    def test_send_launches_immediately_when_device_ready(self, launch_mock: Mock) -> None:
        launch_sendto = getattr(Blueman, "_launch_sendto")
        manager = SimpleNamespace(List=SimpleNamespace(Adapter={"Address": "11:22:33:44:55:66"}))
        manager.__dict__["_launch_sendto"] = lambda adapter, device: launch_sendto(manager, adapter, device)
        device = {"Connected": True, "ServicesResolved": True, "Address": "AA:BB:CC:DD:EE:FF"}

        Blueman.send(manager, device)

        launch_mock.assert_called_once_with(
            "blueman-sendto --source=11:22:33:44:55:66 --device=AA:BB:CC:DD:EE:FF",
            name="File Sender",
        )

    @patch("blueman.main.Manager.launch")
    def test_send_does_not_wait_for_services_resolved(self, launch_mock: Mock) -> None:
        launch_sendto = getattr(Blueman, "_launch_sendto")
        manager = SimpleNamespace(List=SimpleNamespace(Adapter={"Address": "11:22:33:44:55:66"}))
        manager.__dict__["_launch_sendto"] = lambda adapter, device: launch_sendto(manager, adapter, device)
        device = {"Connected": True, "ServicesResolved": False, "Address": "AA:BB:CC:DD:EE:FF"}

        Blueman.send(manager, device)

        launch_mock.assert_called_once_with(
            "blueman-sendto --source=11:22:33:44:55:66 --device=AA:BB:CC:DD:EE:FF",
            name="File Sender",
        )

    @patch("blueman.main.Manager.logging.getLogger")
    @patch("blueman.main.Manager.launch")
    def test_send_propagates_debug_loglevel_to_sendto(self, launch_mock: Mock, get_logger_mock: Mock) -> None:
        launch_sendto = getattr(Blueman, "_launch_sendto")
        manager = SimpleNamespace(List=SimpleNamespace(Adapter={"Address": "11:22:33:44:55:66"}))
        manager.__dict__["_launch_sendto"] = lambda adapter, device: launch_sendto(manager, adapter, device)
        get_logger_mock.return_value.isEnabledFor.return_value = True
        device = {"Connected": True, "ServicesResolved": True, "Address": "AA:BB:CC:DD:EE:FF"}

        Blueman.send(manager, device)

        launch_mock.assert_called_once_with(
            "blueman-sendto --loglevel DEBUG --source=11:22:33:44:55:66 --device=AA:BB:CC:DD:EE:FF",
            name="File Sender",
        )