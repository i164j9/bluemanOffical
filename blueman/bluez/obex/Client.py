import logging

from blueman.bluez.errors import BluezDBusException
from blueman.bluez.obex.Base import Base
from gi.repository import GObject, GLib

from blueman.bluemantyping import GSignals, ObjectPath, BtAddress


class Client(Base):
    __gsignals__: GSignals = {
        'session-failed': (GObject.SignalFlags.NO_HOOKS, None, (object,)),
    }

    _interface_name = 'org.bluez.obex.Client1'
    _obj_path: ObjectPath = ObjectPath('/org/bluez/obex')

    def __init__(self) -> None:
        super().__init__(obj_path=self._obj_path)

    def create_session(
        self,
        dest_addr: BtAddress,
        source_addr: BtAddress | None = BtAddress("00:00:00:00:00:00"),
        pattern: str = "opp",
        channel: int | None = None,
    ) -> None:
        def on_session_created(session_path: ObjectPath) -> None:
            logging.info("%s %s %s %s %s", dest_addr, source_addr, pattern, channel, session_path)

        def on_session_failed(error: BluezDBusException) -> None:
            logging.error("%s %s %s %s %s", dest_addr, source_addr, pattern, channel, error)
            self.emit("session-failed", error)

        v_pattern = GLib.Variant('s', pattern)
        options: dict[str, GLib.Variant] = {"Target": v_pattern}
        if source_addr is not None:
            options["Source"] = GLib.Variant('s', source_addr)
        if channel is not None:
            options["Channel"] = GLib.Variant('y', channel)

        param = GLib.Variant('(sa{sv})', (dest_addr, options))
        self._call('CreateSession', param, reply_handler=on_session_created, error_handler=on_session_failed)

    def remove_session(self, session_path: ObjectPath) -> None:
        def on_session_removed() -> None:
            logging.info(session_path)

        def on_session_remove_failed(error: BluezDBusException) -> None:
            logging.error("%s %s", session_path, error)

        param = GLib.Variant('(o)', (session_path,))
        self._call('RemoveSession', param, reply_handler=on_session_removed,
                   error_handler=on_session_remove_failed)
