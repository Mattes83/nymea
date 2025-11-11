"""Support for nymea sensor entities."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfPressure, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .thing import Thing

_LOGGER = logging.getLogger(__name__)


# https://docs.python.org/3/library/dataclasses.html
@dataclass(frozen=True, kw_only=True)
class NymeaEntityDescription(SensorEntityDescription):
    """Describes Nymea sensor entity."""

    value: Callable[[dict[str, Any]], float | int | None]
    thingclass_id: str


SENSOR_TYPES: list[NymeaEntityDescription] = [
    # aqara h&t
    NymeaEntityDescription(
        thingclass_id="0b582616-0b05-4ac9-8b59-51b66079b571",
        key="b1641cec-3bf6-4654-b9c0-b81acb3b4481",
        name="Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda data: data.get("temperature"),
    ),
    NymeaEntityDescription(
        thingclass_id="0b582616-0b05-4ac9-8b59-51b66079b571",
        key="27a1e85a-f654-48d8-905d-05b3e2bc499e",
        name="Humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda data: data.get("humidity"),
    ),
    NymeaEntityDescription(
        thingclass_id="0b582616-0b05-4ac9-8b59-51b66079b571",
        key="7c3861f3-a9db-407e-9459-90a511d7f797",
        name="Pressure",
        device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        native_unit_of_measurement=UnitOfPressure.HPA,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda data: data.get("pressure"),
    ),
    NymeaEntityDescription(
        thingclass_id="0b582616-0b05-4ac9-8b59-51b66079b571",
        key="684f642e-08ed-4912-b7a9-597baef400c0",
        name="Signal strength",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda data: data.get("signalStrength"),
    ),
    NymeaEntityDescription(
        thingclass_id="0b582616-0b05-4ac9-8b59-51b66079b571",
        key="706eb697-4265-440d-a79a-11df3f6db335",
        name="Battery level",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda data: data.get("batteryLevel"),
    ),
    # maveo sensor
    NymeaEntityDescription(
        thingclass_id="db7bd8f7-3d12-4ed4-a7c7-fa022bd3701c",
        key="48612bb6-f209-44f8-ad21-eb4a4c5b9889",
        name="Humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda data: data.get("humidity"),
    ),
    NymeaEntityDescription(
        thingclass_id="db7bd8f7-3d12-4ed4-a7c7-fa022bd3701c",
        key="16bfc529-7822-40d8-a6c6-953aa9ceae27",
        name="Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda data: data.get("temperature"),
    ),
    # maveo stick
    NymeaEntityDescription(
        thingclass_id="ca6baab8-3708-4478-8ca2-7d4d6d542937",
        key="6f113f20-11ed-4f69-bda5-449363ab71d0",
        name="State",
        device_class=SensorDeviceClass.ENUM,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda data: data.get("temperature"),
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
        ThingSensor(thing, desc)
        for thing in maveoBox.things
        for desc in SENSOR_TYPES
        if thing.thingclass_id == desc.thingclass_id
    ]

    if new_devices:
        async_add_entities(new_devices)


class ThingSensor(SensorEntity):
    """Representation of a Sensor."""
    
    has_entity_name = True
    
    # Disable polling - using push notifications
    should_poll = False

    def __init__(self, thing: Thing, desc: NymeaEntityDescription) -> None:
        """Initialize the sensor."""
        self._thing: Thing = thing
        self._attr_unique_id: str = f"{self._thing.id}_{desc.key}"
        self._attr_name: str = desc.name
        self.device_class: SensorDeviceClass | None = desc.device_class
        self._stateTypeId: str = desc.key
        self.native_unit_of_measurement: str | None = desc.native_unit_of_measurement
        self._available: bool = True
        self.value: float | int | str | None = None

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
            value: float | int | str = self._thing.maveoBox.send_command(
                "Integrations.GetStateValue", params
            )["params"]["value"]  # type: ignore[index]
            self.value = value
            # Also cache it in the Thing for future notifications.
            self._thing._state_cache[self._stateTypeId] = value
            self._available = True
        except Exception as ex:
            self._available = False
            # This is logging, so use % formatting.
            _LOGGER.error("Error fetching initial sensor state for %s: %s", self._thing.id, ex)

    @property
    def state(self) -> float | int | str | None:
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
