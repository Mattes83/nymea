"""Support for Maveo stick."""

from __future__ import annotations

from enum import Enum
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from .maveo_box import MaveoBox

_LOGGER = logging.getLogger(__name__)

State = Enum(
    "State", ["unknown", "open", "closed", "opening", "closing", "intermediate"]
)


class MaveoStick:
    """Represents a Maveo Stick attached to the garage door drive and connected to the maveo box."""

    manufacturer: str = "maveo"
    thingclassid: str = "ca6baab8-3708-4478-8ca2-7d4d6d542937"

    def __init__(
        self,
        thingid: str,
        name: str,
        version: str,
        maveoBox: MaveoBox,
    ) -> None:
        """Init stick."""
        self._id: str = thingid
        self.name: str = name
        self.firmware_version: str = version
        self.maveoBox: MaveoBox = maveoBox
        self._callbacks: set[Callable[[], None]] = set()
        self.state: State = State.unknown

        # Register for state change notifications.
        self._register_for_notifications()

    def _register_for_notifications(self) -> None:
        """Register to receive state change notifications for this thing."""
        # Register handler for Integrations.StateChanged notifications.
        self.maveoBox.register_notification_handler(
            "Integrations.StateChanged", self._handle_state_changed
        )

    def _handle_state_changed(self, params: dict[str, Any]) -> None:
        """Handle state change notification from Nymea (runs in the event loop)."""
        # Check if this notification is for this specific thing.
        thing_id = params.get("thingId")
        if thing_id != self._id:
            return

        # Get the value.
        value = params.get("value")

        # We only care about values matching the garage door State enum.
        if value not in State.__members__:
            return

        old_state = self.state
        self.state = State[value]
        if old_state != self.state:
            _LOGGER.info(
                "Garage door '%s': state changed %s -> %s (via WebSocket)",
                self.name,
                old_state.name,
                self.state.name,
            )
            for callback in list(self._callbacks):
                callback()

    def unregister_notifications(self) -> None:
        """Unregister from state change notifications."""
        self.maveoBox.unregister_notification_handler(
            "Integrations.StateChanged", self._handle_state_changed
        )

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
    async def add(maveoBox: MaveoBox) -> None:
        """Add all maveo sticks connected to the maveo box from the cached inventory."""
        thing_class = maveoBox.get_thing_class(MaveoStick.thingclassid)
        if thing_class is None:
            return

        state_types = thing_class.get("stateTypes", [])
        statetype_version = next(
            (st for st in state_types if st["displayName"] == "maveo-stick version"),
            None,
        )
        statetype_state = next(
            (st for st in state_types if st["displayName"] == "State"),
            None,
        )

        def _state_value(raw_thing: dict[str, Any], state_type: dict[str, Any] | None) -> Any:
            if state_type is None:
                return None
            return next(
                (
                    s.get("value")
                    for s in raw_thing.get("states", [])
                    if s["stateTypeId"] == state_type["id"]
                ),
                None,
            )

        for raw_thing in maveoBox.raw_things:
            if raw_thing["thingClassId"] != MaveoStick.thingclassid:
                continue

            version = _state_value(raw_thing, statetype_version) or "unknown"
            stick = MaveoStick(
                raw_thing["id"],
                raw_thing["name"],
                version,
                maveoBox,
            )
            initial_state = _state_value(raw_thing, statetype_state)
            if initial_state in State.__members__:
                stick.state = State[initial_state]

            maveoBox.maveoSticks.append(stick)
