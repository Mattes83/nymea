"""Support for things."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from .maveo_box import MaveoBox

_LOGGER = logging.getLogger(__name__)


class Thing:
    """Represents a thing connected to the maveo box."""

    def __init__(
        self,
        thingid: str,
        thingclassId: str,
        manufacturer: str,
        name: str,
        maveoBox: MaveoBox,
        model: str | None = None,
    ) -> None:
        """Init sensor."""
        self._id: str = thingid
        self.thingclass_id: str = thingclassId
        self.name: str = name
        self.manufacturer: str = manufacturer
        self.model: str | None = model
        self.maveoBox: MaveoBox = maveoBox
        self._callbacks: set[Callable[[], None]] = set()

        # Cache for state values - maps stateTypeId to value.
        self._state_cache: dict[str, Any] = {}

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

        # Extract and cache the state value.
        state_type_id = params.get("stateTypeId")
        if state_type_id:
            self._state_cache[state_type_id] = params.get("value")
            _LOGGER.debug(
                "Thing %s state updated: %s = %s",
                self.name,
                state_type_id,
                params.get("value"),
            )

        # Trigger all registered callbacks to update Home Assistant.
        for callback in list(self._callbacks):
            callback()

    def get_state_value(self, state_type_id: str) -> Any:
        """Get cached state value for a specific stateTypeId."""
        return self._state_cache.get(state_type_id)

    def set_state_value(self, state_type_id: str, value: Any) -> None:
        """Cache a state value for a specific stateTypeId."""
        self._state_cache[state_type_id] = value

    def register_callback(self, callback: Callable[[], None]) -> None:
        """Register callback, called when Thing changes state."""
        self._callbacks.add(callback)

    def remove_callback(self, callback: Callable[[], None]) -> None:
        """Remove previously registered callback."""
        self._callbacks.discard(callback)

    async def publish_updates(self) -> None:
        """Schedule call all registered callbacks."""
        for callback in self._callbacks:
            callback()

    def unregister_notifications(self) -> None:
        """Unregister from state change notifications."""
        self.maveoBox.unregister_notification_handler(
            "Integrations.StateChanged", self._handle_state_changed
        )

    @property
    def id(self) -> str:
        """Return ID for thing."""
        return self._id

    @staticmethod
    async def add(maveoBox: MaveoBox) -> None:
        """Add all things connected to the maveo box from the cached inventory."""
        for raw_thing in maveoBox.raw_things:
            thing_class = maveoBox.get_thing_class(raw_thing["thingClassId"])
            if thing_class is None:
                _LOGGER.warning(
                    "No thing class found for thing '%s' (%s), skipping",
                    raw_thing.get("name"),
                    raw_thing.get("id"),
                )
                continue

            vendor = maveoBox.vendors.get(thing_class.get("vendorId"), {})

            thing = Thing(
                raw_thing["id"],
                raw_thing["thingClassId"],
                vendor.get("displayName", "Unknown"),
                raw_thing["name"],
                maveoBox,
                thing_class.get("displayName"),
            )
            # Prefill the state cache so entities don't need an initial fetch.
            for state in raw_thing.get("states", []):
                thing.set_state_value(state["stateTypeId"], state.get("value"))

            maveoBox.things.append(thing)
