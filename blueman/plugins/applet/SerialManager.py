from gettext import gettext as _
from dataclasses import dataclass
from typing import Any
import shlex
from blueman.bluemantyping import ObjectPath, BtAddress

from blueman.plugins.AppletPlugin import AppletPlugin
from blueman.gui.Notification import Notification
from blueman.Sdp import SERIAL_PORT_SVCLASS_ID
from blueman.plugins.applet.DBusService import RFCOMMConnectedListener
from blueman.services.Functions import get_services
from _blueman import rfcomm_list, RFCOMMError
from subprocess import Popen
import logging
import os
import signal
from blueman.bluez.Device import Device
from gi.repository import GLib

from blueman.services.meta import SerialService


@dataclass
class ScriptProcess:
    process: "Popen[Any]"
    watch_id: int


class SerialManager(AppletPlugin, RFCOMMConnectedListener):
    __icon__ = "bluetooth-symbolic"
    __description__ = _("Standard SPP profile connection handler, allows executing custom actions")
    __author__ = "walmis"

    __gsettings__ = {
        "schema": "org.blueman.plugins.serialmanager",
        "path": None
    }
    __options__ = {
        "script": {"type": str, "default": "",
                   "name": _("Script to execute on connection"),
                   "desc": _("<span size=\"small\">The following arguments will be passed:\n"
                             "Address, Name, service name, uuid16s, rfcomm node\n"
                             "For example:\n"
                             "AA:BB:CC:DD:EE:FF, Phone, DUN service, 0x1103, /dev/rfcomm0\n"
                             "uuid16s are returned as a comma separated list\n\n"
                             "Upon device disconnection the script will be sent a HUP signal</span>")},
    }

    scripts: dict[BtAddress, dict[str, ScriptProcess]] = {}

    def on_load(self) -> None:
        self.scripts = {}

    def on_unload(self) -> None:
        for bdaddr in list(self.scripts):
            self.terminate_all_scripts(bdaddr)
        self.scripts = {}

    def on_delete(self) -> None:
        logging.debug("Terminating any running scripts")
        for bdaddr in list(self.scripts):
            self.terminate_all_scripts(bdaddr)
        self.scripts = {}

    def on_device_property_changed(self, path: ObjectPath, key: str, value: Any) -> None:
        if key == "Connected" and not value:
            device = Device(obj_path=path)
            self.terminate_all_scripts(device["Address"])
            self.on_device_disconnect(device)

    def on_rfcomm_connected(self, service: SerialService, port: str) -> None:
        device = service.device
        if SERIAL_PORT_SVCLASS_ID == service.short_uuid:
            Notification(_("Serial port connected"),
                         _("Serial port service on device <b>%s</b> now will be available via <b>%s</b>") % (
                         device.display_name, port),
                         icon_name="blueman-serial").show()

            self.call_script(device['Address'],
                             device.display_name,
                             service.name,
                             service.short_uuid,
                             port)

    def terminate_all_scripts(self, address: BtAddress) -> None:
        script_map = self.scripts.get(address)
        if not script_map:
            # Script already terminated or failed to start
            return

        for node in list(script_map):
            self._stop_script(address, node)

        self.scripts.pop(address, None)

    def _stop_script(self, address: BtAddress, node: str) -> None:
        script_map = self.scripts.get(address)
        if not script_map:
            return

        entry = script_map.pop(node, None)
        if entry is None:
            return

        GLib.source_remove(entry.watch_id)
        logging.info("Sending HUP to %s", entry.process.pid)

        try:
            os.killpg(entry.process.pid, signal.SIGHUP)
        except ProcessLookupError:
            logging.debug("No process found for pid %s", entry.process.pid)

        if not script_map:
            self.scripts.pop(address, None)

    def _remove_script(self, address: BtAddress, node: str, pid: int) -> None:
        script_map = self.scripts.get(address)
        if not script_map:
            return

        entry = script_map.get(node)
        if entry is None or entry.process.pid != pid:
            return

        del script_map[node]
        if not script_map:
            del self.scripts[address]

    def on_script_closed(self, pid: int, _cond: int, address_node: tuple[BtAddress, str]) -> None:
        address, node = address_node
        self._remove_script(address, node, pid)
        logging.info("Script with PID %s closed", pid)

    def manage_script(self, address: BtAddress, node: str, process: "Popen[Any]") -> None:
        script_map = self.scripts.setdefault(address, {})

        if node in script_map:
            self._stop_script(address, node)
            script_map = self.scripts.setdefault(address, {})

        watch_id = GLib.child_watch_add(process.pid, self.on_script_closed, (address, node))
        script_map[node] = ScriptProcess(process=process, watch_id=watch_id)

    def call_script(self, address: BtAddress, name: str, sv_name: str, uuid16: int, node: str) -> None:
        c = self.get_option("script")
        if c and c != "":
            try:
                args = shlex.split(c)
                args += [address, name, sv_name, f"{uuid16:#x}", node]
                logging.debug(" ".join(args))
                p = Popen(args, start_new_session=True)

                self.manage_script(address, node, p)

            except (OSError, ValueError) as e:
                logging.debug(str(e))
                Notification(_("Serial port connection script failed"),
                             _("There was a problem launching script %s\n"
                               "%s") % (c, str(e)),
                             icon_name="blueman-serial").show()

    def on_rfcomm_disconnect(self, port: int) -> None:
        for scripts in self.scripts.values():
            entry = scripts.get(f"/dev/rfcomm{port:i}")
            if entry:
                logging.info("Sending HUP to %s", entry.process.pid)
                try:
                    os.killpg(entry.process.pid, signal.SIGHUP)
                except ProcessLookupError:
                    logging.debug("No process found for pid %s", entry.process.pid)

    def on_device_disconnect(self, device: Device) -> None:
        serial_services = [service for service in get_services(device) if isinstance(service, SerialService)]

        if not serial_services:
            return

        try:
            active_ports = [rfcomm['id'] for rfcomm in rfcomm_list() if rfcomm['dst'] == device['Address']]
        except RFCOMMError as e:
            logging.error("rfcomm_list failed with: %s", e)
            return

        for port in active_ports:
            name = f"/dev/rfcomm{port:d}"
            try:
                logging.info("Disconnecting %s", name)
                serial_services[0].disconnect(port)
            except GLib.Error:
                logging.error("Failed to disconnect %s", name, exc_info=True)
