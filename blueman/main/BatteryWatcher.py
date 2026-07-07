import weakref
from collections.abc import Callable
from blueman.bluemantyping import ObjectPath

from blueman.bluez.Battery import Battery, AnyBattery
from blueman.bluez.Manager import Manager


class BatteryWatcher:
    def __init__(self, callback: Callable[[ObjectPath, int], None]) -> None:
        super().__init__()
        manager = Manager()
        manager_handler_id = manager.connect_signal(
            "battery-created",
            lambda _manager, obj_path: callback(obj_path, Battery(obj_path=obj_path)["Percentage"])
        )

        any_battery = AnyBattery()
        battery_handler_id = any_battery.connect_signal(
            "property-changed",
            lambda _any_battery, key, value, path: callback(path, value) if key == "Percentage" else None
        )

        self._finalizer = weakref.finalize(
            self,
            self._disconnect_signals,
            manager,
            manager_handler_id,
            any_battery,
            battery_handler_id,
        )

    @staticmethod
    def _disconnect_signals(
        manager: Manager,
        manager_handler_id: int,
        any_battery: AnyBattery,
        battery_handler_id: int,
    ) -> None:
        manager.disconnect_signal(manager_handler_id)
        any_battery.disconnect_signal(battery_handler_id)

    def destroy(self) -> None:
        if self._finalizer.alive:
            self._finalizer()
