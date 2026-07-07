import weakref

from gi.repository import GObject, GLib
from gi.repository import Gio

from blueman.bluemantyping import GSignals


class AnyBase(GObject.GObject):
    __gsignals__: GSignals = {
        'property-changed': (GObject.SignalFlags.NO_HOOKS, None, (str, object, str))
    }

    connect_signal = GObject.GObject.connect
    disconnect_signal = GObject.GObject.disconnect

    def __init__(self, interface_name: str):
        super().__init__()

        bus = Gio.bus_get_sync(Gio.BusType.SYSTEM)

        this = weakref.proxy(self)

        def on_signal(
            _connection: Gio.DBusConnection,
            _sender_name: str,
            object_path: str,
            _interface_name: str,
            _signal_name: str,
            param: GLib.Variant,
        ) -> None:
            iface_name, changed, invalidated = param.unpack()
            if iface_name == interface_name and this is not None:
                for key in list(changed) + invalidated:
                    this.emit('property-changed', key, changed.get(key, None), object_path)

        subscription_id = bus.signal_subscribe(
            "org.bluez",
            "org.freedesktop.DBus.Properties",
            "PropertiesChanged",
            None,
            None,
            Gio.DBusSignalFlags(0),
            on_signal
        )

        self._finalizer = weakref.finalize(self, bus.signal_unsubscribe, subscription_id)

    def destroy(self) -> None:
        if self._finalizer.alive:
            self._finalizer()
