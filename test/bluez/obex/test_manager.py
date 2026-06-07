from unittest import TestCase
from types import SimpleNamespace
from unittest.mock import Mock

from blueman.bluez.obex.Manager import Manager
from blueman.gobject import SingletonGObjectMeta


class TestManager(TestCase):
    def test_metaclass(self):
        self.assertIsInstance(Manager, SingletonGObjectMeta)

    def test_object_removed_emits_failed_completion_for_tracked_transfer(self):
        transfer = SimpleNamespace(disconnect_signal=Mock())
        manager = SimpleNamespace(
            _Manager__transfers={"/transfer/path": (transfer, (1, 2))},
            emit=Mock(),
        )
        dbus_object = SimpleNamespace(
            get_interface=lambda name: object() if name == 'org.bluez.obex.Transfer1' else None,
            get_object_path=lambda: "/transfer/path",
        )

        getattr(Manager, '_on_object_removed')(manager, Mock(), dbus_object)

        transfer.disconnect_signal.assert_any_call(1)
        transfer.disconnect_signal.assert_any_call(2)
        manager.emit.assert_called_once_with('transfer-completed', '/transfer/path', False)

    def test_transfer_completed_ignores_duplicate_completion_after_removal(self):
        transfer = SimpleNamespace(
            get_object_path=lambda: "/transfer/path",
            disconnect_signal=Mock(),
        )
        manager = SimpleNamespace(
            _Manager__transfers={},
            emit=Mock(),
        )

        getattr(Manager, '_on_transfer_completed')(manager, transfer, True)

        manager.emit.assert_not_called()
