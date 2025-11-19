"""The nymea integration for Home Assistant."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from . import maveo_box
from .const import DOMAIN
from .maveo_stick import MaveoStick
from .thing import Thing

PLATFORMS: list[str] = ["cover", "sensor", "binary_sensor", "switch", "button"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up nymea from a config entry.

    Args:
        hass: Home Assistant instance.
        entry: Config entry for the nymea integration.

    Returns:
        True if setup was successful.

    Raises:
        ConfigEntryNotReady: If unable to connect to the nymea device.
    """
    nymea_hub = maveo_box.MaveoBox(
        hass,
        entry.data["host"],
        entry.data["port"],
        entry.data["token"],
        websocket_port=entry.data.get("websocket_port", 4444),
    )

    try:
        await nymea_hub.init_connection()
    except Exception as ex:
        raise ConfigEntryNotReady(
            f"Error while connecting to {entry.data['host']}"
        ) from ex

    # Discover and log all available thing classes and things
    await nymea_hub.discover_and_log_all_things()

    # Store in runtime_data instead of hass.data.
    entry.runtime_data = nymea_hub

    await MaveoStick.add(nymea_hub)
    await Thing.add(nymea_hub)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Start notification listener AFTER all entities are set up.
    # This prevents blocking during initialization.
    nymea_hub.start_notification_listener()

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry.

    Args:
        hass: Home Assistant instance.
        entry: Config entry to unload.

    Returns:
        True if unload was successful.
    """
    # Stop the notification listener before removing the hub.
    nymea_hub = entry.runtime_data
    await nymea_hub.stop_notification_listener()

    # Unload platforms.
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    return unload_ok
