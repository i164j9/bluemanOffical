from gettext import gettext as _
from typing import Any, cast
from collections.abc import Iterable, Callable, Mapping

import logging

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk

from gi.repository.GObject import GObject

from blueman.Functions import create_menuitem
from blueman.Sdp import ServiceUUID
from blueman.bluez.Device import Device
from blueman.bluez.errors import BluezDBusException
from blueman.gui.manager.ManagerDeviceMenu import MenuItemsProvider, ManagerDeviceMenu, DeviceMenuItem

from blueman.plugins.ManagerPlugin import ManagerPlugin


NO_ACCEL_FLAGS = cast(Gtk.AccelFlags, 0)


def _format_hex_bytes(value: object) -> str:
    if isinstance(value, (bytes, bytearray)):
        return " ".join(f"{byte:02x}" for byte in value)

    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, bytearray, Mapping)):
        values = list(value)
        if values and all(isinstance(item, int) for item in values):
            return " ".join(f"{item:02x}" for item in values)

    return str(value)


def _format_mapping_value(key: object, value: object) -> str:
    if isinstance(key, int):
        prefix = f"0x{key:04x}"
    else:
        prefix = str(key)

    return f"{prefix}: {_format_hex_bytes(value)}"


def format_mapping(data: Mapping[object, object]) -> str:
    if not data:
        return ""

    return "\n".join(_format_mapping_value(key, value) for key, value in data.items())


def show_info(device: Device, parent: Gtk.Window) -> None:
    def format_boolean(x: bool) -> str:
        return _('yes') if x else _('no')

    def format_rssi(rssi: int) -> str:
        if rssi in [0x99, 0x7f]:
            return f'invalid (0x{rssi:02x})'
        else:
            return f'{rssi} dBm (0x{rssi:02x})'

    def format_uuids(uuids: Iterable[str]) -> str:
        return "\n".join([uuid + ' ' + ServiceUUID(uuid).name for uuid in uuids])

    def format_advflags(flags: Iterable[bytes]) -> str:
        return _format_hex_bytes(flags)

    store = Gtk.ListStore(str, str)
    view = Gtk.TreeView(model=store, headers_visible=False)
    view_selection = view.get_selection()
    view_selection.set_mode(Gtk.SelectionMode.MULTIPLE)

    def on_accel_activated(_group: Gtk.AccelGroup, _dialog: GObject, key: int, _modifier: Gdk.ModifierType) -> bool:
        if key != 99:
            logging.warning("Ignoring key %s", key)
            return False

        store, paths = view_selection.get_selected_rows()

        text = []
        for path in paths:
            row = store[path]
            text.append(row[-1])

        logging.info("\n".join(text))
        clipboard.set_text("\n".join(text), -1)

        return False

    clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    dialog = Gtk.Dialog(icon_name="blueman", title="blueman")
    dialog.set_transient_for(parent)
    dialog_content_area = dialog.get_content_area()

    label = Gtk.Label()
    label.set_markup(_("<big>Select row(s) and use <i>Control + C</i> to copy</big>"))
    label.show()
    dialog_content_area.pack_start(label, True, False, 0)

    accelgroup = Gtk.AccelGroup()
    dialog.add_accel_group(accelgroup)

    key, mod = Gtk.accelerator_parse("<Control>C")
    accelgroup.connect(key, mod, NO_ACCEL_FLAGS, on_accel_activated)

    for i in range(2):
        column = Gtk.TreeViewColumn()
        cell = Gtk.CellRendererText()
        column.pack_start(cell, True)
        column.add_attribute(cell, 'text', i)
        view.append_column(column)
    dialog_content_area.pack_start(view, True, False, 0)
    view.show_all()

    properties: Iterable[tuple[str, Callable[[Any], str] | None]] = (
        ('Address', None),
        ('AddressType', None),
        ('Name', None),
        ('Alias', None),
        ('Class', lambda x: f"0x{x:06x}"),
        ('Appearance', lambda x: f"0x{x:04x}"),
        ('Icon', None),
        ('Paired', format_boolean),
        ('CablePairing', format_boolean),
        ('Trusted', format_boolean),
        ('Blocked', format_boolean),
        ('LegacyPairing', format_boolean),
        ('RSSI', format_rssi),
        ('Connected', format_boolean),
        ('UUIDs', format_uuids),
        ('Modalias', None),
        ('Adapter', None),
        ('ManufacturerData', format_mapping),
        ('ServiceData', format_mapping),
        ('AdvertisingData', format_mapping),
        ('AdvertisingFlags', format_advflags),
        ('WakeAllowed', format_boolean),
        ('PreferredBearer', str)

    )
    for name, func in properties:
        try:
            if func is None:
                store.append((name, device.get(name)))
            else:
                store.append((name, func(device.get(name))))
        except BluezDBusException:
            logging.info("Could not get property %s", name)
            continue
        except ValueError:
            logging.info("Could not add property %s", name)
            continue

    dialog.run()
    dialog.destroy()


class Info(ManagerPlugin, MenuItemsProvider):
    def on_request_menu_items(
        self,
        manager_menu: ManagerDeviceMenu,
        device: Device,
        _powered: bool,
    ) -> list[DeviceMenuItem]:
        item = create_menuitem(_("_Info"), "dialog-information-symbolic")
        item.props.tooltip_text = _("Show device information")
        window = manager_menu.get_toplevel()
        assert isinstance(window, Gtk.Window)
        item.connect('activate', lambda x: show_info(device, window))
        return [DeviceMenuItem(item, DeviceMenuItem.Group.ACTIONS, 400)]
