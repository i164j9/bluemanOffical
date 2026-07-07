from gettext import gettext as _
import logging
from collections.abc import Mapping, Sequence

from blueman.bluez.Device import Device
from blueman.plugins.ManagerPlugin import ManagerPlugin
from blueman.main.PulseAudioUtils import (
    PulseAudioUtils,
    EventType,
    describe_event_type,
    summarize_card_info,
)
from blueman.gui.manager.ManagerDeviceMenu import ManagerDeviceMenu, MenuItemsProvider, DeviceMenuItem
from blueman.Functions import create_menuitem
from blueman.Sdp import AUDIO_SOURCE_SVCLASS_ID, AUDIO_SINK_SVCLASS_ID, ServiceUUID

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from blueman.main.PulseAudioUtils import CardInfo


class PulseAudioProfile(ManagerPlugin, MenuItemsProvider):
    devices: dict[str, CardInfo]
    deferred: list[Device]
    _pa: PulseAudioUtils
    _pa_event_handler_id: int | None = None
    _pa_connected_handler_id: int | None = None
    _active: bool

    def on_load(self) -> None:
        self._active = True
        self.devices: dict[str, CardInfo] = {}

        self.deferred: list[Device] = []

        self._pa = PulseAudioUtils()
        self._pa_event_handler_id = self._pa.connect("event", self.on_pa_event)
        self._pa_connected_handler_id = self._pa.connect("connected", self.on_pa_ready)

    def on_unload(self) -> None:
        self._active = False
        if self._pa_event_handler_id is not None and self._pa.handler_is_connected(self._pa_event_handler_id):
            self._pa.disconnect(self._pa_event_handler_id)
            self._pa_event_handler_id = None
        elif self._pa_event_handler_id is not None:
            self._pa_event_handler_id = None
        if self._pa_connected_handler_id is not None and self._pa.handler_is_connected(self._pa_connected_handler_id):
            self._pa.disconnect(self._pa_connected_handler_id)
            self._pa_connected_handler_id = None
        elif self._pa_connected_handler_id is not None:
            self._pa_connected_handler_id = None

    def on_pa_ready(self, _utils: PulseAudioUtils) -> None:
        if not self._active:
            return

        logging.debug(
            "PulseAudioProfile manager ready deferred=%s known_cards=%d",
            [dev['Address'] for dev in self.deferred],
            len(self.devices),
        )
        for dev in self.deferred:
            self.regenerate_with_device(dev['Address'])

        self.deferred = []

    # updates all menu instances with the following device address
    def regenerate_with_device(self, device_addr: str) -> None:
        for inst in ManagerDeviceMenu.__instances__:
            if inst.SelectedDevice['Address'] == device_addr and not inst.is_popup:
                inst.generate()

    def on_pa_event(self, utils: PulseAudioUtils, event: int, idx: int) -> None:
        logging.debug("PulseAudioProfile manager event %s idx=%s", describe_event_type(event), idx)

        def get_card_cb(card: CardInfo) -> None:
            if not self._active:
                return

            drivers = ("module-bluetooth-device.c",
                       "module-bluez4-device.c",
                       "module-bluez5-device.c")

            if card["driver"] in drivers:
                logging.debug("PulseAudioProfile manager card update: %s", summarize_card_info(card))
                self.devices[card["proplist"]["device.string"]] = card
                self.regenerate_with_device(card["proplist"]["device.string"])
            else:
                logging.debug("PulseAudioProfile manager ignoring card: %s", summarize_card_info(card))

        if event & EventType.FACILITY_MASK == EventType.CARD:
            if event & EventType.CHANGE:
                utils.get_card(idx, get_card_cb)
            elif event & EventType.REMOVE:
                logging.debug("PulseAudioProfile manager card removed idx=%s", idx)
            else:
                utils.get_card(idx, get_card_cb)

    def query_pa(self, device: Device, item: Gtk.MenuItem) -> None:
        def list_cb(cards: Mapping[str, CardInfo]) -> None:
            if not self._active:
                return

            for c in cards.values():
                if c["proplist"].get("device.string") == device['Address']:
                    self.devices[device['Address']] = c
                    logging.debug(
                        "PulseAudioProfile manager matched card for %s: %s",
                        device['Address'],
                        summarize_card_info(c),
                    )
                    self.generate_menu(device, item)
                    return

            logging.debug(
                "PulseAudioProfile manager found no PulseAudio card for %s across %d cards",
                device['Address'],
                len(cards),
            )

        pa = PulseAudioUtils()
        logging.debug("PulseAudioProfile manager querying cards for %s", device['Address'])
        pa.list_cards(list_cb)

    def on_selection_changed(self, item: Gtk.CheckMenuItem, device: Device, profile: str) -> None:
        if item.get_active():
            pa = PulseAudioUtils()

            c = self.devices[device['Address']]
            logging.debug(
                "PulseAudioProfile manager set profile device=%s card_idx=%s profile=%s",
                device['Address'],
                c['index'],
                profile,
            )

            def on_result(res: int) -> None:
                if not self._active:
                    return

                logging.debug(
                    "PulseAudioProfile manager set profile result device=%s profile=%s result=%s",
                    device['Address'],
                    profile,
                    res,
                )
                if not res:
                    self.parent.infobar_update(_("Failed to change profile to %s" % profile))

            pa.set_card_profile(c["index"], profile, on_result)

    def generate_menu(self, device: Device, item: Gtk.MenuItem) -> None:
        info = self.devices[device['Address']]
        logging.debug(
            "PulseAudioProfile manager build menu for %s active_profile=%s profiles=%s",
            device['Address'],
            info['active_profile'],
            [profile['name'] for profile in info['profiles']],
        )
        group: Sequence[Gtk.RadioMenuItem] = []

        sub = Gtk.Menu()

        if info:
            for profile in info["profiles"]:
                i = Gtk.RadioMenuItem.new_with_label(group, profile["description"])
                group = i.get_group()

                if profile["name"] == info["active_profile"]:
                    i.set_active(True)

                i.connect("toggled", self.on_selection_changed,
                          device, profile["name"])

                sub.append(i)
                i.show()

            item.set_submenu(sub)
            item.show()

    def on_request_menu_items(
        self,
        _manager_menu: ManagerDeviceMenu,
        device: Device,
        _powered: bool,
    ) -> list[DeviceMenuItem]:
        audio_source = False
        for uuid in device['UUIDs']:
            if ServiceUUID(uuid).short_uuid in (AUDIO_SOURCE_SVCLASS_ID, AUDIO_SINK_SVCLASS_ID):
                audio_source = True
                break

        if device['Connected'] and audio_source:

            pa = PulseAudioUtils()
            logging.debug(
                "PulseAudioProfile manager menu request device=%s connected=%s audio_source=%s known_card=%s pa_connected=%s",
                device['Address'],
                device['Connected'],
                audio_source,
                device['Address'] in self.devices,
                pa.connected,
            )
            if not pa.connected:
                self.deferred.append(device)
                return []

            item = create_menuitem(_("Audio Profile"), "audio-card-symbolic")
            item.props.tooltip_text = _("Select audio profile for PulseAudio")

            if not device['Address'] in self.devices:
                self.query_pa(device, item)
            else:
                self.generate_menu(device, item)

        else:
            return []

        return [DeviceMenuItem(item, DeviceMenuItem.Group.ACTIONS, 300)]
