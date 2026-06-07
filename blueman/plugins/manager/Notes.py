import datetime
from gettext import gettext as _
from tempfile import NamedTemporaryFile

from blueman.Functions import create_menuitem, launch
from blueman.bluez.Device import Device
from blueman.gui.manager.ManagerDeviceMenu import MenuItemsProvider, ManagerDeviceMenu, DeviceMenuItem
from blueman.main.Builder import Builder
from blueman.plugins.ManagerPlugin import ManagerPlugin

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


def normalize_note_text(text: str) -> str:
    return " ".join(text.splitlines()).strip()


def build_note_data(text: str, now: datetime.datetime | None = None) -> str | None:
    normalized = normalize_note_text(text)
    if not normalized:
        return None

    timestamp = (now or datetime.datetime.now()).strftime('%Y%m%dT%H%M00')
    return (
        'BEGIN:VNOTE \n'
        'VERSION:1.1 \n'
        f'BODY;CHARSET=UTF-8: {normalized} \n'
        f'DCREATED:{timestamp} \n'
        f'LAST-MODIFIED:{timestamp} \n'
        'CLASS:PUBLIC \n'
        'X-IRMC-LUID:000001000000 \n'
        'END:VNOTE \n'
    )


def update_note_response_state(dialog: Gtk.Dialog, note: Gtk.Entry) -> None:
    dialog.set_response_sensitive(Gtk.ResponseType.ACCEPT, bool(normalize_note_text(note.get_text())))


def send_note_cb(dialog: Gtk.Dialog, response_id: int, device_address: str, text_view: Gtk.Entry) -> None:
    text = text_view.get_text()
    dialog.destroy()
    if response_id == Gtk.ResponseType.REJECT:
        return

    data = build_note_data(text)
    if data is None:
        return

    tempfile = NamedTemporaryFile(suffix='.vnt', prefix='note', delete=False)
    tempfile.write(data.encode('utf-8'))
    tempfile.close()
    launch(f"blueman-sendto --delete --device={device_address}", paths=[tempfile.name])


def send_note(device: Device, parent: Gtk.ApplicationWindow) -> None:
    builder = Builder("note.ui")
    dialog = builder.get_widget("dialog", Gtk.Dialog)
    dialog.set_transient_for(parent)
    dialog.props.icon_name = 'blueman'
    note = builder.get_widget("note", Gtk.Entry)
    update_note_response_state(dialog, note)
    note.connect('changed', lambda _entry: update_note_response_state(dialog, note))
    dialog.connect('response', send_note_cb, device['Address'], note)
    dialog.present()


class Notes(ManagerPlugin, MenuItemsProvider):
    def on_request_menu_items(
        self,
        manager_menu: ManagerDeviceMenu,
        device: Device,
        powered: bool,
    ) -> list[DeviceMenuItem]:
        if not powered:
            return []

        item = create_menuitem(_("Send _note"), "dialog-information-symbolic")
        item.props.tooltip_text = _("Send a text note")
        assert isinstance(manager_menu.Blueman.window, Gtk.ApplicationWindow)
        window = manager_menu.Blueman.window  # https://github.com/python/mypy/issues/2608
        item.connect('activate', lambda x: send_note(device, window))
        return [DeviceMenuItem(item, DeviceMenuItem.Group.ACTIONS, 500)]
