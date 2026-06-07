import pathlib
import logging
import importlib
import signal
from typing import cast

from blueman.Functions import plugin_names

from blueman.main.Builder import Builder
from blueman.Functions import log_system_info
import blueman.plugins.services
from blueman.plugins.ServicePlugin import ServicePlugin

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from gi.repository import GLibUnix
from gi.repository import Gio


NO_SETTINGS_BIND_FLAGS = cast(Gio.SettingsBindFlags, 0)


class BluemanServices(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id="org.blueman.Services")
        self.window: Gtk.Window | None = None
        self.builder = Builder("services-window.ui")
        self.Config = Gio.Settings(schema_id="org.blueman.general")
        self.notebook: Gtk.Notebook
        self.b_apply: Gtk.Button

        def do_quit(_: object) -> bool:
            self.quit()
            return False

        log_system_info()

        s = GLibUnix.signal_source_new(signal.SIGINT)
        s.set_callback(do_quit)
        s.attach()

        close_action = Gio.SimpleAction.new("quit", None)
        close_action.connect("activate", lambda x, y: self.quit())
        self.add_action(close_action)

    def do_activate(self) -> None:
        if not self.window:
            self.window = self.builder.get_widget("window", Gtk.ApplicationWindow)
            self.window.set_application(self)
            self.notebook = self.builder.get_widget("notebook", Gtk.Notebook)
            self.b_apply = self.builder.get_widget("apply", Gtk.Button)
            self.b_apply.connect("clicked", self.on_apply_clicked)

            self.load_plugins()

            self.Config.bind("services-last-item", self.notebook, "page", NO_SETTINGS_BIND_FLAGS)

        self.window.present_with_time(Gtk.get_current_event_time())

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        self.set_accels_for_action("app.quit", ["<Ctrl>w", "<Ctrl>q", "Escape"])

    def option_changed(self) -> None:
        rets = [plugin.on_query_apply_state() for plugin in ServicePlugin.instances]
        show_apply = False
        for ret in rets:
            if ret == -1:
                show_apply = False
                break
            assert isinstance(ret, bool)
            show_apply = show_apply or ret

        self.b_apply.props.sensitive = show_apply

    def load_plugins(self) -> None:
        path = pathlib.Path(blueman.plugins.services.__file__)
        plugins = plugin_names(path)

        plugins.sort()
        logging.info(plugins)
        for plugin in plugins:
            try:
                importlib.import_module(f"blueman.plugins.services.{plugin}")
            except ImportError:
                logging.error("Unable to load %s plugin", plugin, exc_info=True)

        for cls in ServicePlugin.__subclasses__():
            inst = cls(self)
            if not cls.__plugin_info__:
                logging.warning("Invalid plugin info in %s", cls)
            else:
                (name, icon) = cls.__plugin_info__
                inst.on_load()
                self.add_page(inst, name, icon)

    def add_page(self, inst: ServicePlugin, name: str, icon_name: str) -> None:
        box = Gtk.Box(vexpand=True, visible=True, spacing=6)
        label = Gtk.Label(label=name, visible=True)
        icon = Gtk.Image(icon_name=icon_name, visible=True)
        box.add(icon)
        box.add(label)
        self.notebook.append_page(inst.widget, box)

    def on_apply_clicked(self, _button: Gtk.Button) -> None:
        for plugin in ServicePlugin.instances:
            plugin.on_apply()
        self.option_changed()
