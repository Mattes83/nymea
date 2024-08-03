"""Support for Aqara weather sensor."""

from __future__ import annotations

from .maveo_box import MaveoBox


class AqaraSensor:
    """Represents a Aqara Sensor connected to the maveo box."""

    thingclassid = "0b582616-0b05-4ac9-8b59-51b66079b571"

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
        """Return ID for aqara sensor."""
        return self._id

    def register_callback(self, callback: Callable[[], None]) -> None:
        """Register callback, called when AqaraSensor changes state."""
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
        params["thingClassId"] = AqaraSensor.thingclassid
        stateTypes = maveoBox.send_command("Integrations.GetStateTypes", params)[
            "params"
        ]["stateTypes"]

        statetype_version = next(
            (obj for obj in stateTypes if obj["displayName"] == "Version"),
            None,
        )

        things = maveoBox.send_command("Integrations.GetThings")["params"]["things"]
        for thing in things:
            if thing["thingClassId"] == AqaraSensor.thingclassid:
                version = next(
                    (
                        obj
                        for obj in thing["states"]
                        if obj["stateTypeId"] == statetype_version["id"]
                    ),
                    None,
                )["value"]
                maveoBox.aqaraSensors.append(
                    AqaraSensor(
                        thing["id"],
                        thing["name"],
                        version,
                        maveoBox,
                    )
                )
