from blueman.plugins.manager.Info import format_mapping


class TestInfoFormatting:
    def test_format_mapping_formats_integer_keys_and_byte_values(self) -> None:
        formatted = format_mapping({0x004C: bytes((0x02, 0x15, 0xAA))})

        assert formatted == "0x004c: 02 15 aa"

    def test_format_mapping_formats_string_keys_and_sequence_values(self) -> None:
        formatted = format_mapping({"0000180f-0000-1000-8000-00805f9b34fb": [0x64]})

        assert formatted == "0000180f-0000-1000-8000-00805f9b34fb: 64"