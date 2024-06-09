"""Platform for sensor integration."""

# This file shows the setup for the sensors associated with the cover.
# They are setup in the same way with the call to the async_setup_entry function
# via HA from the module __init__. Each sensor has a device_class, this tells HA how
# to display it in the UI (for know types). The unit_of_measurement property tells HA
# what the unit is, so it can display the correct range. For predefined types (such as
# battery), the unit_of_measurement should match what's expected.
import random

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import (
    ATTR_VOLTAGE,
    PERCENTAGE,
)
from homeassistant.helpers.entity import Entity

from .const import DOMAIN


# See cover.py for more details.
# Note how both entities for each roller sensor (battry and illuminance) are added at
# the same time to the same list. This way only a single async_add_devices call is
# required.
async def async_setup_entry(hass, config_entry, async_add_entities):
    """Add sensors for passed config_entry in HA."""
    hub = hass.data[DOMAIN][config_entry.entry_id]

    new_devices = []
    for roller in hub.rollers:
        new_devices.append(IlluminanceSensor(roller))
    if new_devices:
        async_add_entities(new_devices)


# This base class shows the common properties and methods for a sensor as used in this
# example. See each sensor for further details about properties and methods that
# have been overridden.
class SensorBase(Entity):
    """Base representation of a Sensor."""

    should_poll = True

    def __init__(self, roller) -> None:
        """Initialize the sensor."""
        self._roller = roller

    # To link this entity to the cover device, this property must return an
    # identifiers value matching that used in the cover, but no other information such
    # as name. If name is returned, this entity will then also become a device in the
    # HA UI.
    @property
    def device_info(self):
        """Return information to link this entity with the correct device."""
        return {"identifiers": {(DOMAIN, self._roller.roller_id)}}

    @property
    def available(self) -> bool:
        """Return True if roller and hub is available."""
        return self._roller.online and self._roller.hub.online

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        self._roller.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        self._roller.remove_callback(self.async_write_ha_state)


class IlluminanceSensor(SensorBase):
    """Representation of a Sensor."""

    device_class = SensorDeviceClass.ILLUMINANCE
    _attr_unit_of_measurement = "lx"

    def __init__(self, roller) -> None:
        """Initialize the sensor."""
        super().__init__(roller)
        self._attr_unique_id = f"{self._roller.roller_id}_illuminance"
        self._attr_name = f"{self._roller.name} Illuminance"

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._roller.illuminance
