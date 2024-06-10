"""Platform for sensor integration."""

from __future__ import annotations

from typing import Any

# These constants are relevant to the type of entity we are using.
# See below for how they are used.
from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverEntity,
    CoverDeviceClass,
    CoverEntityFeature,
)
from homeassistant.components.nymea.hub import State
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

from datetime import timedelta

SCAN_INTERVAL = timedelta(seconds=5)


# This function is called as part of the __init__.async_setup_entry (via the
# hass.config_entries.async_forward_entry_setup call)
async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add cover for passed config_entry in HA."""
    # The hub is loaded from the associated hass.data entry that was created in the
    # __init__.async_setup_entry function
    hub = hass.data[DOMAIN][config_entry.entry_id]

    # Add all entities to HA
    async_add_entities(NymeaCover(roller) for roller in hub.rollers)


class NymeaCover(CoverEntity):
    """Representation of a dummy Cover."""

    device_class = CoverDeviceClass.GARAGE

    should_poll = True
    supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE

    def __init__(self, roller) -> None:
        """Initialize the sensor."""
        # Usual setup is done here. Callbacks are added in async_added_to_hass.
        self._roller = roller

        # A unique_id for this entity with in this domain. This means for example if you
        # have a sensor on this cover, you must ensure the value returned is unique,
        # which is done here by appending "_cover". For more information, see:
        # https://developers.home-assistant.io/docs/entity_registry_index/#unique-id-requirements
        # Note: This is NOT used to generate the user visible Entity ID used in automations.
        self._attr_unique_id = f"{self._roller.roller_id}_cover"

        # This is the name for this *entity*, the "name" attribute from "device_info"
        # is used as the device name for device screens in the UI. This name is used on
        # entity screens, and used to build the Entity ID that's used is automations etc.
        self._attr_name = self._roller.name
        params = {}
        params["thingClassId"] = self._roller.thingclassid
        stateTypes = self._roller.hub.send_command(
            "Integrations.GetStateTypes", params
        )["params"]["stateTypes"]

        statetype_state = next(
            (obj for obj in stateTypes if obj["displayName"] == "State"),
            None,
        )
        self.stateTypeIdState = statetype_state["id"]

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        # Importantly for a push integration, the module that will be getting updates
        # needs to notify HA of changes. The dummy device has a registercallback
        # method, so to this we add the 'self.async_write_ha_state' method, to be
        # called where ever there are changes.
        # The call back registration is done once this entity is registered with HA
        # (rather than in the __init__)
        self._roller.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        # The opposite of async_added_to_hass. Remove any registered call backs here.
        self._roller.remove_callback(self.async_write_ha_state)

    @property
    def device_info(self) -> DeviceInfo:
        """Information about this entity/device."""
        return {
            "identifiers": {(DOMAIN, self._roller.roller_id)},
            "name": self.name,
            "sw_version": self._roller.firmware_version,
            "model": self._roller.model,
            "manufacturer": self._roller.hub.manufacturer,
        }

    @property
    def available(self) -> bool:
        """Return True if roller and hub is available."""
        return True

    @property
    def is_closed(self) -> bool:
        """Return if the cover is closed."""
        return self._roller.state == State.closed

    @property
    def is_closing(self) -> bool:
        """Return if the cover is closing or not."""
        return self._roller.state == State.closing

    @property
    def is_opening(self) -> bool:
        """Return if the cover is opening or not."""
        return self._roller.state == State.opening

    async def async_open_cover(self, **kwargs: Any) -> None:
        params = {}
        params["thingClassId"] = self._roller.thingclassid
        response = self._roller.hub.send_command("Integrations.GetActionTypes", params)[
            "params"
        ]["actionTypes"]

        actionType_open = next(
            (obj for obj in response if obj["displayName"] == "Open"), None
        )

        params = {}
        params["actionTypeId"] = actionType_open["id"]
        params["thingId"] = self._roller.roller_id
        response = self._roller.hub.send_command("Integrations.ExecuteAction", params)

        self._roller.state = State.opening

    async def async_close_cover(self, **kwargs: Any) -> None:
        params = {}
        params["thingClassId"] = self._roller.thingclassid
        response = self._roller.hub.send_command("Integrations.GetActionTypes", params)[
            "params"
        ]["actionTypes"]

        actionType_open = next(
            (obj for obj in response if obj["displayName"] == "Close"), None
        )

        params = {}
        params["actionTypeId"] = actionType_open["id"]
        params["thingId"] = self._roller.roller_id
        response = self._roller.hub.send_command("Integrations.ExecuteAction", params)

        self._roller.state = State.closing

    def update(self) -> None:
        """Fetch new state data.

        This is the only method that should fetch new data for Home Assistant.
        """
        params = {}
        params["thingId"] = self._roller.thingid
        params["stateTypeId"] = self.stateTypeIdState

        value = self._roller.hub.send_command("Integrations.GetStateValue", params)[
            "params"
        ]["value"]
        self._roller.state = State[value]
