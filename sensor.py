"""Platform for sensor integration."""

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import ATTR_VOLTAGE, PERCENTAGE
from homeassistant.helpers.entity import Entity

from .const import DOMAIN


async def async_setup_entry(hass, config_entry, async_add_entities) -> None:
    """Add sensors for passed config_entry in HA."""
    maveoBox = hass.data[DOMAIN][config_entry.entry_id]

    new_devices = []
    for stick in maveoBox.maveoSticks:
        new_devices.append(StateSensor(stick))

    # things = maveoBox.send_command("Integrations.GetThings")["params"]["things"]
    # for thing in things:
    #    if thing["thingClassId"] == "ca6baab8-3708-4478-8ca2-7d4d6d542937":
    #        new_devices.append(HumidityTemperatureSensor())

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
        return {"identifiers": {(DOMAIN, self._maveoStick.stick_id)}}

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
        self._attr_unique_id = f"{self._maveoStick.stick_id}_state"
        self._attr_name = f"{self._maveoStick.name} State"

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._maveoStick.state


# class HumidityTemperatureSensor(SensorBase):
#   """Representation of a Sensor."""
#
#   device_class = SensorDeviceClass.HUMIDITY
#
#   def __init__(self, roller) -> None:
#       """Initialize the sensor."""
#       super().__init__(roller)
#       self._attr_unique_id = f"{self._roller.roller_id}_temperature"
#       self._attr_name = f"{self._roller.name} Temperature"
#       self._thingclassid = "db7bd8f7-3d12-4ed4-a7c7-fa022bd3701c"
#       self._stateTypeIdHumidity = "48612bb6-f209-44f8-ad21-eb4a4c5b9889"
#       self._stateTypeIdTemperature = "16bfc529-7822-40d8-a6c6-953aa9ceae27"
#
#   @property
#   def temperature(self):
#       """Return the state of the sensor."""
#       return self.temperature
#
#   def update(self) -> None:
#       """Fetch new state data.
#
#       This is the only method that should fetch new data for Home Assistant.
#       """
#       params = {}
#       params["thingId"] = self._roller.thingid
#       params["stateTypeId"] = self._stateTypeIdTemperature
#
#       value = self._roller.hub.send_command("Integrations.GetStateValue", params)[
#           "params"
#       ]["value"]
#       self.temperature = value
