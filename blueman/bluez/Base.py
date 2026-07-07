from typing import Any, TypeVar, cast
from collections.abc import Callable
from blueman.bluemantyping import GSignals, ObjectPath

from gi.repository import Gio, GLib, GObject
from gi.types import GObjectMeta
from blueman.bluez.errors import parse_dbus_error, BluezDBusException
import logging

DBUS_TIMEOUT = 10 * 1_000
DBUS_CALL_FLAGS_NONE = cast(Gio.DBusCallFlags, 0)

_TBase = TypeVar("_TBase", bound="Base")


class BaseMeta(GObjectMeta):
    def __call__(cls: type[_TBase], *args: object, **kwargs: object) -> _TBase:  # pyright: ignore[reportGeneralTypeIssues]
        if not hasattr(cls, "__instances__"):
            cls.__instances__: dict[str, "Base"] = {}

        path = kwargs.get("obj_path")
        if path is None:
            path = getattr(cls, "_obj_path")
        path = cast(str, path)

        if path in cls.__instances__:
            return cast(_TBase, cls.__instances__[path])

        instance = cast(_TBase, super().__call__(*args, **kwargs))
        cls.__instances__[path] = instance

        return instance


class Base(GObject.Object, metaclass=BaseMeta):
    __name = 'org.bluez'
    __bus_type = Gio.BusType.SYSTEM
    __proxy: Gio.DBusProxy

    __gsignals__: GSignals = {
        'property-changed': (GObject.SignalFlags.NO_HOOKS, None, (str, object, str))
    }
    __instances__: dict[str, "Base"]

    _interface_name: str

    def connect_signal(
        self: _TBase,
        signal_name: str,
        handler: Callable[[_TBase, str, object, ObjectPath], Any],
        *args: object,
    ) -> int:
        return cast(int, cast(Any, GObject.GObject.connect)(self, signal_name, handler, *args))

    def disconnect_signal(self, handler_id: int) -> None:
        GObject.GObject.disconnect(self, handler_id)

    def __init__(self, *, obj_path: ObjectPath):
        super().__init__()

        self.__proxy = Gio.DBusProxy.new_for_bus_sync(
            self.__bus_type,
            Gio.DBusProxyFlags(0),
            None,
            self.__name,
            obj_path,
            self._interface_name,
            None
        )

        self.__proxy.connect("g-properties-changed", self._properties_changed)

        self.__fallback = {'Icon': 'blueman', 'Class': 0, 'Appearance': 0}

        self.__variant_map = {str: 's', int: 'u', bool: 'b'}

    def _properties_changed(self, _proxy: Gio.DBusProxy, changed_properties: GLib.Variant,
                            invalidated_properties: list[str]) -> None:
        changed = changed_properties.unpack()
        object_path = self.get_object_path()
        logging.debug("%s %s %s %s", object_path, changed, invalidated_properties, self)

        for key in list(changed) + invalidated_properties:
            self.emit("property-changed", key, changed.get(key, None), object_path)

    def _call(
        self,
        method: str,
        param: GLib.Variant | None = None,
        reply_handler: Callable[..., None] | None = None,
        error_handler: Callable[[BluezDBusException], None] | None = None,
    ) -> None:
        def callback(
            proxy: Gio.DBusProxy,
            result: Gio.AsyncResult,
            reply: Callable[..., None] | None,
            error: Callable[[BluezDBusException], None] | None,
        ) -> None:
            try:
                value = proxy.call_finish(result).unpack()
                if reply:
                    reply(*value)
            except GLib.Error as e:
                if error:
                    error(parse_dbus_error(e))
                else:
                    logging.error(
                        "Unhandled error for %s.%s",
                        self.__proxy.get_interface_name(),
                        method,
                        exc_info=True,
                    )

        self.__proxy.call(method, param, DBUS_CALL_FLAGS_NONE, DBUS_TIMEOUT, None,
                          callback, reply_handler, error_handler)

    def get(self, name: str) -> Any:
        try:
            prop = self.__proxy.call_sync(
                'org.freedesktop.DBus.Properties.Get',
                GLib.Variant('(ss)', (self._interface_name, name)),
                DBUS_CALL_FLAGS_NONE,
                DBUS_TIMEOUT,
                None)
            return prop.unpack()[0]
        except GLib.Error as e:
            cached_property = self.__proxy.get_cached_property(name)
            if cached_property is not None:
                return cached_property.unpack()
            elif name in self.__fallback:
                return self.__fallback[name]
            else:
                raise parse_dbus_error(e) from e

    def set(self, name: str, value: str | int | bool) -> None:
        v = GLib.Variant(self.__variant_map[type(value)], value)
        param = GLib.Variant('(ssv)', (self._interface_name, name, v))
        self.__proxy.call('org.freedesktop.DBus.Properties.Set',
                          param,
                          DBUS_CALL_FLAGS_NONE,
                          DBUS_TIMEOUT,
                          None)

    def get_object_path(self) -> ObjectPath:
        return ObjectPath(self.__proxy.get_object_path())

    def get_properties(self) -> dict[str, Any]:
        param = GLib.Variant('(s)', (self._interface_name,))
        res = self.__proxy.call_sync('org.freedesktop.DBus.Properties.GetAll',
                                     param,
                                     DBUS_CALL_FLAGS_NONE,
                                     DBUS_TIMEOUT,
                                     None)

        props: dict[str, Any] = res.unpack()[0]
        for k, v in self.__fallback.items():
            if k in props:
                continue
            else:
                props[k] = v

        return props

    def destroy(self) -> None:
        if self.__proxy:
            del self.__proxy

    def __getitem__(self, key: str) -> Any:
        return self.get(key)

    def __setitem__(self, key: str, value: str | int | bool) -> None:
        self.set(key, value)

    def __contains__(self, key: str) -> bool:
        return key in self.get_properties()
