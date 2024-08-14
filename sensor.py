"""Platform for sensor integration."""

from collections.abc import Callable
from dataclasses import dataclass

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


# https://docs.python.org/3/library/dataclasses.html
@dataclass(frozen=True, kw_only=True)
class NymeaEntityDescription(SensorEntityDescription):
    """Describes Nymea sensor entity."""

    value: Callable[[dict], float | int | None]
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
    maveoBox = hass.data[DOMAIN][config_entry.entry_id]

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

    def __init__(self, thing: Thing, desc: NymeaEntityDescription) -> None:
        """Initialize the sensor."""
        self._thing = thing
        self._attr_unique_id = f"{self._thing.id}_{desc.key}"
        self._attr_name = desc.name
        self.device_class = desc.device_class
        self._stateTypeId = desc.key
        self.native_unit_of_measurement = desc.native_unit_of_measurement
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
