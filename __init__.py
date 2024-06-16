"""The nymea integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import maveo_box
from .maveo_stick import MaveoStick
from .const import DOMAIN

PLATFORMS: list[str] = ["cover", "sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up nymea from a config entry."""
    nymea_hub = maveo_box.MaveoBox(hass, entry.data["host"], entry.data["port"])
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = nymea_hub
    await nymea_hub.init_connection()
    await MaveoStick.add(nymea_hub)

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


# list_thingClasses: ca6baab8-3708-4478-8ca2-7d4d6d542937
# Garage, id: 580f520f-5a6c-4f4d-a7d7-45a40ab582c2, thingClassId: ca6baab8-3708-4478-8ca2-7d4d6d542937
