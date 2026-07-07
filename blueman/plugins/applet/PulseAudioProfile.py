import logging
from gettext import gettext as _
from html import escape
from typing import Any
from collections.abc import Mapping, Callable

from blueman.bluez.Device import Device
from blueman.main.PulseAudioUtils import (
    CardInfo,
    CardProfileInfo,
    EventType,
    PulseAudioUtils,
    describe_event_type,
    summarize_card_info,
)
from blueman.plugins.AppletPlugin import AppletPlugin
from blueman.plugins.applet.Menu import MenuItem, SubmenuItemDict
from blueman.Sdp import (AUDIO_SINK_SVCLASS_ID, AUDIO_SOURCE_SVCLASS_ID,
                         ServiceUUID)


class AudioProfiles(AppletPlugin):
    __depends__ = ["Menu"]
    __description__ = _("Adds audio profile selector to the status icon menu")
    __author__ = "Abhijeet Viswa"
    _pa_event_handler_id: int | None = None
    _pa_connected_handler_id: int | None = None

    def __init__(self, parent: Any):
        super().__init__(parent)
        self._active = False
        self._devices: dict[str, CardInfo] = {}
        self._device_menus: dict[str, MenuItem] = {}
        self._menu: Any = None
        self._pa: PulseAudioUtils | None = None

    def on_load(self) -> None:
        self._active = True
        self._devices = {}
        self._device_menus = {}

        self._menu = self.parent.Plugins.Menu

        pa = PulseAudioUtils()
        self._pa = pa
        self._pa_event_handler_id = pa.connect("event", self.on_pa_event)
        self._pa_connected_handler_id = pa.connect("connected", self.on_pa_ready)

    def generate_menu(self) -> None:
        devices = self.parent.Manager.get_devices()
        for device in devices:
            if device['Connected']:
                self.request_device_profile_menu(device)

    def request_device_profile_menu(self, device: Device) -> None:
        audio_source = False
        for uuid in device['UUIDs']:
            if ServiceUUID(uuid).short_uuid in (AUDIO_SOURCE_SVCLASS_ID, AUDIO_SINK_SVCLASS_ID):
                audio_source = True
                break

        if device['Connected'] and audio_source:
            pa = PulseAudioUtils()
            logging.debug(
                "PulseAudioProfile applet menu request device=%s connected=%s audio_source=%s known_card=%s pa_connected=%s",
                device['Address'],
                device['Connected'],
                audio_source,
                device['Address'] in self._devices,
                pa.connected,
            )
            if not pa.connected:
                return

            if not device['Address'] in self._devices:
                self.query_pa(device)
            else:
                self.add_device_profile_menu(device)

    def add_device_profile_menu(self, device: Device) -> None:
        def _activate_profile_wrapper(device: Device, profile: CardProfileInfo) -> Callable[[], None]:
            def _wrapper() -> None:
                self.on_activate_profile(device, profile)
            return _wrapper

        def _generate_profiles_menu(info: CardInfo) -> list[SubmenuItemDict]:
            items: list[SubmenuItemDict] = []
            if not info:
                return items
            for profile in info["profiles"]:
                profile_name = escape(profile["description"])
                profile_icon = "bluetooth-symbolic"
                if profile["name"] == info["active_profile"]:
                    profile_name = f"<b>{profile_name}</b>"
                    profile_icon = "dialog-ok"
                items.append({
                    "text": profile_name,
                    "markup": True,
                    "icon_name": profile_icon,
                    "sensitive": True,
                    "callback": _activate_profile_wrapper(device, profile),
                    "tooltip": "",
                })
            return items

        info = self._devices[device['Address']]
        idx = max((item.priority[1] for item in self._device_menus.values()), default=-1) + 1
        menu = self._menu.add(self, (42, idx), _("Audio Profiles for %s") % device.display_name,
                              icon_name="audio-card-symbolic",
                              submenu_function=lambda: _generate_profiles_menu(info))
        self._device_menus[device['Address']] = menu

    def query_pa(self, device: Device) -> None:
        def list_cb(cards: Mapping[str, CardInfo]) -> None:
            if not self._active:
                return

            for c in cards.values():
                if c["proplist"].get("device.string") == device['Address']:
                    self._devices[device['Address']] = c
                    logging.debug(
                        "PulseAudioProfile applet matched card for %s: %s",
                        device['Address'],
                        summarize_card_info(c),
                    )
                    self.add_device_profile_menu(device)
                    return

            logging.debug(
                "PulseAudioProfile applet found no PulseAudio card for %s across %d cards",
                device['Address'],
                len(cards),
            )

        pa = PulseAudioUtils()
        logging.debug("PulseAudioProfile applet querying cards for %s", device['Address'])
        pa.list_cards(list_cb)

    def on_activate_profile(self, device: Device, profile: CardProfileInfo) -> None:
        pa = PulseAudioUtils()

        c = self._devices[device['Address']]
        logging.debug(
            "PulseAudioProfile applet set profile device=%s card_idx=%s profile=%s",
            device['Address'],
            c['index'],
            profile['name'],
        )

        def on_result(res: int) -> None:
            if not self._active:
                return

            logging.debug(
                "PulseAudioProfile applet set profile result device=%s profile=%s result=%s",
                device['Address'],
                profile['name'],
                res,
            )
            if not res:
                logging.error("Failed to change profile to %s", profile['name'])

        pa.set_card_profile(c["index"], profile["name"], on_result)

    def on_pa_event(self, utils: PulseAudioUtils, event: int, idx: int) -> None:
        logging.debug("PulseAudioProfile applet event %s idx=%s", describe_event_type(event), idx)

        def get_card_cb(card: CardInfo) -> None:
            if not self._active:
                return

            drivers = ("module-bluetooth-device.c",
                       "module-bluez4-device.c",
                       "module-bluez5-device.c")

            if card["driver"] in drivers:
                logging.debug("PulseAudioProfile applet card update: %s", summarize_card_info(card))
                self._devices[card["proplist"]["device.string"]] = card
                self.clear_menu()
                self.generate_menu()
            else:
                logging.debug("PulseAudioProfile applet ignoring card: %s", summarize_card_info(card))

        if event & EventType.FACILITY_MASK == EventType.CARD:
            if event & EventType.TYPE_MASK == EventType.CHANGE:
                utils.get_card(idx, get_card_cb)
            elif event & EventType.TYPE_MASK == EventType.REMOVE:
                logging.debug("PulseAudioProfile applet card removed idx=%s", idx)
            else:
                utils.get_card(idx, get_card_cb)

    def on_pa_ready(self, _utils: PulseAudioUtils) -> None:
        if not self._active:
            return

        logging.debug(
            "PulseAudioProfile applet ready known_cards=%d menu_devices=%d",
            len(self._devices),
            len(self._device_menus),
        )
        self.generate_menu()

    def on_adapter_added(self, path: str) -> None:
        self.clear_menu()
        self.generate_menu()

    def on_adapter_removed(self, path: str) -> None:
        self.clear_menu()
        self.generate_menu()

    def on_device_property_changed(self, path: str, key: str, value: Any) -> None:
        if key == "Connected":
            logging.debug(
                "PulseAudioProfile applet device property changed path=%s key=%s value=%r",
                path,
                key,
                value,
            )
            self.clear_menu()
            self.generate_menu()

    def on_manager_state_changed(self, state: bool) -> None:
        self.clear_menu()

    def on_unload(self) -> None:
        self._active = False
        if self._pa is not None and self._pa_event_handler_id is not None \
                and self._pa.handler_is_connected(self._pa_event_handler_id):
            self._pa.disconnect(self._pa_event_handler_id)
            self._pa_event_handler_id = None
        elif self._pa_event_handler_id is not None:
            self._pa_event_handler_id = None
        if self._pa is not None and self._pa_connected_handler_id is not None \
                and self._pa.handler_is_connected(self._pa_connected_handler_id):
            self._pa.disconnect(self._pa_connected_handler_id)
            self._pa_connected_handler_id = None
        elif self._pa_connected_handler_id is not None:
            self._pa_connected_handler_id = None
        self.clear_menu()

    def clear_menu(self) -> None:
        self._device_menus = {}
        self._menu.unregister(self)
