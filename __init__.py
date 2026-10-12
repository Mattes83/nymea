"""The nymea integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TOKEN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr

from .const import CONF_WEBSOCKET_PORT, DOMAIN
from .dynamic_mapper import generate_entities_for_thing_class
from .maveo_box import MaveoBox
from .maveo_stick import MaveoStick
from .thing import Thing

_LOGGER = logging.getLogger(__name__)

type NymeaConfigEntry = ConfigEntry[MaveoBox]

PLATFORMS: list[Platform] = [
    Platform.COVER,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.BUTTON,
]


async def async_setup_entry(hass: HomeAssistant, entry: NymeaConfigEntry) -> bool:
    """Set up nymea from a config entry.

    Raises:
        ConfigEntryError: If the device configuration is unsupported.
        ConfigEntryNotReady: If unable to connect to the nymea device.
    """
    nymea_hub = MaveoBox(
        hass,
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data.get(CONF_TOKEN),
        websocket_port=entry.data.get(CONF_WEBSOCKET_PORT, 4445),
    )

    try:
        await nymea_hub.init_connection()
        await nymea_hub.async_fetch_inventory()
    except NotImplementedError as ex:
        await nymea_hub.close()
        raise ConfigEntryError(str(ex)) from ex
    except Exception as ex:
        await nymea_hub.close()
        raise ConfigEntryNotReady(
            f"Error while connecting to {entry.data[CONF_HOST]}"
        ) from ex

    # Store in runtime_data instead of hass.data.
    entry.runtime_data = nymea_hub

    await MaveoStick.add(nymea_hub)
    await Thing.add(nymea_hub)

    # Pre-compute entity configs once; all platforms read from nymea_hub.entity_configs.
    entity_configs: dict[str, list] = {
        "sensors": [],
        "binary_sensors": [],
        "switches": [],
        "buttons": [],
    }
    for thing_class in nymea_hub.thing_classes:
        configs = generate_entities_for_thing_class(thing_class)
        for key in entity_configs:
            entity_configs[key].extend(configs[key])
    nymea_hub.entity_configs = entity_configs

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Remove devices from HA registry that no longer exist in the nymea hub.
    _cleanup_stale_devices(hass, entry, nymea_hub)

    # Start notification listener AFTER all entities are set up.
    # This prevents blocking during initialization.
    nymea_hub.start_notification_listener()

    return True


def _cleanup_stale_devices(
    hass: HomeAssistant, entry: NymeaConfigEntry, nymea_hub: MaveoBox
) -> None:
    """Remove devices from HA registry that no longer exist in the nymea hub."""
    device_registry = dr.async_get(hass)

    current_thing_ids = {thing.id for thing in nymea_hub.things}
    current_thing_ids.update(stick.id for stick in nymea_hub.maveoSticks)

    _LOGGER.debug("Current thing IDs from hub: %s", current_thing_ids)

    registered_devices = dr.async_entries_for_config_entry(
        device_registry, entry.entry_id
    )
    _LOGGER.debug("Registered devices for config entry: %d", len(registered_devices))

    for device in registered_devices:
        device_thing_ids = {
            identifier[1]
            for identifier in device.identifiers
            if identifier[0] == DOMAIN
        }
        _LOGGER.debug(
            "Device '%s' has nymea identifiers: %s", device.name, device_thing_ids
        )
        if not device_thing_ids.intersection(current_thing_ids):
            _LOGGER.info(
                "Removing stale device '%s' (%s) from registry",
                device.name,
                device.id,
            )
            device_registry.async_remove_device(device.id)


async def async_unload_entry(hass: HomeAssistant, entry: NymeaConfigEntry) -> bool:
    """Unload a config entry."""
    # Stop the notification listener and close the connection.
    await entry.runtime_data.close()

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
