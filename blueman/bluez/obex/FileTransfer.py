from os.path import basename
import logging

from gi.repository import GObject, GLib

from blueman.bluez.errors import BluezDBusException
from blueman.bluez.obex.Base import Base
from blueman.bluemantyping import GSignals, ObjectPath


class FileTransfer(Base):
    __gsignals__: GSignals = {
        'transfer-started': (GObject.SignalFlags.NO_HOOKS, None, (str, str,)),
        'transfer-failed': (GObject.SignalFlags.NO_HOOKS, None, (str,)),
    }

    _interface_name = 'org.bluez.obex.FileTransfer1'

    def __init__(self, obj_path: ObjectPath):
        super().__init__(obj_path=obj_path)

    def send_file(self, file_path: str) -> None:
        target_name = basename(file_path)

        def on_transfer_started(transfer_path: ObjectPath, props: dict[str, str]) -> None:
            logging.info("%s %s %s", self.get_object_path(), file_path, transfer_path)
            self.emit('transfer-started', transfer_path, props.get('Name', target_name))

        def on_transfer_error(error: BluezDBusException) -> None:
            logging.error("%s %s", file_path, error)
            self.emit('transfer-failed', error)

        param = GLib.Variant('(ss)', (file_path, target_name))
        self._call('PutFile', param, reply_handler=on_transfer_started, error_handler=on_transfer_error)

    def get_session_path(self) -> ObjectPath:
        path: ObjectPath = self.get_object_path()
        return path