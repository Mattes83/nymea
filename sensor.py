"""Platform for sensor integration."""

from homeassistant.components.nymea.aqara_weather_sensor import AqaraSensor
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from dataclasses import dataclass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfPressure, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.const import (
    ATTR_MANUFACTURER,
    ATTR_MODEL,
    ATTR_SW_VERSION,
    PERCENTAGE,
    STATE_UNKNOWN,
    EntityCategory,
    UnitOfApparentPower,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)

from .const import DOMAIN
from typing import Callable, Final, cast


# https://docs.python.org/3/library/dataclasses.html
@dataclass(frozen=True, kw_only=True)
class NymeaEntityDescription(SensorEntityDescription):
    """Describes Nymea sensor entity."""

    value: Callable[[dict], float | int | None]
    thingclass_id: str


SENSOR_TYPES: list[NymeaEntityDescription] = [
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
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda data: data.get("batteryLevel"),
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add sensors for passed config_entry in HA."""
    maveoBox = hass.data[DOMAIN][config_entry.entry_id]

    new_devices = []
    for stick in maveoBox.maveoSticks:
        new_devices.append(StateSensor(stick))

    for sensor in maveoBox.maveoSensors:
        new_devices.append(MaveoHumiditySensor(sensor))
        new_devices.append(MaveoTemperatureSensor(sensor))

    for sensor in maveoBox.aqaraSensors:
        for desc in SENSOR_TYPES:
            new_devices.append(AqaraHTSensor(sensor, desc))

    if new_devices:
        async_add_entities(new_devices)


class SensorBase(Entity):
    """Base representation of a Sensor."""

    should_poll = True

    def __init__(self, stick) -> None:
        """Initialize the sensor."""
        self._maveoStick = stick

    @property
    def device_info(self):
        """Return information to link this entity with the correct device."""
        return {"identifiers": {(DOMAIN, self._maveoStick.id)}}

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        self._maveoStick.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        self._maveoStick.remove_callback(self.async_write_ha_state)


class StateSensor(SensorBase):
    """Representation of a Sensor."""

    device_class = SensorDeviceClass.ENUM

    def __init__(self, stick) -> None:
        """Initialize the sensor."""
        super().__init__(stick)
        self._attr_unique_id = f"{self._maveoStick.id}_state"
        self._attr_name = f"{self._maveoStick.name} State"
        self.entity_registry_visible_default = False

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._maveoStick.state


class MaveoHumiditySensor(SensorEntity):
    """Representation of a Sensor."""

    device_class = SensorDeviceClass.HUMIDITY

    def __init__(self, sensor) -> None:
        """Initialize the sensor."""
        self._maveoSensor = sensor
        self._attr_unique_id = f"{self._maveoSensor.id}_humidity"
        self._attr_name = "Humidity"
        self._thingclassid = "db7bd8f7-3d12-4ed4-a7c7-fa022bd3701c"
        self._stateTypeIdHumidity = "48612bb6-f209-44f8-ad21-eb4a4c5b9889"
        self.native_unit_of_measurement = PERCENTAGE
        self.update()

    @property
    def state(self) -> float:
        """Return the state of the sensor."""
        return self.humidity

    @property
    def device_info(self) -> DeviceInfo:
        """Information about this entity/device."""
        return {
            "identifiers": {(DOMAIN, self._maveoSensor.id)},
            "name": "maveo Sensor H+T",
            "model": "maveo Sensor H+T",
            "sw_version": self._maveoSensor.firmware_version,
            "manufacturer": "Marantec",
        }

    def update(self) -> None:
        """Fetch new state data. This is the only method that should fetch new data for Home Assistant."""

        params = {}
        params["thingId"] = self._maveoSensor.id
        params["stateTypeId"] = self._stateTypeIdHumidity
        value = self._maveoSensor.maveoBox.send_command(
            "Integrations.GetStateValue", params
        )["params"]["value"]
        self.humidity = value


class MaveoTemperatureSensor(SensorEntity):
    """Representation of a Sensor."""

    device_class = SensorDeviceClass.TEMPERATURE

    def __init__(self, sensor) -> None:
        """Initialize the sensor."""
        self._maveoSensor = sensor
        self._attr_unique_id = f"{self._maveoSensor.id}_temperature"
        self._attr_name = "Temperature"
        self._thingclassid = "db7bd8f7-3d12-4ed4-a7c7-fa022bd3701c"
        self._stateTypeIdTemperature = "16bfc529-7822-40d8-a6c6-953aa9ceae27"
        self.native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self.update()

    @property
    def state(self) -> float:
        """Return the state of the sensor."""
        return self.temperature

    @property
    def device_info(self) -> DeviceInfo:
        """Information about this entity/device."""
        return {
            "identifiers": {(DOMAIN, self._maveoSensor.id)},
            "name": "maveo Sensor H+T",
            "model": "maveo Sensor H+T",
            "sw_version": self._maveoSensor.firmware_version,
            "manufacturer": "Marantec",
        }

    def update(self) -> None:
        """Fetch new state data. This is the only method that should fetch new data for Home Assistant."""

        params = {}
        params["thingId"] = self._maveoSensor.id
        params["stateTypeId"] = self._stateTypeIdTemperature
        value = self._maveoSensor.maveoBox.send_command(
            "Integrations.GetStateValue", params
        )["params"]["value"]
        self.temperature = value


class AqaraHTSensor(SensorEntity):
    """Representation of a Sensor."""

    device_class = SensorDeviceClass.TEMPERATURE

    def __init__(self, sensor: AqaraSensor, desc: NymeaEntityDescription) -> None:
        """Initialize the sensor."""
        self._aqaraSensor = sensor
        self._attr_unique_id = f"{self._aqaraSensor.id}_{desc.key}"
        self._attr_name = desc.name
        self._thingclassid = desc.thingclass_id
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
            "identifiers": {(DOMAIN, self._aqaraSensor.id)},
            "name": "Aqara Sensor H+T",
            "model": "WSDCGQ11LM",
            "sw_version": self._aqaraSensor.firmware_version,
            "manufacturer": "Lumi",
            # "via_device": (DOMAIN, self._aqaraSensor.maveoBox.hub_id), bridge has to be added as device first
        }

    def update(self) -> None:
        """Fetch new state data. This is the only method that should fetch new data for Home Assistant."""

        params = {}
        params["thingId"] = self._aqaraSensor.id
        params["stateTypeId"] = self._stateTypeId
        value = self._aqaraSensor.maveoBox.send_command(
            "Integrations.GetStateValue", params
        )["params"]["value"]
        self.value = value
