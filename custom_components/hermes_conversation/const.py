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
