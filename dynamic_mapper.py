"""Dynamic entity mapper for Nymea integration.

Maps Nymea state types to Home Assistant entity types based on state type metadata.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    PERCENTAGE,
    UnitOfPressure,
    UnitOfTemperature,
)

_LOGGER = logging.getLogger(__name__)


# Mapping of Nymea state type names (lowercase) to HA sensor device classes
STATE_NAME_TO_SENSOR_CLASS = {
    "temperature": SensorDeviceClass.TEMPERATURE,
    "humidity": SensorDeviceClass.HUMIDITY,
    "pressure": SensorDeviceClass.ATMOSPHERIC_PRESSURE,
    "battery": SensorDeviceClass.BATTERY,
    "battery level": SensorDeviceClass.BATTERY,
    "signal strength": SensorDeviceClass.SIGNAL_STRENGTH,
    "voc": SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS,
    "co2": SensorDeviceClass.CO2,
    "pm2.5": SensorDeviceClass.PM25,
    "pm10": SensorDeviceClass.PM10,
    "illuminance": SensorDeviceClass.ILLUMINANCE,
    "energy": SensorDeviceClass.ENERGY,
    "power": SensorDeviceClass.POWER,
    "voltage": SensorDeviceClass.VOLTAGE,
    "current": SensorDeviceClass.CURRENT,
}

# Unit mappings
UNIT_MAPPINGS = {
    "celsius": UnitOfTemperature.CELSIUS,
    "fahrenheit": UnitOfTemperature.FAHRENHEIT,
    "hpa": UnitOfPressure.HPA,
    "mbar": UnitOfPressure.MBAR,
    "percentage": PERCENTAGE,
    "%": PERCENTAGE,
}

# Binary sensor mappings
STATE_NAME_TO_BINARY_SENSOR_CLASS = {
    "connected": BinarySensorDeviceClass.CONNECTIVITY,
    "available": BinarySensorDeviceClass.CONNECTIVITY,
    "reachable": BinarySensorDeviceClass.CONNECTIVITY,
    "battery critical": BinarySensorDeviceClass.BATTERY,
    "battery level critical": BinarySensorDeviceClass.BATTERY,
    "motion": BinarySensorDeviceClass.MOTION,
    "presence": BinarySensorDeviceClass.PRESENCE,
    "opened": BinarySensorDeviceClass.OPENING,
    "closed": BinarySensorDeviceClass.DOOR,
    "door": BinarySensorDeviceClass.DOOR,
    "window": BinarySensorDeviceClass.WINDOW,
    "smoke": BinarySensorDeviceClass.SMOKE,
    "gas": BinarySensorDeviceClass.GAS,
    "maintenance required": BinarySensorDeviceClass.PROBLEM,
    "problem": BinarySensorDeviceClass.PROBLEM,
    "tamper": BinarySensorDeviceClass.TAMPER,
    "intruder": BinarySensorDeviceClass.SAFETY,
    "vibration": BinarySensorDeviceClass.VIBRATION,
    "occupancy": BinarySensorDeviceClass.OCCUPANCY,
    "light": BinarySensorDeviceClass.LIGHT,
    "moving": BinarySensorDeviceClass.MOVING,
    "barrier": BinarySensorDeviceClass.SAFETY,
    "interrupted": BinarySensorDeviceClass.PROBLEM,
}


def determine_sensor_type(
    state_type: dict[str, Any],
) -> tuple[str, SensorDeviceClass | None, str | None, SensorStateClass | None, bool]:
    """Determine what type of sensor this state type should be.

    Returns:
        Tuple of (entity_type, device_class, unit, state_class, inverted)
        where entity_type is 'sensor', 'binary_sensor', or None
        and inverted indicates if binary sensor state should be inverted
    """
    display_name = state_type.get("displayName", "").lower()
    state_type_id = state_type.get("id", "")
    data_type = state_type.get("type", "").lower()

    # Check if it's a binary sensor (Bool type)
    if data_type == "bool":
        # Find matching binary sensor class
        for keyword, device_class in STATE_NAME_TO_BINARY_SENSOR_CLASS.items():
            if keyword in display_name:
                # "Closed" state should be inverted (True means closed, but HA door sensor True means open)
                inverted = keyword == "closed"
                return ("binary_sensor", device_class, None, None, inverted)
        # Default binary sensor with no specific class
        return ("binary_sensor", None, None, None, False)

    # Check if it's a regular sensor
    if data_type in ["int", "uint", "double", "string"]:
        device_class = None
        unit = None
        state_class = None

        # Determine device class from name
        for keyword, sensor_class in STATE_NAME_TO_SENSOR_CLASS.items():
            if keyword in display_name:
                device_class = sensor_class
                break

        # Determine unit and state class based on device class
        if device_class == SensorDeviceClass.TEMPERATURE:
            unit = UnitOfTemperature.CELSIUS
            state_class = SensorStateClass.MEASUREMENT
        elif device_class == SensorDeviceClass.HUMIDITY:
            unit = PERCENTAGE
            state_class = SensorStateClass.MEASUREMENT
        elif device_class == SensorDeviceClass.ATMOSPHERIC_PRESSURE:
            unit = UnitOfPressure.HPA
            state_class = SensorStateClass.MEASUREMENT
        elif (
            device_class == SensorDeviceClass.BATTERY
            or device_class == SensorDeviceClass.SIGNAL_STRENGTH
        ):
            unit = PERCENTAGE
            state_class = SensorStateClass.MEASUREMENT
        elif data_type in ["int", "uint", "double"]:
            # Numeric sensor without specific class
            state_class = SensorStateClass.MEASUREMENT

        # For string types, check if it should be an enum
        if data_type == "string" and "state" in display_name:
            device_class = SensorDeviceClass.ENUM

        return ("sensor", device_class, unit, state_class, False)

    # Unknown type
    return (None, None, None, None, False)


def should_create_entity(state_type: dict[str, Any]) -> bool:
    """Determine if an entity should be created for this state type.

    Some state types are internal or not suitable for entities.
    """
    display_name = state_type.get("displayName", "").lower()

    # Skip internal/diagnostic states that users don't need to see
    skip_keywords = [
        "update status",
        "update progress",
        "available version",
        "available firmware",
        "dfu progress",
        "firmware upgrade status",
    ]

    for keyword in skip_keywords:
        if keyword in display_name:
            return False

    return True


def generate_entities_for_thing_class(
    thing_class: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    """Generate entity configurations for a thing class.

    Returns:
        Dict with keys 'sensors', 'binary_sensors', 'switches', and 'buttons', each containing a list of
        entity configuration dicts.
    """
    thing_class_id = thing_class.get("id")
    thing_class_name = thing_class.get("displayName", "Unknown")
    state_types = thing_class.get("stateTypes", [])
    action_types = thing_class.get("actionTypes", [])

    sensors = []
    binary_sensors = []
    switches = []
    buttons = []

    # Check if this state type has controllable actions
    for state_type in state_types:
        if not should_create_entity(state_type):
            continue

        state_type_id = state_type.get("id")
        display_name = state_type.get("displayName", "").lower()
        data_type = state_type.get("type", "").lower()

        # Check if this is a controllable boolean state (switch)
        if data_type == "bool":
            # Look for corresponding action types (match by ID or similar name)
            matching_actions = [
                action for action in action_types
                if action.get("id") == state_type_id or
                action.get("name", "").lower() == display_name or
                ("switch " + display_name) in action.get("name", "").lower() or
                display_name in action.get("name", "").lower()
            ]

            # If we have actions to control this state, make it a switch
            # Skip certain read-only states that shouldn't be switches
            readonly_keywords = ["connected", "available", "reachable", "opened", "closed",
                                 "maintenance", "intruder", "interrupted", "barrier", "critical"]
            is_readonly = any(keyword in display_name for keyword in readonly_keywords)

            _LOGGER.debug(
                "Checking bool state '%s' (ID: %s) - matching_actions: %d, is_readonly: %s",
                display_name, state_type_id, len(matching_actions), is_readonly
            )

            if matching_actions and not is_readonly:
                # Prefer actions with different IDs (parameterized) over same ID (toggle)
                # Actions with parameters allow explicit on/off control
                parameterized_actions = [
                    action for action in matching_actions
                    if action.get("id") != state_type_id
                ]

                _LOGGER.warning(
                    "State '%s' (ID: %s) - Found %d matching actions, %d parameterized",
                    display_name, state_type_id, len(matching_actions), len(parameterized_actions)
                )
                _LOGGER.warning(
                    "Matching actions: %s",
                    [{"id": a.get("id"), "name": a.get("name", a.get("displayName"))}
                     for a in matching_actions]
                )

                if parameterized_actions:
                    # Use the parameterized action (different ID from state)
                    action_type_id = parameterized_actions[0].get("id")
                    _LOGGER.warning(
                        "Creating switch for '%s' with parameterized action ID: %s (state ID: %s)",
                        display_name, action_type_id, state_type_id
                    )
                else:
                    # Fall back to toggle action (same ID as state)
                    action_type_id = matching_actions[0].get("id")
                    _LOGGER.warning(
                        "Creating switch for '%s' with toggle action ID: %s (state ID: %s)",
                        display_name, action_type_id, state_type_id
                    )

                switches.append(
                    {
                        "thingclass_id": thing_class_id,
                        "thingclass_name": thing_class_name,
                        "state_type_id": state_type_id,
                        "action_type_id": action_type_id,
                        "name": state_type.get("displayName"),
                    }
                )
                continue  # Don't also create a binary sensor for this

        # Not a switch, determine sensor type
        entity_type, device_class, unit, state_class, inverted = determine_sensor_type(
            state_type
        )

        if entity_type == "sensor":
            sensors.append(
                {
                    "thingclass_id": thing_class_id,
                    "thingclass_name": thing_class_name,
                    "state_type_id": state_type.get("id"),
                    "name": state_type.get("displayName"),
                    "device_class": device_class,
                    "unit": unit,
                    "state_class": state_class,
                }
            )
        elif entity_type == "binary_sensor":
            binary_sensors.append(
                {
                    "thingclass_id": thing_class_id,
                    "thingclass_name": thing_class_name,
                    "state_type_id": state_type.get("id"),
                    "name": state_type.get("displayName"),
                    "device_class": device_class,
                    "inverted": inverted,
                }
            )

    # Generate buttons for specific action types (actions without state types)
    # Common actions that should be buttons
    button_action_keywords = [
        "intermediate",  # Intermediate position for garage doors
        "identify",      # Identify device (flash light)
        "check",         # Check firmware, etc.
        "connect",       # Manual connect
        "disconnect",    # Manual disconnect
    ]

    for action_type in action_types:
        action_id = action_type.get("id")
        action_name = action_type.get("name", "").lower()
        action_display_name = action_type.get("displayName", action_type.get("name", ""))

        # Skip actions that are already used as switches
        if any(s["action_type_id"] == action_id for s in switches):
            continue

        # Check if this action should be a button
        should_be_button = any(keyword in action_name for keyword in button_action_keywords)

        if should_be_button:
            _LOGGER.info(
                "Creating button for action '%s' (ID: %s) in thing class '%s'",
                action_display_name, action_id, thing_class_name
            )
            buttons.append(
                {
                    "thingclass_id": thing_class_id,
                    "thingclass_name": thing_class_name,
                    "action_type_id": action_id,
                    "name": action_display_name,
                }
            )

    _LOGGER.info(
        "Thing class '%s': Generated %d sensors, %d binary_sensors, %d switches, %d buttons",
        thing_class_name, len(sensors), len(binary_sensors), len(switches), len(buttons)
    )

    return {
        "sensors": sensors,
        "binary_sensors": binary_sensors,
        "switches": switches,
        "buttons": buttons,
    }
