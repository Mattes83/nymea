"""Support for nymea binary sensor entities."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
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
    """Add binary sensors for passed config_entry in HA."""
    maveoBox = config_entry.runtime_data

    # Generate dynamic binary sensor configurations from discovered thing classes
    binary_sensor_configs = []
    for thing_class in maveoBox.thing_classes:
        entities = generate_entities_for_thing_class(thing_class)
        binary_sensor_configs.extend(entities["binary_sensors"])

    _LOGGER.info(
        "Generated %d dynamic binary sensor configurations", len(binary_sensor_configs)
    )

    # Create binary sensors for all things that match the thing class IDs
    new_devices = []
    for thing in maveoBox.things:
        for sensor_config in binary_sensor_configs:
            if thing.thingclass_id == sensor_config["thingclass_id"]:
                new_devices.append(DynamicBinaryThingSensor(thing, sensor_config))

    _LOGGER.info("Created %d binary sensor entities", len(new_devices))

    if new_devices:
        async_add_entities(new_devices)


class DynamicBinaryThingSensor(BinarySensorEntity):
    """Representation of a dynamically discovered Binary Sensor."""

    has_entity_name = True

    # Disable polling - using push notifications
    should_poll = False

    def __init__(self, thing: Thing, sensor_config: dict[str, Any]) -> None:
        """Initialize the binary sensor."""
        self._thing: Thing = thing
        self._stateTypeId: str = sensor_config["state_type_id"]
        self._attr_unique_id: str = f"{self._thing.id}_{self._stateTypeId}"
        self._attr_name: str = sensor_config["name"]
        self._attr_device_class: BinarySensorDeviceClass | None = sensor_config.get(
            "device_class"
        )
        self._inverted: bool = sensor_config.get("inverted", False)
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
            # Invert value if configured (e.g., "Closed" state)
            if self._inverted:
                value = not value
            self._is_on = value
            self._available = True
        except Exception as ex:
            self._available = False
            # This is logging, so use % formatting.
            _LOGGER.error(
                "Error fetching initial binary sensor state for %s: %s",
                self._thing.id,
                ex,
            )

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        # Try to get the latest value from Thing's cache (updated by notifications).
        cached_value: Any = self._thing.get_state_value(self._stateTypeId)
        if cached_value is not None:
            # Invert value if configured (e.g., "Closed" state)
            self._is_on = not cached_value if self._inverted else cached_value
        return self._is_on

    @property
    def available(self) -> bool:
        """Return if the binary sensor is available."""
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
