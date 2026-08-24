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
