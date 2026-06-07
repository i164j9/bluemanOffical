import logging
from blueman.bluemantyping import ObjectPath

from blueman.bluez.obex.Base import Base
from blueman.bluez.errors import BluezDBusException
from gi.repository import GObject, Gio, GLib

from blueman.bluemantyping import GSignals


class Transfer(Base):
    __gsignals__: GSignals = {
        'progress': (GObject.SignalFlags.NO_HOOKS, None, (int,)),
        'completed': (GObject.SignalFlags.NO_HOOKS, None, ()),
        'error': (GObject.SignalFlags.NO_HOOKS, None, ())
    }

    _interface_name = 'org.bluez.obex.Transfer1'

    def __init__(self, obj_path: ObjectPath):
        super().__init__(obj_path=obj_path)

    def _get_optional(self, name: str) -> str | int | ObjectPath | None:
        try:
            return self.get(name)
        except BluezDBusException:
            return None

    @property
    def filename(self) -> str | None:
        name = self._get_optional("Filename")
        return name if isinstance(name, str) else None

    @property
    def name(self) -> str:
        name = self._get_optional("Name")
        if isinstance(name, str) and name:
            return name

        filename = self.filename
        if filename:
            return filename

        return str(self.get_object_path()).rsplit('/', 1)[-1]

    @property
    def session(self) -> ObjectPath:
        session: ObjectPath = self.get("Session")
        return session

    @property
    def size(self) -> int | None:
        size = self._get_optional("Size")
        return size if isinstance(size, int) else None

    def _properties_changed(self, _proxy: Gio.DBusProxy, changed_properties: GLib.Variant,
                            _invalidated_properties: list[str]) -> None:
        logging.debug("%s", changed_properties)
        for name, value in changed_properties.unpack().items():
            logging.debug("%s %s %s", self.get_object_path(), name, value)
            if name == 'Transferred' and isinstance(value, int):
                self.emit('progress', value)
            elif name == 'Status' and isinstance(value, str):
                if value == 'complete':
                    self.emit('completed')
                elif value == 'error':
                    self.emit('error')
