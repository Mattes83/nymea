"""Platform for sensor integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

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
from .maveo_stick import MaveoStick, State

SCAN_INTERVAL = timedelta(seconds=5)


# This function is called as part of the __init__.async_setup_entry (via the
# hass.config_entries.async_forward_entry_setup call)
async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add cover for passed config_entry in HA."""
    # The maveoBox is loaded from the associated hass.data entry that was created in the
    # __init__.async_setup_entry function
    maveoBox = hass.data[DOMAIN][config_entry.entry_id]

    # Add all entities to HA
    async_add_entities(GarageDoor(stick) for stick in maveoBox.maveoSticks)


class GarageDoor(CoverEntity):
    """Representation of a GarageDoor."""

    device_class = CoverDeviceClass.GARAGE

    should_poll = True
    supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE

    def __init__(self, maveoStick) -> None:
        """Initialize the garage door."""
        # Usual setup is done here. Callbacks are added in async_added_to_hass.
        self._maveoStick = maveoStick
        self._attr_unique_id = f"{self._maveoStick.id}_cover"

        # This is the name for this *entity*, the "name" attribute from "device_info"
        # is used as the device name for device screens in the UI. This name is used on
        # entity screens, and used to build the Entity ID that's used is automations etc.
        self._attr_name = self._maveoStick.name
        params = {}
        params["thingClassId"] = MaveoStick.thingclassid
        stateTypes = self._maveoStick.maveoBox.send_command(
            "Integrations.GetStateTypes", params
        )["params"]["stateTypes"]

        statetype_state = next(
            (obj for obj in stateTypes if obj["displayName"] == "State"),
            None,
        )
        self.stateTypeIdState = statetype_state["id"]
        self._available = True

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        # Importantly for a push integration, the module that will be getting updates
        # needs to notify HA of changes. The dummy device has a registercallback
        # method, so to this we add the 'self.async_write_ha_state' method, to be
        # called where ever there are changes.
        # The call back registration is done once this entity is registered with HA
        # (rather than in the __init__)
        self._maveoStick.register_callback(self.async_write_ha_state)

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
    def is_closed(self) -> bool:
        """Return if the cover is closed."""
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

    async def async_open_cover(self, **kwargs: Any) -> None:
        params = {}
        params["thingClassId"] = MaveoStick.thingclassid
        response = self._maveoStick.maveoBox.send_command(
            "Integrations.GetActionTypes", params
        )["params"]["actionTypes"]

        actionType_open = next(
            (obj for obj in response if obj["displayName"] == "Open"), None
        )

        params = {}
        params["actionTypeId"] = actionType_open["id"]
        params["thingId"] = self._maveoStick.id
        response = self._maveoStick.maveoBox.send_command(
            "Integrations.ExecuteAction", params
        )

        self._maveoStick.state = State.opening
        await self._maveoStick.publish_updates()

    async def async_close_cover(self, **kwargs: Any) -> None:
        params = {}
        params["thingClassId"] = MaveoStick.thingclassid
        response = self._maveoStick.maveoBox.send_command(
            "Integrations.GetActionTypes", params
        )["params"]["actionTypes"]

        actionType_open = next(
            (obj for obj in response if obj["displayName"] == "Close"), None
        )

        params = {}
        params["actionTypeId"] = actionType_open["id"]
        params["thingId"] = self._maveoStick.id
        response = self._maveoStick.maveoBox.send_command(
            "Integrations.ExecuteAction", params
        )

        self._maveoStick.state = State.closing
        await self._maveoStick.publish_updates()

    def update(self) -> None:
        """Fetch new state data.

        This is the only method that should fetch new data for Home Assistant.
        """
        params = {}
        params["thingId"] = self._maveoStick.id
        params["stateTypeId"] = self.stateTypeIdState
        try:
            value = self._maveoStick.maveoBox.send_command(
                "Integrations.GetStateValue", params
            )["params"]["value"]
            self._maveoStick.state = State[value]
            self._available = True
        except:
            self._available = False
            self._maveoStick.maveoBox.init_connection()
