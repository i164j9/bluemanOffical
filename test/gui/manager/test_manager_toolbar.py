from types import SimpleNamespace

from blueman.gui.manager.ManagerToolbar import ManagerToolbar


class TestManagerToolbar:
    def test_update_buttons_keeps_bluetooth_switch_enabled_without_selection(self) -> None:
        update_buttons = getattr(ManagerToolbar, "_update_buttons")
        toolbar = SimpleNamespace(
            b_search=SimpleNamespace(props=SimpleNamespace(sensitive=None)),
            b_bond=SimpleNamespace(props=SimpleNamespace(sensitive=None, opacity=None)),
            b_trust=SimpleNamespace(props=SimpleNamespace(sensitive=None, icon_name=None, label=None)),
            b_remove=SimpleNamespace(props=SimpleNamespace(sensitive=None, opacity=None)),
            b_send=SimpleNamespace(props=SimpleNamespace(sensitive=None, opacity=None)),
            b_bluetooth_status=SimpleNamespace(props=SimpleNamespace(sensitive=None)),
        )
        bt_status_box = SimpleNamespace(set_visible=lambda visible: setattr(bt_status_box, "visible", visible))
        bt_status_box.visible = None
        toolbar.blueman = SimpleNamespace(
            Applet=SimpleNamespace(QueryPlugins=lambda: ["PowerManager"]),
            builder=SimpleNamespace(get_widget=lambda widget_id, _widget_type: bt_status_box),
            List=SimpleNamespace(selected=lambda: None),
        )

        update_buttons(toolbar, None)

        assert bt_status_box.visible is True
        assert toolbar.b_bluetooth_status.props.sensitive is True