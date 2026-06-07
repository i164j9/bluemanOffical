from blueman.main.Adapter import discoverable_timeout_to_minutes, get_adapter_service_vanished_dialog_text


class TestAdapterHelpers:
    def test_discoverable_timeout_to_minutes_converts_seconds(self) -> None:
        assert discoverable_timeout_to_minutes(180) == 3
        assert discoverable_timeout_to_minutes(0) == 0

    def test_adapter_service_vanished_dialog_text_is_user_facing(self) -> None:
        primary, secondary = get_adapter_service_vanished_dialog_text()

        assert "Bluetooth adapter manager" in primary
        assert "will now close" in secondary