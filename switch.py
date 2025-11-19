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
from .dynamic_mapper import generate_entities_for_thing_class
from .thing import Thing

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add switches for passed config_entry in HA."""
    maveoBox = config_entry.runtime_data

    # Generate dynamic switch configurations from discovered thing classes
    switch_configs = []
    for thing_class in maveoBox.thing_classes:
        entities = generate_entities_for_thing_class(thing_class)
        switch_configs.extend(entities["switches"])

    _LOGGER.info("Generated %d dynamic switch configurations", len(switch_configs))

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

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        # Fetch initial state before notifications start
        await self.async_update()

        # Register callback for push notifications
        self._thing.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        self._thing.remove_callback(self.async_write_ha_state)

    async def async_update(self) -> None:
        """Fetch initial state (called once before notification listener starts)."""
        params: dict[str, str] = {}
        params["thingId"] = self._thing.id
        params["stateTypeId"] = self._stateTypeId
        try:
            value: bool = self._thing.maveoBox.send_command(
                "Integrations.GetStateValue", params
            )["params"]["value"]  # type: ignore[index]
            # Cache the original value in the Thing for future notifications.
            self._thing._state_cache[self._stateTypeId] = value
            self._is_on = value
            self._available = True
        except Exception as ex:
            self._available = False
            # This is logging, so use % formatting.
            _LOGGER.error(
                "Error fetching initial switch state for %s: %s",
                self._thing.id,
                ex,
            )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        # Query the action type to get parameter information
        params_query: dict[str, Any] = {}
        params_query["thingClassId"] = self._thing.thingclass_id

        try:
            # Run synchronous send_command in executor
            response = await self.hass.async_add_executor_job(
                self._thing.maveoBox.send_command,
                "Integrations.GetActionTypes",
                params_query,
            )

            if response is None:
                _LOGGER.error("Failed to get action types for %s", self._thing.name)
                return

            action_types = response.get("params", {}).get("actionTypes", [])

            # Find the action type we want to execute
            action_type = next(
                (at for at in action_types if at.get("id") == self._actionTypeId_on),
                None,
            )

            # Log what we discovered about this action
            _LOGGER.warning(
                "Turn ON - Full action type definition for %s: %s",
                self._thing.name, action_type
            )
            _LOGGER.warning(
                "Turn ON - Action ID we're looking for: %s", self._actionTypeId_on
            )
            _LOGGER.warning(
                "Turn ON - All available action types: %s",
                [{"id": at.get("id"), "name": at.get("name", at.get("displayName")),
                  "paramTypes": at.get("paramTypes", [])} for at in action_types]
            )

            # Build the execution params
            exec_params: dict[str, Any] = {}
            exec_params["thingId"] = self._thing.id
            exec_params["actionTypeId"] = self._actionTypeId_on

            # Check if this action has parameters
            if action_type and action_type.get("paramTypes"):
                # Build params based on paramTypes
                param_list = []
                for param_type in action_type["paramTypes"]:
                    # Use the parameter ID (not name) as the key
                    param_id = param_type.get("id")
                    param_name = param_type.get("name")
                    param_type_type = param_type.get("type", "unknown")
                    _LOGGER.warning(
                        "Turn ON - Param type found: id=%s, name=%s, type=%s",
                        param_id, param_name, param_type_type
                    )
                    # For Nymea API, use paramTypeId (the parameter ID) and value
                    param_list.append({"paramTypeId": param_id, "value": True})
                exec_params["params"] = param_list
                _LOGGER.warning("Turn ON - Built params: %s", exec_params["params"])
            else:
                _LOGGER.warning("Turn ON - No parameters required for this action")

            # Execute the action and wait for response
            result = await self.hass.async_add_executor_job(
                self._thing.maveoBox.send_command,
                "Integrations.ExecuteAction",
                exec_params,
            )

            _LOGGER.warning("Turn ON - Execution params sent: %s", exec_params)
            _LOGGER.warning("Turn ON - Result received: %s", result)

            if result is None:
                _LOGGER.error("Failed to execute turn_on action for %s", self._thing.name)
                return

            _LOGGER.info("Turn ON command successful for %s, result: %s", self._thing.name, result)
            # Don't update state optimistically - wait for notification from device
        except Exception as ex:
            _LOGGER.error(
                "Error turning on switch for %s: %s",
                self._thing.id,
                ex,
            )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        # Query the action type to get parameter information
        params_query: dict[str, Any] = {}
        params_query["thingClassId"] = self._thing.thingclass_id

        try:
            # Run synchronous send_command in executor
            response = await self.hass.async_add_executor_job(
                self._thing.maveoBox.send_command,
                "Integrations.GetActionTypes",
                params_query,
            )

            if response is None:
                _LOGGER.error("Failed to get action types for %s", self._thing.name)
                return

            action_types = response.get("params", {}).get("actionTypes", [])

            # Find the action type we want to execute
            action_type = next(
                (at for at in action_types if at.get("id") == self._actionTypeId_off),
                None,
            )

            # Log what we discovered about this action
            _LOGGER.warning(
                "Turn OFF - Full action type definition for %s: %s",
                self._thing.name, action_type
            )
            _LOGGER.warning(
                "Turn OFF - Action ID we're looking for: %s", self._actionTypeId_off
            )

            # Build the execution params
            exec_params: dict[str, Any] = {}
            exec_params["thingId"] = self._thing.id
            exec_params["actionTypeId"] = self._actionTypeId_off

            # Check if this action has parameters
            if action_type and action_type.get("paramTypes"):
                # Build params based on paramTypes
                param_list = []
                for param_type in action_type["paramTypes"]:
                    # Use the parameter ID (not name) as the key
                    param_id = param_type.get("id")
                    param_name = param_type.get("name")
                    param_type_type = param_type.get("type", "unknown")
                    _LOGGER.warning(
                        "Turn OFF - Param type found: id=%s, name=%s, type=%s",
                        param_id, param_name, param_type_type
                    )
                    # For Nymea API, use paramTypeId (the parameter ID) and value
                    param_list.append({"paramTypeId": param_id, "value": False})
                exec_params["params"] = param_list
                _LOGGER.warning("Turn OFF - Built params: %s", exec_params["params"])
            else:
                _LOGGER.warning("Turn OFF - No parameters required for this action")

            # Execute the action and wait for response
            result = await self.hass.async_add_executor_job(
                self._thing.maveoBox.send_command,
                "Integrations.ExecuteAction",
                exec_params,
            )

            _LOGGER.warning("Turn OFF - Execution params sent: %s", exec_params)
            _LOGGER.warning("Turn OFF - Result received: %s", result)

            if result is None:
                _LOGGER.error("Failed to execute turn_off action for %s", self._thing.name)
                return

            _LOGGER.info("Turn OFF command successful for %s, result: %s", self._thing.name, result)
            # Don't update state optimistically - wait for notification from device
        except Exception as ex:
            _LOGGER.error(
                "Error turning off switch for %s: %s",
                self._thing.id,
                ex,
            )

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
