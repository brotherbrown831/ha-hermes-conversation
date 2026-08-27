"""Hermes Conversation agent."""

from __future__ import annotations

import asyncio
from typing import Literal

from aiohttp import ClientError
from homeassistant.components import conversation
from homeassistant.const import MATCH_ALL
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import intent

from .const import CONF_MODEL, DOMAIN


class HermesConversationEntity(conversation.ConversationEntity):
    """Conversation entity that delegates the agent loop to Hermes."""

    _attr_should_poll = False
    _attr_supports_streaming = False

    def __init__(self, entry, config: dict) -> None:
        """Initialize the entity."""
        self.entry = entry
        self.config = config
        self._attr_name = entry.data[CONF_MODEL]
        self._attr_unique_id = entry.entry_id

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        """Return all supported languages."""
        return MATCH_ALL

    def _source_context(self, user_input: conversation.ConversationInput) -> str:
        """Resolve the source voice device's area into a short context prefix.

        HA sets ``user_input.device_id`` to the device that originated the
        request (e.g. the ESPHome voice satellite the user spoke to). Resolve
        that device to its area and return a compact prefix that tells the
        agent which room the user is in, so an unqualified request like
        "turn off the lights" can default to that room's devices. Returns an
        empty string when the source device or its area is unknown.
        """
        device_id = getattr(user_input, "device_id", None)
        if not device_id:
            return ""
        dev = dr.async_get(self.hass).async_get(device_id)
        if not dev or not dev.area_id:
            return ""
        area = ar.async_get(self.hass).async_get_area(dev.area_id)
        if not area or not area.name:
            return ""
        device_name = dev.name_by_user or dev.name or ""
        if device_name:
            return f'[Source area: {area.name}; device "{device_name}".] '
        return f"[Source area: {area.name}.] "

    async def _async_handle_message(
        self,
        user_input: conversation.ConversationInput,
        chat_log: conversation.ChatLog,
    ) -> conversation.ConversationResult:
        """Send only the current user text to Hermes, plus a source-area prefix."""
        session_id = user_input.conversation_id or f"ha-{self.entry.entry_id}"
        prefix = self._source_context(user_input)
        content = f"{prefix}{user_input.text}" if prefix else user_input.text
        headers = {
            "Authorization": f"Bearer {self.config['api_key']}",
            "Content-Type": "application/json",
            "X-Hermes-Session-Id": session_id,
            "X-Hermes-Session-Key": f"ha:{self.entry.entry_id}",
        }
        payload = {
            "model": self.entry.data[CONF_MODEL],
            "messages": [{"role": "user", "content": content}],
            "stream": False,
        }
        try:
            async with self.config["session"].post(
                f"{self.config['base_url']}/chat/completions",
                headers=headers,
                json=payload,
                timeout=self.config["timeout"],
            ) as response:
                response.raise_for_status()
                result = await response.json()
        except (asyncio.TimeoutError, ClientError, ValueError):
            return self._error_result(user_input, session_id)

        try:
            speech = result["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return self._error_result(user_input, session_id)
        if not isinstance(speech, str):
            return self._error_result(user_input, session_id)

        chat_log.async_add_assistant_content_without_tools(
            conversation.AssistantContent(agent_id=self.entity_id, content=speech)
        )
        response = intent.IntentResponse(language=user_input.language)
        response.async_set_speech(speech)
        return conversation.ConversationResult(
            response=response,
            conversation_id=user_input.conversation_id,
            continue_conversation=False,
        )

    @staticmethod
    def _error_result(
        user_input: conversation.ConversationInput,
        conversation_id: str,
    ) -> conversation.ConversationResult:
        """Return a user-safe conversation error without raising from the agent."""
        response = intent.IntentResponse(language=user_input.language)
        response.async_set_error(
            intent.IntentResponseErrorCode.UNKNOWN,
            "Hermes is unavailable right now.",
        )
        return conversation.ConversationResult(
            response=response,
            conversation_id=conversation_id,
            continue_conversation=False,
        )


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Set up the Hermes conversation entity."""
    config = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([HermesConversationEntity(entry, config)])
