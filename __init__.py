"""The nymea integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from . import maveo_box
from .const import DOMAIN
from .thing import Thing
from .maveo_stick import MaveoStick

PLATFORMS: list[str] = ["cover", "sensor", "binary_sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up nymea from a config entry."""
    nymea_hub = maveo_box.MaveoBox(
        hass, 
        entry.data["host"], 
        entry.data["port"], 
        entry.data["token"],
        websocket_port=entry.data.get("websocket_port", 4444)
    )
    
    try:
        await nymea_hub.init_connection()
    except Exception as ex:
        raise ConfigEntryNotReady(
            f"Error while connecting to {entry.data['host']}"
        ) from ex
    
    # Store in runtime_data instead of hass.data
    entry.runtime_data = nymea_hub
    
    await MaveoStick.add(nymea_hub)
    await Thing.add(nymea_hub)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Start notification listener AFTER all entities are set up
    # This prevents blocking during initialization
    nymea_hub.start_notification_listener()
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Stop the notification listener before removing the hub
    nymea_hub = entry.runtime_data
    await nymea_hub.stop_notification_listener()
    
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    return unload_ok
