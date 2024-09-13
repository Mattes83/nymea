"""Support for Maveo stick."""

from __future__ import annotations

from enum import Enum

from .maveo_box import MaveoBox

State = Enum(
    "State", ["unknown", "open", "closed", "opening", "closing", "intermediate"]
)


class MaveoStick:
    """Represents a Maveo Stick attached to the garage door drive and connected to the maveo box."""

    manufacturer = "maveo"
    thingclassid = "ca6baab8-3708-4478-8ca2-7d4d6d542937"

    def __init__(
        self,
        thingid: str,
        name: str,
        version: str,
        maveoBox: MaveoBox,
    ) -> None:
        """Init stick."""
        self._id = thingid
        self.name = name
        self.firmware_version = version
        self.maveoBox = maveoBox
        self._callbacks = set()
        self.state = State.closed

    @property
    def id(self) -> str:
        """Return ID for maveo stick."""
        return self._id

    def register_callback(self, callback: Callable[[], None]) -> None:
        """Register callback, called when MaveoStick changes state."""
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
        # things = maveoBox.nymea.get_things(MaveoStick.thingclassid)
        """Add all maveo sticks connected to the maveo box."""
        params = {}
        params["thingClassId"] = MaveoStick.thingclassid
        stateTypes = maveoBox.send_command("Integrations.GetStateTypes", params)[
            "params"
        ]["stateTypes"]

        statetype_version = next(
            (obj for obj in stateTypes if obj["displayName"] == "maveo-stick version"),
            None,
        )

        things = maveoBox.send_command("Integrations.GetThings")["params"]["things"]
        for thing in things:
            if thing["thingClassId"] == MaveoStick.thingclassid:
                version = next(
                    (
                        obj
                        for obj in thing["states"]
                        if obj["stateTypeId"] == statetype_version["id"]
                    ),
                    None,
                )["value"]
                maveoBox.maveoSticks.append(
                    MaveoStick(
                        thing["id"],
                        thing["name"],
                        version,
                        maveoBox,
                    )
                )
