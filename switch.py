"""Support for nymea switch entities."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .thing import Thing

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add switches for passed config_entry in HA."""
    maveoBox = config_entry.runtime_data

    switch_configs = maveoBox.entity_configs["switches"]
    _LOGGER.debug("Using %d pre-computed switch configurations", len(switch_configs))

    # Create switches for all things that match the thing class IDs
    new_devices = []
    for thing in maveoBox.things:
        for switch_config in switch_configs:
            if thing.thingclass_id == switch_config["thingclass_id"]:
                new_devices.append(DynamicThingSwitch(thing, switch_config))

    _LOGGER.info("Created %d switch entities", len(new_devices))

    if new_devices:
        async_add_entities(new_devices)


class DynamicThingSwitch(SwitchEntity):
    """Representation of a dynamically discovered Switch."""

    has_entity_name = True

    # Disable polling - using push notifications
    should_poll = False

    def __init__(self, thing: Thing, switch_config: dict[str, Any]) -> None:
        """Initialize the switch."""
        self._thing: Thing = thing
        self._stateTypeId: str = switch_config["state_type_id"]
        self._actionTypeId_off: str = switch_config.get(
            "action_type_id_off", switch_config.get("action_type_id", "")
        )
        self._actionTypeId_on: str = switch_config.get(
            "action_type_id_on", switch_config.get("action_type_id", "")
        )
        self._attr_unique_id: str = f"{self._thing.id}_{self._stateTypeId}"
        self._attr_name: str = switch_config["name"]
        self._available: bool = True
        self._is_on: bool | None = None

        # Look up action type definitions from the cached inventory (no network I/O).
        thing_class = thing.maveoBox.get_thing_class(thing.thingclass_id)
        action_types = thing_class.get("actionTypes", []) if thing_class else []
        self._action_type_on: dict[str, Any] | None = next(
            (at for at in action_types if at.get("id") == self._actionTypeId_on), None
        )
        self._action_type_off: dict[str, Any] | None = next(
            (at for at in action_types if at.get("id") == self._actionTypeId_off), None
        )

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        # Fetch initial state only if it wasn't prefilled from the inventory.
        if self._thing.get_state_value(self._stateTypeId) is None:
            await self._async_fetch_state()

        # Register callback for push notifications
        self._thing.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        self._thing.remove_callback(self.async_write_ha_state)

    async def _async_fetch_state(self) -> None:
        """Fetch the current state from the nymea box."""
        params = {"thingId": self._thing.id, "stateTypeId": self._stateTypeId}
        try:
            response = await self._thing.maveoBox.async_send_command(
                "Integrations.GetStateValue", params
            )
            if response is None:
                self._available = False
                return
            self._thing.set_state_value(self._stateTypeId, response["params"]["value"])
            self._available = True
        except Exception as ex:
            self._available = False
            _LOGGER.error(
                "Error fetching initial switch state for %s: %s",
                self._thing.id,
                ex,
            )

    async def _async_execute(
        self, action_type: dict[str, Any] | None, action_type_id: str, value: bool
    ) -> None:
        """Execute the on/off action, setting only bool-typed parameters."""
        exec_params: dict[str, Any] = {
            "thingId": self._thing.id,
            "actionTypeId": action_type_id,
        }

        if action_type:
            param_list = [
                {"paramTypeId": pt["id"], "value": value}
                for pt in action_type.get("paramTypes", [])
                if pt.get("type", "").lower() == "bool" and "id" in pt
            ]
            if param_list:
                exec_params["params"] = param_list

        _LOGGER.debug(
            "Executing action %s (value=%s) for %s with params: %s",
            action_type_id,
            value,
            self._thing.name,
            exec_params,
        )

        try:
            result = await self._thing.maveoBox.async_send_command(
                "Integrations.ExecuteAction", exec_params
            )
        except Exception as ex:
            _LOGGER.error(
                "Error switching %s for %s: %s",
                "on" if value else "off",
                self._thing.id,
                ex,
            )
            return

        if result is None:
            _LOGGER.error(
                "Failed to execute switch action for %s", self._thing.name
            )
        # Don't update state optimistically - wait for notification from device.

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self._async_execute(self._action_type_on, self._actionTypeId_on, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._async_execute(self._action_type_off, self._actionTypeId_off, False)

    @property
    def is_on(self) -> bool | None:
        """Return true if the switch is on."""
        # Try to get the latest value from Thing's cache (updated by notifications).
        cached_value: Any = self._thing.get_state_value(self._stateTypeId)
        if cached_value is not None:
            self._is_on = cached_value
        return self._is_on

    @property
    def available(self) -> bool:
        """Return if the switch is available."""
        return self._available

    @property
    def device_info(self) -> DeviceInfo:
        """Information about this entity/device."""
        return {
            "identifiers": {(DOMAIN, self._thing.id)},
            "name": self._thing.name,
            "manufacturer": self._thing.manufacturer,
            "model": self._thing.model,
        }
