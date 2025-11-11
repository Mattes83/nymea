"""Support for nymea binary sensor entities."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .thing import Thing

_LOGGER = logging.getLogger(__name__)


# https://docs.python.org/3/library/dataclasses.html
@dataclass(frozen=True, kw_only=True)
class NymeaEntityDescription(BinarySensorEntityDescription):
    """Describes Nymea sensor entity."""

    value: Callable[[dict[str, Any]], float | int | None]
    thingclass_id: str


BINARY_SENSOR_TYPES: list[NymeaEntityDescription] = [
    # maveo stick
    NymeaEntityDescription(
        thingclass_id="ca6baab8-3708-4478-8ca2-7d4d6d542937",
        key="ee5fb485-f95a-4daf-a414-14ade7a0a452",
        name="Door movement",
        device_class=BinarySensorDeviceClass.MOVING,
        value=lambda data: data.get("moving"),
    ),
    NymeaEntityDescription(
        thingclass_id="ca6baab8-3708-4478-8ca2-7d4d6d542937",
        key="394538db-4f28-4230-98bb-0bbe699ee2c3",
        name="Maintenance required",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value=lambda data: data.get("maintenanceRequired"),
    ),
    NymeaEntityDescription(
        thingclass_id="ca6baab8-3708-4478-8ca2-7d4d6d542937",
        key="300a5eea-4961-4c9c-929a-32741ffa1a26",
        name="Firmware update available",
        device_class=BinarySensorDeviceClass.UPDATE,
        value=lambda data: data.get("updateAvailable"),
    ),
    NymeaEntityDescription(
        thingclass_id="ca6baab8-3708-4478-8ca2-7d4d6d542937",
        key="90ef8e32-0bc2-49fd-9fe9-abb633debeae",
        name="Intruder detected",
        device_class=BinarySensorDeviceClass.TAMPER,
        value=lambda data: data.get("updateAvailable"),
    ),
    NymeaEntityDescription(
        thingclass_id="ca6baab8-3708-4478-8ca2-7d4d6d542937",
        key="234bbb47-1641-4e8f-a7cd-09a65722596c",
        name="Connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value=lambda data: data.get("connected"),
    ),
    NymeaEntityDescription(
        thingclass_id="ca6baab8-3708-4478-8ca2-7d4d6d542937",
        key="4e61b1da-3d5f-4300-826a-62726680bc2b",
        name="Opened",
        entity_registry_visible_default=False,
        device_class=BinarySensorDeviceClass.GARAGE_DOOR,
        value=lambda data: data.get("opened"),
    ),
    NymeaEntityDescription(
        thingclass_id="ca6baab8-3708-4478-8ca2-7d4d6d542937",
        key="bad168af-1925-42c2-8343-51bdb19895d3",
        name="Light",
        device_class=BinarySensorDeviceClass.LIGHT,
        value=lambda data: data.get("power"),
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add sensors for passed config_entry in HA."""
    maveoBox = config_entry.runtime_data

    new_devices = [
        BinaryThingSensor(thing, desc)
        for thing in maveoBox.things
        for desc in BINARY_SENSOR_TYPES
        if thing.thingclass_id == desc.thingclass_id
    ]

    if new_devices:
        async_add_entities(new_devices)


class BinaryThingSensor(BinarySensorEntity):
    """Representation of a Sensor."""
    
    has_entity_name = True
    
    # Disable polling - using push notifications
    should_poll = False

    def __init__(self, thing: Thing, desc: NymeaEntityDescription) -> None:
        """Initialize the sensor."""
        self._thing: Thing = thing
        self._attr_unique_id: str = f"{self._thing.id}_{desc.key}"
        self._attr_name: str = desc.name
        self.device_class: BinarySensorDeviceClass | None = desc.device_class
        self._stateTypeId: str = desc.key
        self._available: bool = True
        self.value: bool | None = None

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
            self.value = value
            # Also cache it in the Thing for future notifications.
            self._thing._state_cache[self._stateTypeId] = value
            self._available = True
        except Exception as ex:
            self._available = False
            # This is logging, so use % formatting.
            _LOGGER.error("Error fetching initial binary sensor state for %s: %s", self._thing.id, ex)

    @property
    def state(self) -> bool | None:
        """Return the state of the sensor."""
        # Try to get the latest value from Thing's cache (updated by notifications).
        cached_value: Any = self._thing.get_state_value(self._stateTypeId)
        if cached_value is not None:
            self.value = cached_value
        return self.value

    @property
    def available(self) -> bool:
        """Return the state of the sensor."""
        return self._available

    @property
    def device_info(self) -> DeviceInfo:
        """Information about this entity/device."""
        return {
            "identifiers": {(DOMAIN, self._thing.id)},
            "name": self._thing.name,
            "manufacturer": self._thing.manufacturer,
        }
