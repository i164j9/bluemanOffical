from types import SimpleNamespace
from unittest.mock import Mock, patch

from blueman.plugins.applet.SerialManager import ScriptProcess, SerialManager


class TestSerialManager:
    @patch("blueman.plugins.applet.SerialManager.Popen")
    def test_call_script_uses_start_new_session(self, popen: Mock) -> None:
        process = SimpleNamespace(pid=20)
        popen.return_value = process
        manager = SimpleNamespace(
            get_option=lambda _key: 'script --flag "two words"',
            manage_script=Mock(),
        )

        SerialManager.call_script(manager, "AA:BB:CC:DD:EE:FF", "Phone", "Serial", 0x1101, "/dev/rfcomm0")

        popen.assert_called_once_with(
            [
                "script",
                "--flag",
                "two words",
                "AA:BB:CC:DD:EE:FF",
                "Phone",
                "Serial",
                "0x1101",
                "/dev/rfcomm0",
            ],
            start_new_session=True,
        )
        manager.manage_script.assert_called_once_with("AA:BB:CC:DD:EE:FF", "/dev/rfcomm0", process)

    def test_manage_script_replaces_existing_watch_safely(self) -> None:
        old_process = SimpleNamespace(pid=10)
        new_process = SimpleNamespace(pid=20)
        manager = SimpleNamespace(
            scripts={"AA:BB:CC:DD:EE:FF": {"/dev/rfcomm0": ScriptProcess(old_process, 11)}},
        )
        manager.__dict__["_stop_script"] = lambda address, node: getattr(SerialManager, "_stop_script")(manager, address, node)
        manager.__dict__["on_script_closed"] = lambda pid, cond, address_node: getattr(SerialManager, "on_script_closed")(
            manager, pid, cond, address_node
        )
        manager.__dict__["_remove_script"] = lambda address, node, pid: getattr(SerialManager, "_remove_script")(
            manager, address, node, pid
        )

        with patch("blueman.plugins.applet.SerialManager.GLib.child_watch_add", return_value=22), \
                patch("blueman.plugins.applet.SerialManager.GLib.source_remove") as source_remove, \
                patch("blueman.plugins.applet.SerialManager.os.killpg") as killpg:
            SerialManager.manage_script(manager, "AA:BB:CC:DD:EE:FF", "/dev/rfcomm0", new_process)

        source_remove.assert_called_once_with(11)
        killpg.assert_called_once_with(10, __import__("signal").SIGHUP)
        entry = manager.scripts["AA:BB:CC:DD:EE:FF"]["/dev/rfcomm0"]
        assert entry.process is new_process
        assert entry.watch_id == 22

    def test_stale_child_watch_does_not_remove_replacement_process(self) -> None:
        new_process = SimpleNamespace(pid=20)
        manager = SimpleNamespace(
            scripts={"AA:BB:CC:DD:EE:FF": {"/dev/rfcomm0": ScriptProcess(new_process, 22)}},
        )
        manager.__dict__["_remove_script"] = lambda address, node, pid: getattr(SerialManager, "_remove_script")(
            manager, address, node, pid
        )

        getattr(SerialManager, "on_script_closed")(manager, 10, 0, ("AA:BB:CC:DD:EE:FF", "/dev/rfcomm0"))

        entry = manager.scripts["AA:BB:CC:DD:EE:FF"]["/dev/rfcomm0"]
        assert entry.process is new_process
        assert entry.watch_id == 22

    def test_on_unload_stops_scripts_and_clears_registry(self) -> None:
        manager = SimpleNamespace(scripts={"AA:BB:CC:DD:EE:FF": {"/dev/rfcomm0": Mock()}})
        manager.__dict__["terminate_all_scripts"] = Mock(side_effect=lambda address: manager.scripts.pop(address, None))

        SerialManager.on_unload(manager)

        getattr(manager, "terminate_all_scripts").assert_called_once_with("AA:BB:CC:DD:EE:FF")
        assert manager.scripts == {}