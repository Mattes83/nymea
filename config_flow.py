"""Config flow for nymea integration."""

from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant import config_entries, exceptions
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TOKEN
from homeassistant.core import HomeAssistant

from .const import DOMAIN  # pylint:disable=unused-import
from .maveo_box import MaveoBox

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default="192.168.2.179"): str,
        vol.Required(CONF_PORT, default=2223): int,
    },
)


async def validate_input(hass: HomeAssistant, data: dict):
    """Validate the user input allows us to connect.

    Data has the keys from DATA_SCHEMA with values provided by the user.
    """
    # Validate the data can be used to set up a connection.
    pattern = r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.[A-Za-z0-9-]{1,63})*$"
    if not re.match(pattern, data[CONF_HOST]):
        raise InvalidHost

    hub = MaveoBox(hass, data[CONF_HOST], data[CONF_PORT])
    success = await hub.test_connection()
    if not success:
        # If there is an error, raise an exception to notify HA that there was a
        # problem. The UI will also show there was a problem
        raise CannotConnect


class NymeaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a nymea config."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the nymea config flow."""
        self.data: dict[str, Any]

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            try:
                await validate_input(self.hass, user_input)
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

        box = MaveoBox(None, self.data[CONF_HOST], self.data[CONF_PORT])
        token = await box.init_connection()
        self.data[CONF_TOKEN] = token

        return self.async_create_entry(
            title=f"nymea({self.data[CONF_HOST]})", data=self.data
        )


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidHost(exceptions.HomeAssistantError):
    """Error to indicate there is an invalid hostname."""
