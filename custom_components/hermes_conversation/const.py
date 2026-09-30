"""Constants for the Hermes Conversation integration."""

DOMAIN = "hermes_conversation"
CONF_BASE_URL = "base_url"
CONF_API_KEY = "api_key"
CONF_MODEL = "model"
CONF_TIMEOUT = "timeout"
DEFAULT_BASE_URL = "http://127.0.0.1:8642/v1"
DEFAULT_MODEL = "hermes-agent"
DEFAULT_TIMEOUT = 120

# Voice silence control token.
#
# The agent returns this instead of words when an utterance was not addressed to
# it (background conversation, TV/podcast/video audio, an overheard fragment).
# Home Assistant's Assist pipeline skips TTS entirely when the agent's speech is
# empty or whitespace-only (assist_pipeline/pipeline.py:
# `if all_targets_in_satellite_area or tts_input.strip(): ... else: # Skip TTS`),
# so an empty speech string makes the satellite stay silent and drop to idle.
# The token itself must never reach TTS, hence the conversion below.
SILENCE_TOKENS = frozenset({"<silence>", "[silence]", "<silent>"})


def is_silence_response(speech: str) -> bool:
    """True when the agent's reply means "say nothing".

    Covers whitespace-only replies and the explicit silence control token,
    case-insensitively, so a control marker is never spoken aloud.
    """
    stripped = speech.strip()
    return not stripped or stripped.lower() in SILENCE_TOKENS


def expects_reply(speech: str) -> bool:
    """True when the agent's reply asks the user something.

    Drives Home Assistant's continued conversation: a clarifying question must
    leave the microphone open so the answer needs no repeat wake word, while a
    statement ("Lights are on.") must end the turn. The ESPHome satellite
    re-opens the mic only when the agent returns continue_conversation=True
    (voice_assistant.cpp: on TTS end, `if (continue_conversation_)` ->
    START_MICROPHONE; otherwise -> IDLE) and drops the wake-word requirement for
    that follow-up run.
    """
    text = speech.strip().strip("\"'").strip()
    return text.endswith("?")
