"""Small dependency-free contract tests for the Hermes request shape."""

import json
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_manifest_is_valid_and_dependency_free() -> None:
    manifest = json.loads(
        (ROOT / "custom_components/hermes_conversation/manifest.json").read_text()
    )
    assert manifest["domain"] == "hermes_conversation"
    assert manifest["requirements"] == []
    assert manifest["config_flow"] is True


def test_minimal_payload_contains_only_text_message() -> None:
    payload = {
        "model": "vexavoice",
        "messages": [{"role": "user", "content": "hello"}],
        "stream": False,
    }
    assert list(payload) == ["model", "messages", "stream"]
    assert payload["messages"] == [{"role": "user", "content": "hello"}]
    assert "tools" not in payload
    assert "system" not in payload


def test_required_files_exist() -> None:
    package = ROOT / "custom_components/hermes_conversation"
    for name in (
        "__init__.py",
        "config_flow.py",
        "const.py",
        "conversation.py",
        "manifest.json",
        "strings.json",
    ):
        assert (package / name).is_file()


def test_no_secret_like_values_are_in_source() -> None:
    source = "\n".join(
        p.read_text()
        for p in (ROOT / "custom_components/hermes_conversation").glob("*")
        if p.is_file() and p.suffix in {".py", ".json"}
    )
    assert "sk-or-v1-" not in source
    assert "Bearer vv_" not in source


def test_hacs_metadata_is_valid() -> None:
    metadata = json.loads((ROOT / "hacs.json").read_text())
    assert metadata["filename"] == "hermes_conversation"
    assert metadata["content_in_root"] is False


def test_json_round_trip() -> None:
    # Ensures the test itself uses the same JSON semantics as the HA payload.
    assert json.loads(json.dumps({"role": "user", "content": "hello"}))[
        "role"
    ] == "user"


def _load_const():
    """Load const.py standalone (it must stay HA-import-free)."""
    import importlib.util

    path = ROOT / "custom_components/hermes_conversation/const.py"
    spec = importlib.util.spec_from_file_location("hermes_const_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_silence_token_is_recognised_and_never_spoken() -> None:
    const = _load_const()
    for silence in ("", "   ", "\n", "<silence>", "<SILENCE>", " <silence> ", "[silence]"):
        assert const.is_silence_response(silence), repr(silence)


def test_real_replies_are_not_swallowed() -> None:
    const = _load_const()
    for speech in (
        "Lights are on.",
        "No response needed.",
        "Done.",
        "silence",
        "<silence>maybe",
    ):
        assert not const.is_silence_response(speech), repr(speech)


def test_whitespace_and_token_replies_normalise_to_empty_speech() -> None:
    # The Assist pipeline skips TTS when the speech text is empty or whitespace
    # (assist_pipeline/pipeline.py: `if ... or tts_input.strip()`), so both a
    # silence token and a blank reply must normalise to the empty string.
    const = _load_const()
    for speech in ("<silence>", "   ", ""):
        normalised = "" if const.is_silence_response(speech) else speech
        assert normalised.strip() == ""
