"""Support for nymea button entities."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
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
    """Add buttons for passed config_entry in HA."""
    maveoBox = config_entry.runtime_data

    # Generate dynamic button configurations from discovered thing classes
    button_configs = []
    for thing_class in maveoBox.thing_classes:
        entities = generate_entities_for_thing_class(thing_class)
        button_configs.extend(entities["buttons"])

    _LOGGER.info("Generated %d dynamic button configurations", len(button_configs))

    # Create buttons for all things that match the thing class IDs
    new_devices = []
    for thing in maveoBox.things:
        for button_config in button_configs:
            if thing.thingclass_id == button_config["thingclass_id"]:
                new_devices.append(DynamicThingButton(thing, button_config))

    _LOGGER.info("Created %d button entities", len(new_devices))

    if new_devices:
        async_add_entities(new_devices)


class DynamicThingButton(ButtonEntity):
    """Representation of a dynamically discovered Button."""

    has_entity_name = True

    def __init__(self, thing: Thing, button_config: dict[str, Any]) -> None:
        """Initialize the button."""
        self._thing: Thing = thing
        self._actionTypeId: str = button_config["action_type_id"]
        self._attr_unique_id: str = f"{self._thing.id}_{self._actionTypeId}"
        self._attr_name: str = button_config["name"]
        self._available: bool = True

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            # Execute the action
            exec_params: dict[str, Any] = {}
            exec_params["thingId"] = self._thing.id
            exec_params["actionTypeId"] = self._actionTypeId

            _LOGGER.info(
                "Button press - Executing action %s for %s",
                self._actionTypeId,
                self._thing.name,
            )

            # Execute the action and wait for response
            result = await self.hass.async_add_executor_job(
                self._thing.maveoBox.send_command,
                "Integrations.ExecuteAction",
                exec_params,
            )

            if result is None:
                _LOGGER.error(
                    "Failed to execute button action %s for %s",
                    self._actionTypeId,
                    self._thing.name,
                )
                return

            _LOGGER.info(
                "Button action successful for %s, result: %s",
                self._thing.name,
                result,
            )
        except Exception as ex:
            _LOGGER.error(
                "Error executing button action for %s: %s",
                self._thing.id,
                ex,
            )

    @property
    def available(self) -> bool:
        """Return if the button is available."""
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
