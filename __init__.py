"""The nymea integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import maveo_box
from .maveo_stick import MaveoStick
from .maveo_sensor import MaveoSensor
from .aqara_sensor import AqaraSensor
from .const import DOMAIN

PLATFORMS: list[str] = ["cover", "sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up nymea from a config entry."""
    nymea_hub = maveo_box.MaveoBox(
        hass, entry.data["host"], entry.data["port"], entry.data["token"]
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = nymea_hub
    await nymea_hub.init_connection()
    await MaveoStick.add(nymea_hub)
    await MaveoSensor.add(nymea_hub)
    await AqaraSensor.add(nymea_hub)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # This is called when an entry/configured device is to be removed. The class
    # needs to unload itself, and remove callbacks. See the classes for further
    # details
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
