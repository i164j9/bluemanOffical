from importlib import import_module
import logging
import os
import signal
import sys
from typing import Any, cast
from blueman.Functions import log_system_info
from blueman.main.DBusProxies import AppletMenuService, AppletStatusIconService
from gi.repository import Gio, GLib, GLibUnix

from blueman.main.indicators.IndicatorInterface import IndicatorNotAvailable


NO_APPLICATION_FLAGS = cast(Gio.ApplicationFlags, 0)
NO_BUS_NAME_WATCHER_FLAGS = cast(Gio.BusNameWatcherFlags, 0)


class BluemanTray(Gio.Application):
    indicator: Any

    def __init__(self) -> None:
        super().__init__(application_id="org.blueman.Tray", flags=NO_APPLICATION_FLAGS)
        self._active = False
        self.connect("shutdown", lambda *_args: self._destroy_indicator())

        def do_quit(_: object) -> bool:
            self.quit()
            return False

        log_system_info()

        s = GLibUnix.signal_source_new(signal.SIGINT)
        s.set_callback(do_quit)
        s.attach()

    def do_activate(self) -> None:
        if self._active:
            GLib.timeout_add_seconds(1, lambda: os.execv(sys.argv[0], sys.argv))
            logging.info("Already running, restarting instance")
            return

        Gio.bus_watch_name(Gio.BusType.SESSION, 'org.blueman.Applet', NO_BUS_NAME_WATCHER_FLAGS,
                           self._on_name_appeared, self._on_name_vanished)
        self.hold()

    def _destroy_indicator(self) -> None:
        indicator = getattr(self, "indicator", None)
        if indicator is not None:
            indicator.destroy()
            self.indicator = None
        self._active = False

    def _on_name_appeared(self, _connection: Gio.DBusConnection, name: str, _owner: str) -> None:
        logging.debug("Applet started on name %s, showing indicator", name)

        trayicon_service = AppletStatusIconService()
        menu_service = AppletMenuService()
        for indicator_name in menu_service.get_statusicon_implementations():
            indicator_class = getattr(import_module('blueman.main.indicators.' + indicator_name), indicator_name)
            try:
                self.indicator = indicator_class(self, menu_service.get_icon_name())
                break
            except IndicatorNotAvailable:
                logging.info('Indicator "%s" is not available', indicator_name)
        logging.info('Using indicator "%s"', self.indicator.__class__.__name__)

        menu_service.connect('g-signal', self.on_signal)
        trayicon_service.connect('g-signal', self.on_signal)

        self.indicator.set_tooltip_title(menu_service.get_tooltip_title())
        self.indicator.set_tooltip_text(menu_service.get_tooltip_text())
        self.indicator.set_visibility(menu_service.get_visibility())
        self.indicator.set_menu(menu_service.get_menu())

        self._active = True

    def _on_name_vanished(self, _connection: Gio.DBusConnection, _name: str) -> None:
        logging.debug("Applet shutdown or not available at startup")
        self._destroy_indicator()
        self.quit()


    def activate_menu_item(self, *indexes: int) -> None:
        AppletMenuService().ActivateMenuItem('(ai)', indexes)

    def activate_status_icon(self) -> None:
        AppletMenuService().Activate()

    def on_signal(self, _applet: AppletMenuService | AppletStatusIconService, _sender_name: str, signal_name: str,
                  vargs: GLib.Variant) -> None:
        logging.debug("%s", signal_name)
        args = vargs.unpack()
        if signal_name == 'IconNameChanged':
            self.indicator.set_icon(*args)
        elif signal_name == 'ToolTipTitleChanged':
            self.indicator.set_tooltip_title(*args)
        elif signal_name == 'ToolTipTextChanged':
            self.indicator.set_tooltip_text(*args)
        elif signal_name == 'VisibilityChanged':
            self.indicator.set_visibility(*args)
        elif signal_name == 'MenuChanged':
            self.indicator.set_menu(*args)
