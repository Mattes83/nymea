"""Support for Maveo stick."""

from __future__ import annotations

import logging
from enum import Enum
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
        self.state: State = State.closed
        
        # Register for state change notifications.
        self._register_for_notifications()

    def _register_for_notifications(self) -> None:
        """Register to receive state change notifications for this thing."""
        # Register handler for Integrations.StateChanged notifications.
        self.maveoBox.register_notification_handler(
            "Integrations.StateChanged", 
            self._handle_state_changed
        )

    def _handle_state_changed(self, params: dict[str, Any]) -> None:
        """Handle state change notification from Nymea."""
        # Check if this notification is for this specific thing.
        thing_id = params.get("thingId")
        if thing_id != self._id:
            return
            
        # Get the state type and value.
        state_type_id = params.get("stateTypeId")
        value = params.get("value")
        
        # We only care about the "State" state type (need to check if it's the right one)
        # For now, update the state if we get any state change for this thing
        try:
            if value in State.__members__:
                old_state = self.state
                self.state = State[value]
                if old_state != self.state:
                    # This is logging, so use % formatting.
                    _LOGGER.info(
                        "MaveoStick %s state changed from %s to %s (via notification)",
                        self.name,
                        old_state.name,
                        self.state.name
                    )
                    # Publish updates to Home Assistant.
                    self.maveoBox._hass.loop.call_soon_threadsafe(
                        self.maveoBox._hass.async_create_task,
                        self.publish_updates()
                    )
        except Exception as ex:
            # This is logging, so use % formatting.
            _LOGGER.error("Error handling state change notification: %s", ex)

    def unregister_notifications(self) -> None:
        """Unregister from state change notifications."""
        self.maveoBox.unregister_notification_handler(
            "Integrations.StateChanged",
            self._handle_state_changed
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
        """Add all maveo sticks connected to the maveo box."""
        params: dict[str, str] = {}
        params["thingClassId"] = MaveoStick.thingclassid
        things: list[dict[str, Any]] = maveoBox.send_command("Integrations.GetConfiguredThings", params)[  # type: ignore[index]
            "params"
        ]["things"]

    def unregister_notifications(self):
        """Unregister from state change notifications."""
        self.maveoBox.unregister_notification_handler(
            "Integrations.StateChanged",
            self._handle_state_changed
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
