"""Support for nymea cover entities."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

if TYPE_CHECKING:
    from .maveo_stick import MaveoStick

from .maveo_stick import State

_LOGGER = logging.getLogger(__name__)


# This function is called as part of the __init__.async_setup_entry (via the
# hass.config_entries.async_forward_entry_setup call).
async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add cover entities for passed config_entry in HA.

    Args:
        hass: Home Assistant instance.
        config_entry: Config entry for this integration.
        async_add_entities: Callback to add entities to HA.
    """
    # The maveoBox is loaded from the config entry's runtime_data.
    maveoBox = config_entry.runtime_data

    # Add all entities to HA.
    async_add_entities(GarageDoor(stick) for stick in maveoBox.maveoSticks)


class GarageDoor(CoverEntity):
    """Representation of a GarageDoor."""

    device_class = CoverDeviceClass.GARAGE
    has_entity_name = True

    # Polling disabled - using push notifications
    should_poll = False
    supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE

    def __init__(self, maveoStick: MaveoStick) -> None:
        """Initialize the garage door."""
        # Usual setup is done here. Callbacks are added in async_added_to_hass.
        self._maveoStick: MaveoStick = maveoStick
        self._attr_unique_id: str = f"{self._maveoStick.id}_cover"

        # This is the name for this *entity*, the "name" attribute from "device_info"
        # is used as the device name for device screens in the UI. This name is used on
        # entity screens, and used to build the Entity ID that's used is automations etc.
        self._attr_name: str = self._maveoStick.name

        # Look up state/action types from the cached inventory (no network I/O).
        thing_class = maveoStick.maveoBox.get_thing_class(maveoStick.thingclassid)
        state_types: list[dict[str, Any]] = (
            thing_class.get("stateTypes", []) if thing_class else []
        )
        statetype_state: dict[str, Any] | None = next(
            (obj for obj in state_types if obj["displayName"] == "State"),
            None,
        )
        self._state_type_id: str | None = (
            statetype_state["id"] if statetype_state else None
        )
        self._action_type_ids: dict[str, str] = {
            at["displayName"]: at["id"]
            for at in (thing_class.get("actionTypes", []) if thing_class else [])
            if "displayName" in at and "id" in at
        }
        self._available: bool = True

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        # Fetch initial state before notifications start
        await self.async_update()

        # Register callback for push notifications
        self._maveoStick.register_callback(self.async_write_ha_state)

    async def async_update(self) -> None:
        """Fetch initial state (called once before notification listener starts)."""
        if self._state_type_id is None:
            _LOGGER.error(
                "No 'State' state type found for %s", self._maveoStick.id
            )
            self._available = False
            return
        params: dict[str, str] = {
            "thingId": self._maveoStick.id,
            "stateTypeId": self._state_type_id,
        }
        try:
            response = await self._maveoStick.maveoBox.async_send_command(
                "Integrations.GetStateValue", params
            )
            if response is None:
                self._available = False
                return
            value: str = response["params"]["value"]
            self._maveoStick.state = (
                State[value] if value in State.__members__ else State.unknown
            )
            self._available = True
        except Exception as ex:
            self._available = False
            _LOGGER.error(
                "Error fetching initial state for %s: %s", self._maveoStick.id, ex
            )

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        # The opposite of async_added_to_hass. Remove any registered call backs here.
        self._maveoStick.remove_callback(self.async_write_ha_state)

    @property
    def device_info(self) -> DeviceInfo:
        """Information about this entity/device."""
        return {
            "identifiers": {(DOMAIN, self._maveoStick.id)},
            "name": "maveo Stick",
            "model": "maveo Stick",
            "sw_version": self._maveoStick.firmware_version,
            "manufacturer": "Marantec",
        }

    @property
    def is_closed(self) -> bool | None:
        """Return if the cover is closed, or None if unknown."""
        if self._maveoStick.state == State.unknown:
            return None
        return self._maveoStick.state == State.closed

    @property
    def is_closing(self) -> bool:
        """Return if the cover is closing or not."""
        return self._maveoStick.state == State.closing

    @property
    def is_opening(self) -> bool:
        """Return if the cover is opening or not."""
        return self._maveoStick.state == State.opening

    @property
    def available(self) -> bool:
        """Return the state of the sensor."""
        return self._available

    async def _async_execute_action(
        self, action_name: str, transition_state: State
    ) -> None:
        """Execute a named action and set the optimistic transition state."""
        action_type_id = self._action_type_ids.get(action_name)
        if action_type_id is None:
            _LOGGER.error(
                "No '%s' action found for %s", action_name, self._maveoStick.id
            )
            return

        params = {"actionTypeId": action_type_id, "thingId": self._maveoStick.id}
        result = await self._maveoStick.maveoBox.async_send_command(
            "Integrations.ExecuteAction", params
        )
        if result is None:
            _LOGGER.error(
                "Failed to execute '%s' for %s", action_name, self._maveoStick.id
            )
            return

        self._maveoStick.state = transition_state
        await self._maveoStick.publish_updates()

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        await self._async_execute_action("Open", State.opening)

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        await self._async_execute_action("Close", State.closing)
