"""Config flow for nymea integration."""

from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant import config_entries, exceptions
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)

from .const import DOMAIN  # pylint:disable=unused-import
from .maveo_box import MaveoBox

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required("host", default="192.168.2.179"): str,
        vol.Required("port", default=2223): int,
    },
)


async def validate_input(hass: HomeAssistant, data: dict) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from DATA_SCHEMA with values provided by the user.
    """
    # Validate the data can be used to set up a connection.
    pattern = r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.[A-Za-z0-9-]{1,63})*$"
    if not re.match(pattern, data["host"]):
        raise InvalidHost

    hub = MaveoBox(hass, data["host"], data["port"])
    success = await hub.test_connection()
    if not success:
        # If there is an error, raise an exception to notify HA that there was a
        # problem. The UI will also show there was a problem
        raise CannotConnect

    return {"title": f"nymea({data['host']})"}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for nymea."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    def __init__(self) -> None:
        """Initialize the Hue flow."""
        self.data: dict[str, Any]

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
                self.data = user_input
                return await self.async_step_link()
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidHost:
                errors["host"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        # If there is no user input or there were errors, show the form again, including any errors that were found with the input.
        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )

    async def async_step_link(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Attempt to link with the nymea bridge.

        Given a configured host, will ask the user to press the link button
        to connect to the bridge.
        """
        if user_input is None:
            return self.async_show_form(step_id="link")

        box = MaveoBox(None, self.data["host"], self.data["port"])
        token = await box.init_connection()
        self.data["token"] = token

        return self.async_create_entry(
            title=f"nymea({self.data['host']})", data=self.data
        )


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidHost(exceptions.HomeAssistantError):
    """Error to indicate there is an invalid hostname."""
