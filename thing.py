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
        """Handle state change notification from Nymea."""
        # Check if this notification is for this specific thing.
        thing_id = params.get("thingId")
        if thing_id != self._id:
            return

        # Extract and cache the state value.
        state_type_id = params.get("stateTypeId")
        value = params.get("value")

        if state_type_id and value is not None:
            self._state_cache[state_type_id] = value
            # This is logging, so use % formatting.
            _LOGGER.debug(
                "Thing %s state updated: %s = %s", self.name, state_type_id, value
            )

        # Trigger all registered callbacks to update Home Assistant.
        try:
            self.maveoBox._hass.loop.call_soon_threadsafe(
                self.maveoBox._hass.async_create_task, self.publish_updates()
            )
        except Exception as ex:
            # This is logging, so use % formatting.
            _LOGGER.error("Error handling state change notification for thing: %s", ex)

    def get_state_value(self, state_type_id: str) -> Any:
        """Get cached state value for a specific stateTypeId."""
        return self._state_cache.get(state_type_id)

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
    async def add(maveoBox: MaveoBox):
        """Add all things connected to the maveo box."""
        things = maveoBox.send_command("Integrations.GetThings")["params"]["things"]

        for thing in things:
            params = {}
            params["thingClassIds"] = [thing["thingClassId"]]
            thingClasses = maveoBox.send_command(
                "Integrations.GetThingClasses", params
            )["params"]["thingClasses"]

            vendors = maveoBox.send_command("Integrations.GetVendors")["params"][
                "vendors"
            ]

            vendor = next(x for x in vendors if x["id"] == thingClasses[0]["vendorId"])

            maveoBox.things.append(
                Thing(
                    thing["id"],
                    thing["thingClassId"],
                    vendor["displayName"],
                    thing["name"],
                    maveoBox,
                    thingClasses[0].get("displayName"),
                )
            )
