import logging
import signal
from gettext import gettext as _
from typing import Any
from collections.abc import Callable

from blueman.bluez.Adapter import Adapter
from blueman.bluez.Device import Device
from blueman.bluez.Manager import Manager
from blueman.Constants import WEBSITE
from blueman.Functions import bmexit, e_, launch, log_system_info, setup_icon_path
from blueman.gui.manager.ManagerDeviceList import ManagerDeviceList
from blueman.gui.manager.ManagerToolbar import ManagerToolbar
from blueman.gui.manager.ManagerMenu import ManagerMenu
from blueman.gui.manager.ManagerStats import ManagerStats
from blueman.gui.manager.ManagerProgressbar import ManagerProgressbar
from blueman.main.Builder import Builder
from blueman.gui.CommonUi import ErrorDialog, show_about_dialog
from blueman.main.DBusProxies import (
    AppletService,
    AppletPowerManagerService,
    DBusProxyFailed,
    DBus,
    AppletServiceApplication
)
from blueman.gui.Notification import Notification
from blueman.main.PluginManager import PluginManager
import blueman.plugins.manager
from blueman.plugins.ManagerPlugin import ManagerPlugin

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, Gio, Gdk, GLib, GLibUnix


def _is_missing_power_manager_interface(error: GLib.Error) -> bool:
    message = str(error)
    return "org.freedesktop.DBus.Error.UnknownMethod" in message or "No such interface" in message


POWER_MANAGER_STATUS_RETRY_INTERVAL_MS = 250
POWER_MANAGER_STATUS_RETRY_LIMIT = 5


class Blueman(Gtk.Application):
    window: Gtk.ApplicationWindow | None
    Config: Gio.Settings
    builder: Builder
    _infobar: Gtk.InfoBar
    _infobar_bt: str
    List: ManagerDeviceList
    Toolbar: ManagerToolbar
    Menu: ManagerMenu
    Stats: ManagerStats
    _power_manager_retry_source_id: int | None
    _power_manager_retry_attempts: int

    def __init__(self) -> None:
        super().__init__(application_id="org.blueman.Manager")
        self._applet_was_running = DBus().NameHasOwner("(s)", AppletService.NAME)
        self._power_manager_retry_source_id = None
        self._power_manager_retry_attempts = 0

        def do_quit(_: object) -> bool:
            self.quit()
            return False

        log_system_info()

        s = GLibUnix.signal_source_new(signal.SIGINT)
        s.set_callback(do_quit)
        s.attach()

        setup_icon_path()

        try:
            self.Applet = AppletService()
            self.Applet.connect('g-signal', self.on_applet_signal)
            self.PowerManager = AppletPowerManagerService()
        except DBusProxyFailed:
            print("Blueman applet needs to be running")
            bmexit()

        self.Plugins = PluginManager(ManagerPlugin, blueman.plugins.manager, self)
        self.Plugins.load_plugin()

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        self.window = None

        self.Config = Gio.Settings(schema_id="org.blueman.general")

        self.builder = Builder("manager-main.ui")

        self._infobar = self.builder.get_widget("message_area", Gtk.InfoBar)
        self._infobar.connect("response", self._infobar_response)
        self._infobar_bt: str = ""

        self.register_action("inquiry", self.simple_action)
        self.register_action("bond", self.simple_action)
        self.register_action("trust-toggle", self.simple_action)
        self.register_action("remove", self.simple_action)
        self.register_action("send", self.simple_action)
        self.register_action("report", self.simple_action)
        self.register_action("about", self.simple_action)
        self.register_action("plugins", self.simple_action)
        self.register_action("services", self.simple_action)
        self.register_action("preferences", self.simple_action)

        self.register_action("Quit", self.simple_action)
        self.set_accels_for_action("app.Quit", ["<Ctrl>q", "<Ctrl>w"])

        self.register_settings_action("sort-descending")
        self.register_settings_action("show-toolbar")
        self.register_settings_action("show-statusbar")
        self.register_settings_action("hide-unnamed")
        self.register_settings_action("sort-by")

        bt_status_action = Gio.SimpleAction.new_stateful("bluetooth_status", None, GLib.Variant.new_boolean(False))
        bt_status_action.connect("change-state", self._on_bt_state_changed)
        self.add_action(bt_status_action)

        Manager.watch_name_owner(self.on_dbus_name_appeared, self.on_dbus_name_vanished)

    def do_shutdown(self) -> None:
        self._clear_power_manager_status_retry()
        Gtk.Application.do_shutdown(self)

        if not self._applet_was_running:
            AppletServiceApplication().stop()

    def do_activate(self) -> None:
        if not self.window:
            self.window = self.builder.get_widget("manager_window", Gtk.ApplicationWindow)
            self.window.set_application(self)
            w, h, x, y = self.Config["window-properties"]
            if w and h:
                self.window.resize(w, h)
            if x and y:
                self.window.move(x, y)

            # Connect to configure event to store new window position and size
            self.window.connect("configure-event", self._on_configure)
            # Quit application if primary window is closed
            self.window.connect("delete-event", self._on_delete)

        self.window.present_with_time(Gtk.get_current_event_time())

    def on_applet_signal(self, _proxy: AppletService | AppletPowerManagerService, _sender: str, signal_name: str,
                         params: GLib.Variant) -> None:
        if signal_name == 'BluetoothStatusChanged':
            self._clear_power_manager_status_retry()
            status = params.unpack()[0]
            self._apply_bluetooth_status(status)
        elif signal_name == "PluginsChanged":
            if "PowerManager" in self.Applet.QueryPlugins():
                self._apply_bluetooth_status(self._get_initial_bluetooth_action_state())
            else:
                self._apply_bluetooth_status(False)

            getattr(self.Toolbar, "_update_buttons")(self.List.Adapter)

    def _apply_bluetooth_status(self, state: bool) -> None:
        action = self.lookup_action("bluetooth_status")
        assert action is not None
        action.set_state(GLib.Variant.new_boolean(state))

        if state:
            icon_name = "bluetooth"
            tooltip_text = _("Click to disable.")
        else:
            icon_name = "bluetooth-disabled"
            tooltip_text = _("Click to enable.")

        box = self.builder.get_widget("bt_status_box", Gtk.Box)
        image = self.builder.get_widget("im_bluetooth_status", Gtk.Image)
        box.set_tooltip_text(tooltip_text)
        image.props.icon_name = icon_name

    def _try_get_power_manager_status(self, log_missing: bool = True) -> bool | None:
        try:
            return self.PowerManager.get_bluetooth_status()
        except GLib.Error as e:
            if _is_missing_power_manager_interface(e):
                if log_missing:
                    logging.info("PowerManager DBus interface unavailable: %s", e)
                return None
            raise

    def _get_power_manager_status(self) -> bool:
        status = Blueman._try_get_power_manager_status(self)
        return False if status is None else status

    def _clear_power_manager_status_retry(self) -> None:
        source_id = getattr(self, "_power_manager_retry_source_id", None)
        if source_id is not None:
            GLib.source_remove(source_id)
            self._power_manager_retry_source_id = None
        self._power_manager_retry_attempts = 0

    def _schedule_power_manager_status_retry(self) -> None:
        if getattr(self, "_power_manager_retry_source_id", None) is not None:
            return
        if getattr(self, "_power_manager_retry_attempts", 0) >= POWER_MANAGER_STATUS_RETRY_LIMIT:
            return

        self._power_manager_retry_attempts = getattr(self, "_power_manager_retry_attempts", 0) + 1

        def retry() -> bool:
            self._power_manager_retry_source_id = None

            if "PowerManager" not in self.Applet.QueryPlugins():
                self._power_manager_retry_attempts = 0
                self._apply_bluetooth_status(False)
                return False

            status = Blueman._try_get_power_manager_status(self, log_missing=False)
            if status is None:
                self._apply_bluetooth_status(False)
                self._schedule_power_manager_status_retry()
                return False

            self._power_manager_retry_attempts = 0
            self._apply_bluetooth_status(status)
            return False

        self._power_manager_retry_source_id = GLib.timeout_add(POWER_MANAGER_STATUS_RETRY_INTERVAL_MS, retry)

    def _get_initial_bluetooth_action_state(self) -> bool:
        if "PowerManager" not in self.Applet.QueryPlugins():
            return False

        status = Blueman._try_get_power_manager_status(self, log_missing=False)
        if status is None:
            self._schedule_power_manager_status_retry()
            return False

        self._power_manager_retry_attempts = 0
        return status

    def on_dbus_name_appeared(self, _connection: Gio.DBusConnection, name: str, owner: str) -> None:
        logging.info("%s %s", name, owner)

        sw = self.builder.get_widget("scrollview", Gtk.ScrolledWindow)
        # Disable overlay scrolling
        if Gtk.get_minor_version() >= 16:
            sw.props.overlay_scrolling = False

        self.List = ManagerDeviceList(adapter=self.Config["last-adapter"], inst=self)

        self.List.show()
        sw.add(self.List)

        self.Toolbar = ManagerToolbar(self)
        self.Menu = ManagerMenu(self)
        self.Stats = ManagerStats(self)

        if self.List.is_valid_adapter():
            self.List.populate_devices()

        self.List.connect("adapter-changed", self.on_adapter_changed)

        self._apply_bluetooth_status(self._get_initial_bluetooth_action_state())

    def on_dbus_name_vanished(self, _connection: Gio.DBusConnection, name: str) -> None:
        logging.info(name)

        if self.window is not None:
            self.window.hide()

        d = ErrorDialog(
            _("Connection to BlueZ failed"),
            _("Bluez daemon is not running, blueman-manager cannot continue.\n"
              "This probably means that there were no Bluetooth adapters detected "
              "or Bluetooth daemon was not started."),
            icon_name="blueman")
        d.run()
        d.destroy()

        # UI already handles BlueZ start/stop; user notification could be improved.
        self.quit()

    def _on_bt_state_changed(self, _action: Gio.SimpleAction, state_variant: GLib.Variant) -> None:
        state = state_variant.unpack()
        try:
            self.PowerManager.set_bluetooth_status(state)
        except GLib.Error as e:
            if _is_missing_power_manager_interface(e):
                logging.info("PowerManager DBus interface unavailable: %s", e)
                return
            raise

        self._apply_bluetooth_status(state)

    def _on_configure(self, _window: Gtk.ApplicationWindow, event: Gdk.EventConfigure) -> bool:
        width, height, x, y = self.Config["window-properties"]
        if event.x != x or event.y != y or event.width != width or event.height != height:
            self.Config["window-properties"] = [event.width, event.height, event.x, event.y]
        return False

    def _on_delete(self, _window: Gtk.ApplicationWindow, _event: Gdk.Event) -> bool:
        self.quit()
        return False

    def register_settings_action(self, name: str) -> None:
        action = self.Config.create_action(name)
        self.add_action(action)

    def register_action(self, name: str, callback: Callable[[Gio.SimpleAction, Any | None], None],
                        vtype: GLib.VariantType | None = None) -> None:
        if name in self.list_actions():
            logging.error("%s already exists", name)
        else:
            action = Gio.SimpleAction.new(name, vtype)
            action.connect("activate", callback)
            self.add_action(action)

    def simple_action(self, action: Gio.SimpleAction, _param: GLib.Variant | None) -> None:
        match action.get_name():
            case "Quit":
                self.quit()
            case "inquiry":
                self.inquiry()
            case "bond":
                device = self.List.get_selected_device()
                if device is not None:
                    self.bond(device)
            case "trust-toggle":
                device = self.List.get_selected_device()
                if device is not None:
                    self.toggle_trust(device)
            case "remove":
                device = self.List.get_selected_device()
                if device is not None:
                    self.remove(device)
            case "send":
                device = self.List.get_selected_device()
                if device is not None:
                    self.send(device)
            case "report":
                launch(f"xdg-open {WEBSITE}/issues", system=True)
            case "about":
                widget = self.window.get_toplevel() if self.window else None
                assert isinstance(widget, Gtk.Window)
                show_about_dialog('Blueman ' + _('Device Manager'), parent=widget)
            case "plugins":
                self.Applet.OpenPluginDialog()
            case "services":
                launch("blueman-services", name=_("Service Preferences"))
            case "preferences":
                self.adapter_properties()
            case _ as name:
                logging.error("Unknown action: %s", name)

    def on_adapter_changed(self, _lst: ManagerDeviceList, adapter: str) -> None:
        if adapter is not None:
            self.List.populate_devices()

    def inquiry(self) -> None:
        def prop_changed(_lst: ManagerDeviceList, _adapter: Adapter, key_value: tuple[str, Any]) -> None:
            key, value = key_value
            if key == "Discovering" and not value:
                prog.finalize()

                self.List.disconnect(s1)
                self.List.disconnect(s2)

        def on_progress(_lst: ManagerDeviceList, frac: float) -> None:
            if abs(1.0 - frac) <= 0.00001:
                if not prog.started():
                    prog.start()
            else:
                prog.fraction(frac)

        prog = ManagerProgressbar(self, text=_("Searching"))
        prog.connect("cancelled", lambda x: self.List.stop_discovery())

        def on_error(e: Exception) -> None:
            prog.finalize()
            self.infobar_update(*e_(e))

        self.List.discover_devices(error_handler=on_error)

        s1 = self.List.connect("discovery-progress", on_progress)
        s2 = self.List.connect("adapter-property-changed", prop_changed)

    def infobar_update(self, message: str, bt: str | None = None, icon_name: str = "dialog-warning") -> None:
        if icon_name == "dialog-warning":
            self._infobar.set_message_type(Gtk.MessageType.WARNING)
        else:
            self._infobar.set_message_type(Gtk.MessageType.INFO)

        more_button = self.builder.get_widget("ib_more_button", Gtk.Button)
        image = self.builder.get_widget("ib_icon", Gtk.Image)
        msg_lbl = self.builder.get_widget("ib_message", Gtk.Label)
        image.set_from_icon_name(icon_name, 16)

        if bt is not None:
            msg_lbl.set_text(f"{message}…")
            self._infobar_bt = f"{message}\n{bt}"
            more_button.show()
        else:
            more_button.hide()
            msg_lbl.set_text(f"{message}")

        self._infobar.set_visible(True)
        self._infobar.set_revealed(True)

    def _infobar_response(self, info_bar: Gtk.InfoBar, response_id: int) -> None:
        def hide() -> bool:
            self._infobar.set_visible(False)
            return False

        logging.debug("Response: %s", response_id)
        if response_id == Gtk.ResponseType.CLOSE:
            self._infobar_bt = ""
            info_bar.set_revealed(False)
            GLib.timeout_add(250, hide)  # transition is 250.
        elif response_id == 0:
            dialog = Gtk.MessageDialog(parent=self.window, type=Gtk.MessageType.INFO, modal=True,
                                       buttons=Gtk.ButtonsType.CLOSE, text=self._infobar_bt)
            dialog.connect("response", lambda d, _i: d.destroy())
            dialog.connect("close", lambda d: d.destroy())
            dialog.show()

    @staticmethod
    def bond(device: Device) -> None:
        def error_handler(e: Exception) -> None:
            logging.exception(e)
            message = f"Pairing failed for:\n{device.display_name} ({device['Address']})"
            Notification('Bluetooth', message, icon_name="blueman").show()

        device.pair(error_handler=error_handler)

    @staticmethod
    def adapter_properties() -> None:
        launch("blueman-adapters", name=_("Adapter Preferences"))

    @staticmethod
    def toggle_trust(device: Device) -> None:
        device['Trusted'] = not device['Trusted']

    @staticmethod
    def toggle_blocked(device: Device) -> None:
        device['Blocked'] = not device['Blocked']

    @staticmethod
    def _sendto_command(adapter: Adapter, device: Device) -> str:
        command = ["blueman-sendto"]

        if logging.getLogger().isEnabledFor(logging.DEBUG):
            command.extend(["--loglevel", "DEBUG"])

        command.extend([
            f"--source={adapter['Address']}",
            f"--device={device['Address']}",
        ])

        return " ".join(command)

    def _launch_sendto(self, adapter: Adapter, device: Device) -> None:
        command = Blueman._sendto_command(adapter, device)
        logging.info("Launching file sender for %s via %s", device["Address"], adapter["Address"])
        logging.debug("File sender command: %s", command)
        launch(command, name=_("File Sender"))

    def send(self, device: Device) -> None:
        adapter = self.List.Adapter
        assert adapter

        self._launch_sendto(adapter, device)

    def remove(self, device: Device) -> None:
        assert self.List.Adapter
        self.List.Adapter.remove_device(device)
