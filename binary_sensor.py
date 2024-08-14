"""Platform for sensor integration."""

from collections.abc import Callable
from dataclasses import dataclass

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


# https://docs.python.org/3/library/dataclasses.html
@dataclass(frozen=True, kw_only=True)
class NymeaEntityDescription(BinarySensorEntityDescription):
    """Describes Nymea sensor entity."""

    value: Callable[[dict], float | int | None]
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
    maveoBox = hass.data[DOMAIN][config_entry.entry_id]

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

    def __init__(self, thing: Thing, desc: NymeaEntityDescription) -> None:
        """Initialize the sensor."""
        self._thing = thing
        self._attr_unique_id = f"{self._thing.id}_{desc.key}"
        self._attr_name = desc.name
        self.device_class = desc.device_class
        self._stateTypeId = desc.key
        self.update()

    @property
    def state(self) -> float:
        """Return the state of the sensor."""
        return self.value

    @property
    def device_info(self) -> DeviceInfo:
        """Information about this entity/device."""
        return {
            "identifiers": {(DOMAIN, self._thing.id)},
            "name": self._thing.name,
            "manufacturer": self._thing.manufacturer,
        }

    def update(self) -> None:
        """Fetch new state data. This is the only method that should fetch new data for Home Assistant."""

        params = {}
        params["thingId"] = self._thing.id
        params["stateTypeId"] = self._stateTypeId
        value = self._thing.maveoBox.send_command("Integrations.GetStateValue", params)[
            "params"
        ]["value"]
        self.value = value
