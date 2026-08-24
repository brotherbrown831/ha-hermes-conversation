"""Hermes Conversation integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_API_KEY, CONF_BASE_URL, CONF_TIMEOUT, DOMAIN

PLATFORMS = [Platform.CONVERSATION]




async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a Hermes Conversation config entry."""
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "session": async_get_clientsession(hass),
        "base_url": entry.data[CONF_BASE_URL].rstrip("/"),
        "api_key": entry.data[CONF_API_KEY],
        "timeout": entry.data[CONF_TIMEOUT],
    }
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Hermes Conversation config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
