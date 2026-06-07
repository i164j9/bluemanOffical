from types import SimpleNamespace
from unittest.mock import Mock

from blueman.bluez.errors import BluezDBusException
from blueman.bluez.obex.Transfer import Transfer


class TestTransfer:
    def test_name_falls_back_to_filename_when_name_missing(self) -> None:
        fake_transfer = SimpleNamespace(
            get=Mock(side_effect=[BluezDBusException("missing"), "photo.jpg"]),
            filename="photo.jpg",
        )
        get_optional = getattr(Transfer, "_get_optional")
        fake_transfer.__dict__["_get_optional"] = lambda name: get_optional(fake_transfer, name)

        name = getattr(Transfer, "name").__get__(fake_transfer, type(fake_transfer))

        assert name == "photo.jpg"

    def test_size_returns_none_when_property_missing(self) -> None:
        fake_transfer = SimpleNamespace(
            get=Mock(side_effect=BluezDBusException("missing")),
        )
        get_optional = getattr(Transfer, "_get_optional")
        fake_transfer.__dict__["_get_optional"] = lambda name: get_optional(fake_transfer, name)

        size = getattr(Transfer, "size").__get__(fake_transfer, type(fake_transfer))

        assert size is None