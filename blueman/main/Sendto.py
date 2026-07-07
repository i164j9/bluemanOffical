from gettext import gettext as _
import atexit
import os
import time
import logging
from argparse import Namespace
from gettext import ngettext
from collections.abc import Iterable, Sequence
from typing import Any, cast
import _blueman

from blueman.bluez.Device import Device, AnyDevice
from blueman.bluez.errors import BluezDBusException, DBusNoSuchAdapterError
from blueman.main.Builder import Builder
from blueman.bluemantyping import GSignals, ObjectPath
from blueman.bluez.Adapter import Adapter, AnyAdapter
from blueman.bluez.Manager import Manager
from blueman.bluez.obex.FileTransfer import FileTransfer
from blueman.bluez.obex.ObjectPush import ObjectPush
from blueman.bluez.obex.Manager import Manager as ObexManager
from blueman.bluez.obex.Client import Client
from blueman.bluez.obex.Transfer import Transfer
from blueman.Functions import format_bytes, log_system_info, bmexit, check_bluetooth_status, setup_icon_path, \
    adapter_path_to_name
from blueman.main.SpeedCalc import SpeedCalc
from blueman.gui.CommonUi import ErrorDialog
from blueman.gui.DeviceSelectorDialog import DeviceSelector
from blueman.Sdp import ServiceUUID, OBEX_FILETRANS_SVCLASS_ID, OBEX_OBJPUSH_SVCLASS_ID

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk, GObject, GLib, Gio


NO_FILE_QUERY_INFO_FLAGS = cast(Gio.FileQueryInfoFlags, 0)


def describe_session_attempt(source_addr: str | None, channel: int | None) -> str:
    parts = [f"source {source_addr}" if source_addr is not None else "without Source"]
    if channel is not None:
        parts.append(f"channel {channel}")
    return ", ".join(parts)


def build_session_failure_message(
    error: BluezDBusException,
    attempts: Sequence[tuple[str | None, int | None]],
) -> str:
    reason = error.reason.strip()

    if "Connection refused" in reason:
        message = _(
            "The remote device refused the OBEX file transfer connection. "
            "Make sure Bluetooth file sharing is enabled on the device, it is unlocked, and ready to receive files."
        )
    else:
        parts = reason.split(None, 1)
        if len(parts) == 2 and parts[1]:
            message = parts[1]
        elif reason.startswith("org.bluez.obex.Error."):
            message = _("The OBEX file transfer session could not be established with the remote device.")
        else:
            message = reason or _("The OBEX file transfer session could not be established with the remote device.")

    if attempts:
        attempted = "; ".join(describe_session_attempt(source, channel) for source, channel in attempts)
        message = f"{message}\n\n{_('Tried session variants')}: {attempted}"

    return message


def build_session_failure_title(error: BluezDBusException) -> str:
    if "Connection refused" in error.reason:
        return _("Remote device refused file transfer")
    return _("Error occurred")


class SendTo:
    def __init__(self, parsed_args: Namespace) -> None:
        setup_icon_path()

        check_bluetooth_status(_("Bluetooth needs to be turned on for file sending to work"), bmexit)

        if not parsed_args.files:
            self.files = self.select_files()
        else:
            self.files = [os.path.abspath(f) for f in parsed_args.files]

        logging.info(
            "SendTo starting with source=%s device=%s files=%d",
            parsed_args.source,
            parsed_args.device,
            len(self.files),
        )

        self.device: Device | None = None
        self._manager = manager = Manager()
        self._manager.connect_signal("adapter-added", self.__on_manager_signal, "adapter-added")
        self._manager.connect_signal("adapter-removed", self.__on_manager_signal, "adapter-removed")
        self._manager.connect_signal("device-created", self.__on_manager_signal, "device-added")
        self._manager.connect_signal("device-removed", self.__on_manager_signal, "device-removed")

        self.__any_adapter = AnyAdapter()
        self.__any_adapter.connect_signal("property-changed", self.__on_adapter_property_changed)
        self.__any_device = AnyDevice()
        self.__any_device.connect_signal("property-changed", self.__on_device_property_changed)

        adapter: Adapter | None = None
        adapters = manager.get_adapters()
        last_adapter_name: str | None = Gio.Settings(schema_id="org.blueman.general")["last-adapter"]

        if len(adapters) == 0:
            logging.error("Error: No Adapters present")
            bmexit()

        if parsed_args.source is not None:
            try:
                adapter = manager.get_adapter(parsed_args.source)
            except DBusNoSuchAdapterError:
                logging.error("Unknown adapter, trying first available")

        if adapter is None:
            try:
                adapter = manager.get_adapter(last_adapter_name)
            except DBusNoSuchAdapterError:
                adapter = manager.get_adapter()

        self.adapter_path = adapter.get_object_path()
        adapter_name = adapter_path_to_name(self.adapter_path)
        assert adapter_name is not None

        self._device_selector = DeviceSelector(adapter_name=adapter_name)

        for adapter in adapters:
            self._device_selector.add_adapter(adapter.get_object_path())
        manager.populate_devices()

        if parsed_args.delete:
            def delete_files() -> None:
                for file in self.files:
                    os.unlink(file)
            atexit.register(delete_files)

        if parsed_args.device is None:
            if not self.select_device():
                bmexit()

            self.do_send()
            self.__cleanup()

        else:
            d = manager.find_device(parsed_args.device, self.adapter_path)
            if d is None:
                bmexit("Unknown bluetooth device")

            self.device = d
            self.do_send()
            self.__cleanup()

    def __on_manager_signal(self, _manager: Manager, object_path: ObjectPath, signal_name: str) -> None:
        logging.debug("%s %s", object_path, signal_name)
        match signal_name:
            case "adapter-added":
                self._device_selector.add_adapter(object_path)
                # Let the adapter become ready before we start discovery
                GLib.timeout_add_seconds(1, self._start_discovery, True)
            case "adapter-removed":
                self._device_selector.remove_adapter(object_path)
            case "device-added":
                show_warning = not self._has_objpush(object_path)
                self._device_selector.add_device(object_path, show_warning)
            case "device-removed":
                self._device_selector.remove_device(object_path)
            case _:
                raise ValueError(f"Unhandled signal {signal_name}")

    def __on_adapter_property_changed(self, _: AnyAdapter, key: str, value: Any, _object_path: ObjectPath) -> None:
        if key == "Discovering":
            self._device_selector.set_discovering(value)

    def __on_device_property_changed(self, _: AnyDevice, key: str, value: Any, object_path: ObjectPath) -> None:
        match key:
            case "Alias":
                self._device_selector.update_row(object_path, "description", value)
            case "UUIDs":
                show_warning = not self._has_objpush(object_path)
                self._device_selector.update_row(object_path, "warning", show_warning)

    def _has_objpush(self, object_path: ObjectPath) -> bool:
        device = Device(obj_path=object_path)
        for uuid in device["UUIDs"]:
            if ServiceUUID(uuid).short_uuid == OBEX_OBJPUSH_SVCLASS_ID:
                return True
        return False

    def _start_discovery(self, from_timer: bool = False) -> bool:
        for adapter in self._manager.get_adapters():
            if not adapter["Discovering"]:
                adapter.start_discovery()
        if from_timer:
            return False
        return True

    def __cleanup(self) -> None:
        self._manager.destroy()

        del self.__any_device
        del self.__any_adapter
        del self._manager

    def do_send(self) -> None:
        if not self.files:
            logging.warning("No files to send")
            bmexit()

        assert self.device is not None
        sender = Sender(self.device, self.adapter_path, self.files)

        def on_result(_sender: Sender, _res: bool) -> None:
            Gtk.main_quit()

        sender.connect("result", on_result)

    @staticmethod
    def select_files() -> Sequence[str]:
        logging.info("Opening file chooser for Bluetooth send")
        d = Gtk.FileChooserDialog(title=_("Select files to send"), icon_name='blueman-send-symbolic')
        d.set_select_multiple(True)  # this avoids type error when using keyword arg above
        d.add_buttons(_("_Cancel"), Gtk.ResponseType.REJECT, _("_OK"), Gtk.ResponseType.ACCEPT)
        resp = d.run()

        if resp == Gtk.ResponseType.ACCEPT:
            files = d.get_filenames()
            d.destroy()
            logging.info("Selected %d file(s) for Bluetooth send", len(files))
            return files
        else:
            d.destroy()
            logging.info("Bluetooth send cancelled during file selection")
            quit()

    def select_device(self) -> bool:
        self._start_discovery()
        resp = self._device_selector.run()
        self._device_selector.close()
        if resp == Gtk.ResponseType.ACCEPT:
            if self._device_selector.selection:
                self.adapter_path, self.device = self._device_selector.selection
                return True
            else:
                return False
        else:
            return False


class Sender(Gtk.Dialog):
    __gsignals__: GSignals = {
        'result': (GObject.SignalFlags.RUN_FIRST, None, (GObject.TYPE_BOOLEAN,)),
    }

    def __init__(self, device: Device, adapter_path: ObjectPath, files: Iterable[str]) -> None:
        super().__init__(
            title=_("Bluetooth File Transfer"),
            name="BluemanSendTo",
            icon_name="blueman",
            border_width=5,
            default_width=400,
            window_position=Gtk.WindowPosition.CENTER,
            type_hint=Gdk.WindowTypeHint.DIALOG
        )

        log_system_info()

        self.b_cancel = self.add_button(_("_Stop"), Gtk.ResponseType.CLOSE)
        self.b_cancel.props.receives_default = True
        self.b_cancel.props.use_underline = True
        self.b_cancel.connect("clicked", self.on_cancel)

        builder = Builder("send-dialog.ui")

        grid = builder.get_widget("sendto", Gtk.Grid)
        content_area = self.get_content_area()
        content_area.add(grid)

        self.l_dest = builder.get_widget("l_dest", Gtk.Label)
        self.l_file = builder.get_widget("l_file", Gtk.Label)

        self.pb = builder.get_widget("pb", Gtk.ProgressBar)
        self.pb.props.text = _("Connecting")

        self.device = device
        self._awaiting_device_ready = False
        self._device_handler_id = self.device.connect_signal("property-changed", self._on_device_property_changed)
        self.adapter = Adapter(obj_path=adapter_path)
        self._preferred_session_source_addr: str = self.adapter["Address"]
        self._session_source_addr: str | None = self._preferred_session_source_addr
        self._session_channel: int | None = None
        self._session_target = "opp"
        self._session_attempts: list[tuple[str | None, int | None, str]] = [(self._session_source_addr, None, "opp")]
        self._session_attempt_index = 0
        self._session_retry_source_id: int | None = None
        self.obex_manager = ObexManager()
        self.files: list[Gio.File] = []
        self.num_files = 0
        self.object_push: ObjectPush | FileTransfer | None = None
        self.object_push_handlers: list[int] = []
        self.transfer: Transfer | None = None

        self.total_bytes = 0
        self.total_transferred = 0

        self._last_bytes = 0
        self._last_update = 0.0

        self.error_dialog: ErrorDialog | None = None
        self.cancelling = False

        # bytes transferred on a current transfer
        self.transferred = 0

        self.speed = SpeedCalc(6)

        for file_name in files:
            parsed_file = Gio.File.parse_name(file_name)

            if not parsed_file.query_exists():
                logging.info("Skipping non existing file %s", parsed_file.get_path())
                continue

            file_info = parsed_file.query_info("standard::*", NO_FILE_QUERY_INFO_FLAGS)

            if file_info.get_file_type() == Gio.FileType.DIRECTORY:
                logging.info("Skipping directory %s", parsed_file.get_path())
                continue

            self.files.append(parsed_file)
            self.num_files += 1
            self.total_bytes += file_info.get_size()

        if len(self.files) == 0:
            self.emit("result", False)

        try:
            self.client = Client()
            self.obex_manager.connect_signal('session-added', self.on_session_added)
            self.obex_manager.connect_signal('session-removed', self.on_session_removed)
        except GLib.Error as e:
            message = str(e)
            if 'StartServiceByName' in message:
                logging.debug("%s", message)
                parent = self.get_toplevel()
                assert isinstance(parent, Gtk.Container)
                d = ErrorDialog(_("obexd not available"), _("Failed to autostart obex service. Make sure the obex "
                                                            "daemon is running"), parent=parent)
                d.run()
                d.destroy()
                self.emit("result", False)
            else:
                # Fail on anything else
                raise

        basename = self.files[-1].get_basename()
        assert basename is not None
        self.l_file.props.label = basename

        self.client.connect('session-failed', self.on_session_failed)

        logging.info("Sending to %s", device['Address'])
        self.l_dest.props.label = device.display_name

        self.show()

        # Stop discovery if discovering and let adapter settle for a second
        if self.adapter["Discovering"]:
            self.adapter.stop_discovery()
            GLib.timeout_add_seconds(1, self._start_send_session_after_discovery)
        else:
            self._start_send_session()

    def _start_send_session_after_discovery(self) -> bool:
        self._start_send_session()
        return False

    def _services_resolved(self) -> bool:
        try:
            return bool(self.device["ServicesResolved"])
        except BluezDBusException:
            return bool(self.device["Connected"])

    def _device_ready_for_transfer(self) -> bool:
        return bool(self.device["Connected"]) and self._services_resolved()

    def _start_send_session(self) -> None:
        if self._device_ready_for_transfer():
            self._awaiting_device_ready = False
            self.create_session()
            return

        self._awaiting_device_ready = True
        self.pb.props.text = _("Preparing")

        if not self.device["Connected"]:
            self.device.connect(error_handler=self.on_device_connect_failed)

    def _on_device_property_changed(self, _device: Device, key: str, _value: Any, _path: ObjectPath) -> None:
        if not self._awaiting_device_ready:
            return

        if key in ("Connected", "ServicesResolved") and self._device_ready_for_transfer():
            self._awaiting_device_ready = False
            self.pb.props.text = _("Connecting")
            self.create_session()

    def on_device_connect_failed(self, error: BluezDBusException) -> None:
        self._awaiting_device_ready = False

        parent = self.get_toplevel()
        assert isinstance(parent, Gtk.Container)
        d = ErrorDialog(_("Error occurred"), str(error), icon_name="blueman", parent=parent)
        d.run()
        d.destroy()
        self.emit("result", False)

    def _clear_session_retry(self) -> None:
        if self._session_retry_source_id is not None:
            GLib.source_remove(self._session_retry_source_id)
            self._session_retry_source_id = None

    def _schedule_session_retry(self) -> None:
        self._clear_session_retry()
        self.pb.props.text = _("Connecting")

        def retry() -> bool:
            self._session_retry_source_id = None
            self.create_session()
            return False

        self._session_retry_source_id = GLib.timeout_add_seconds(1, retry)

    def create_session(self) -> None:
        self._session_source_addr, self._session_channel, self._session_target = self._session_attempts[
            self._session_attempt_index
        ]
        self.client.create_session(
            self.device['Address'],
            self._session_source_addr,
            pattern=self._session_target,
            channel=self._session_channel,
        )

    def _ensure_session_fallbacks(self) -> None:
        if len(self._session_attempts) > 1:
            return

        attempts: list[tuple[str | None, int | None, str]] = [
            (self._preferred_session_source_addr, None, "opp"),
            (None, None, "opp"),
        ]

        opp_channel = _blueman.get_rfcomm_channel(OBEX_OBJPUSH_SVCLASS_ID, self.device["Address"])
        if opp_channel is not None:
            attempts.extend([
                (self._preferred_session_source_addr, opp_channel, "opp"),
                (None, opp_channel, "opp"),
            ])

        if any(ServiceUUID(uuid).short_uuid == OBEX_FILETRANS_SVCLASS_ID for uuid in self.device["UUIDs"]):
            attempts.extend([
                (self._preferred_session_source_addr, None, "ftp"),
                (None, None, "ftp"),
            ])

            ftp_channel = _blueman.get_rfcomm_channel(OBEX_FILETRANS_SVCLASS_ID, self.device["Address"])
            if ftp_channel is not None:
                attempts.extend([
                    (self._preferred_session_source_addr, ftp_channel, "ftp"),
                    (None, ftp_channel, "ftp"),
                ])

        self._session_attempts = attempts

    def _clear_object_push(self, session_path: ObjectPath | None = None) -> bool:
        if self.object_push is None:
            return False

        current_session_path = self.object_push.get_session_path()
        if session_path is not None and current_session_path != session_path:
            return False

        for handlerid in self.object_push_handlers:
            self.object_push.disconnect(handlerid)

        self.object_push_handlers = []
        self.object_push = None
        return True

    def _reset_transfer_state(self) -> None:
        if self.transferred:
            self.total_transferred = max(0, self.total_transferred - self.transferred)

        self.transfer = None
        self.transferred = 0
        self._last_bytes = 0
        self.speed.reset()

    def on_cancel(self, button: Gtk.Button | None) -> None:
        self.cancelling = True
        self._clear_session_retry()
        self._awaiting_device_ready = False
        self.pb.props.text = _("Cancelling")
        if button:
            button.props.sensitive = False

        if self.object_push:
            self.client.remove_session(self.object_push.get_session_path())

        self.emit("result", False)

    def _update_pb_text(self, speed: float = 0.0, unit: str = "B", eta: str | None = None) -> None:
        num = self.num_files - len(self.files) + 1
        eta = "∞" if eta is None else eta
        text = "%s %d/%d %.2f (%s/s) %s %s" % (_("Sending File"), num, self.num_files, speed, unit, _("ETA:"), eta)
        self.pb.set_text(text)

    def on_transfer_started(self, _object_push: ObjectPush, transfer_path: ObjectPath, filename: str) -> None:
        if self.total_transferred == 0:
            self._update_pb_text(0.0, "B")

        self.l_file.props.label = filename
        self._last_bytes = 0
        self.transferred = 0

        self.transfer = Transfer(obj_path=transfer_path)
        self.transfer.connect("error", self.on_transfer_error)
        self.transfer.connect("progress", self.on_transfer_progress)
        self.transfer.connect("completed", self.on_transfer_completed)

    def on_transfer_failed(self, _object_push: ObjectPush, error: str) -> None:
        self.on_transfer_error(None, str(error))

    def on_transfer_progress(self, _transfer: Transfer, progress: int) -> None:
        self.transferred = progress
        if self._last_bytes == 0:
            self.total_transferred += progress
        else:
            self.total_transferred += (progress - self._last_bytes)

        self._last_bytes = progress

        tm = time.time()
        if tm - self._last_update > 0.5:
            spd = self.speed.calc(self.total_transferred)
            (size, units) = format_bytes(spd)
            try:
                x = ((self.total_bytes - self.total_transferred) / spd) + 1
                if x > 60:
                    x /= 60
                    eta = ngettext("%(minutes)d Minute", "%(minutes)d Minutes", round(x)) % {"minutes": round(x)}
                else:
                    eta = ngettext("%(seconds)d Second", "%(seconds)d Seconds", round(x)) % {"seconds": round(x)}
            except ZeroDivisionError:
                eta = None

            self._update_pb_text(size, units, eta)
            self._last_update = tm

        self.pb.props.fraction = float(self.total_transferred) / self.total_bytes

    def on_transfer_completed(self, _transfer: Transfer) -> None:
        del self.files[-1]
        self.transfer = None
        self.transferred = 0
        self._last_bytes = 0

        self.process_queue()

    def process_queue(self) -> None:
        if len(self.files) > 0:
            path = self.files[-1].get_path()
            assert path is not None
            self.send_file(path)
        else:
            self.emit("result", True)

    def send_file(self, file_path: str) -> None:
        logging.info(file_path)
        if self.object_push:
            self.object_push.send_file(file_path)

    def on_transfer_error(self, _transfer: Transfer | None, msg: str = "") -> None:
        if not self.error_dialog:
            self.speed.reset()
            parent = self.get_toplevel()
            assert isinstance(parent, Gtk.Container)
            d = ErrorDialog(msg, _("Error occurred while sending file %s") % self.files[-1].get_basename(),
                            modal=True, icon_name="blueman", parent=parent, buttons=Gtk.ButtonsType.NONE)

            if len(self.files) > 1:
                d.add_button(_("Skip"), Gtk.ResponseType.NO)
            d.add_button(_("Retry"), Gtk.ResponseType.YES)
            d.add_button(_("_Cancel"), Gtk.ResponseType.CANCEL)

            if self.object_push:
                self.client.remove_session(self.object_push.get_object_path())

            def on_response(dialog: Gtk.Dialog, resp: int) -> None:
                dialog.destroy()
                self.error_dialog = None

                if resp == Gtk.ResponseType.CANCEL:
                    self.on_cancel(None)
                elif resp == Gtk.ResponseType.NO:
                    finfo = self.files[-1].query_info('standard::*', NO_FILE_QUERY_INFO_FLAGS)
                    self.total_bytes -= finfo.get_size()
                    self.total_transferred -= self.transferred
                    self.transferred = 0
                    del self.files[-1]
                    if not self.object_push:
                        self.create_session()
                    self.process_queue()
                elif resp == Gtk.ResponseType.YES:
                    self.total_transferred -= self.transferred
                    self.transferred = 0
                    if not self.object_push:
                        self.create_session()

                    self.process_queue()
                else:
                    self.on_cancel(None)

            d.connect("response", on_response)
            d.show()
            self.error_dialog = d

    def on_session_added(self, _manager: ObexManager, session_path: ObjectPath) -> None:
        self._clear_session_retry()
        self._clear_object_push()
        if self._session_target == "ftp":
            self.object_push = FileTransfer(obj_path=session_path)
        else:
            self.object_push = ObjectPush(obj_path=session_path)
        self.object_push_handlers.append(self.object_push.connect("transfer-started", self.on_transfer_started))
        self.object_push_handlers.append(self.object_push.connect("transfer-failed", self.on_transfer_failed))
        self.process_queue()

    def on_session_removed(self, _manager: ObexManager, session_path: ObjectPath) -> None:
        logging.debug("Session removed: %s", session_path)
        if not self._clear_object_push(session_path):
            return

        self._reset_transfer_state()

        if self.cancelling or self.error_dialog is not None or not self.files:
            return

        self.pb.props.text = _("Connecting")
        self.create_session()

    def on_session_failed(self, _client: Client, msg: BluezDBusException) -> None:
        self._ensure_session_fallbacks()

        if self._session_attempt_index + 1 < len(self._session_attempts):
            current_source, current_channel, current_target = self._session_attempts[self._session_attempt_index]
            self._session_attempt_index += 1
            next_source, next_channel, next_target = self._session_attempts[self._session_attempt_index]

            logging.warning(
                "CreateSession failed with source %s channel %s target %s, retrying with source %s channel %s target %s: %s",
                current_source,
                current_channel,
                current_target,
                next_source,
                next_channel,
                next_target,
                msg,
            )
            self._schedule_session_retry()
            return

        parent = self.get_toplevel()
        assert isinstance(parent, Gtk.Container)
        attempted_variants = [(source, channel) for source, channel, _target in self._session_attempts[:self._session_attempt_index + 1]]
        d = ErrorDialog(
            build_session_failure_title(msg),
            build_session_failure_message(msg, attempted_variants),
            icon_name="blueman",
            parent=parent,
        )

        d.run()
        d.destroy()
        self.emit("result", False)
