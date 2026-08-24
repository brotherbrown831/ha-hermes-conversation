"""Config flow for Hermes Conversation."""

from __future__ import annotations

import asyncio
from typing import Any

from aiohttp import ClientError
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .const import (
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_MODEL,
    CONF_TIMEOUT,
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT,
    DOMAIN,
)


class HermesConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Hermes Conversation."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await _validate_endpoint(self.hass, user_input)
            except asyncio.TimeoutError:
                errors["base"] = "timeout"
            except (ClientError, ValueError, HermesConfigError):
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(user_input[CONF_BASE_URL].rstrip("/"))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_MODEL], data=user_input
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_BASE_URL, default=DEFAULT_BASE_URL): str,
                vol.Required(CONF_API_KEY): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                vol.Required(CONF_MODEL, default=DEFAULT_MODEL): str,
                vol.Required(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.All(
                    int, vol.Range(min=5, max=300)
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)


class HermesConfigError(Exception):
    """Raised when Hermes returns an invalid response."""


async def _validate_endpoint(hass, data: dict[str, Any]) -> None:
    """Validate the endpoint and API key using model discovery."""
    session = async_get_clientsession(hass)
    headers = {"Authorization": f"Bearer {data[CONF_API_KEY]}"}
    async with session.get(
        f"{data[CONF_BASE_URL].rstrip('/')}/models",
        headers=headers,
        timeout=data[CONF_TIMEOUT],
    ) as response:
        if response.status != 200:
            raise HermesConfigError(f"Hermes returned HTTP {response.status}")
        payload = await response.json()
    if not isinstance(payload.get("data"), list):
        raise HermesConfigError("Hermes returned an invalid models response")
