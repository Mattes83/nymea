"""SUpport for Maveo sensor."""

from __future__ import annotations
from typing import Callable

from .maveo_box import MaveoBox


class MaveoSensor:
    """Represents a Maveo Sensor connected to the maveo box."""

    thingclassid = "db7bd8f7-3d12-4ed4-a7c7-fa022bd3701c"

    def __init__(
        self,
        thingid: str,
        name: str,
        version: str,
        maveoBox: MaveoBox,
    ) -> None:
        """Init sensor."""
        self._id = thingid
        self.name = name
        self.firmware_version = version
        self.maveoBox = maveoBox
        self._callbacks = set()

    @property
    def id(self) -> str:
        """Return ID for maveo sensor."""
        return self._id

    def register_callback(self, callback: Callable[[], None]) -> None:
        """Register callback, called when MaveoSensor changes state."""
        self._callbacks.add(callback)

    def remove_callback(self, callback: Callable[[], None]) -> None:
        """Remove previously registered callback."""
        self._callbacks.discard(callback)

    async def publish_updates(self) -> None:
        """Schedule call all registered callbacks."""
        for callback in self._callbacks:
            callback()

    @staticmethod
    async def add(maveoBox: MaveoBox):
        """Add all maveo sensors connected to the maveo box."""
        params = {}
        params["thingClassId"] = MaveoSensor.thingclassid
        stateTypes = maveoBox.send_command("Integrations.GetStateTypes", params)[
            "params"
        ]["stateTypes"]

        statetype_version = next(
            (obj for obj in stateTypes if obj["displayName"] == "Firmware version"),
            None,
        )

        things = maveoBox.send_command("Integrations.GetThings")["params"]["things"]
        for thing in things:
            if thing["thingClassId"] == MaveoSensor.thingclassid:
                version = next(
                    (
                        obj
                        for obj in thing["states"]
                        if obj["stateTypeId"] == statetype_version["id"]
                    ),
                    None,
                )["value"]
                maveoBox.maveoSensors.append(
                    MaveoSensor(
                        thing["id"],
                        thing["name"],
                        version,
                        maveoBox,
                    )
                )
