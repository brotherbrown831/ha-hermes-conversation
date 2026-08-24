# Continuation Notes

Updated: 2026-08-24

## Project

Repository: https://github.com/brotherbrown831/ha-hermes-conversation
Local path:

```text
/home/nolan/.hermes/profiles/vexa/workspace/ha-hermes-conversation
```

Branch: `main`
Latest commit before this documentation update: `d3196bc fix: handle Hermes request timeouts`

## Current objective

Build a minimal Home Assistant conversation integration that sends user text to a dedicated Hermes profile (`vexavoice`). Home Assistant owns Assist/STT/TTS and conversation transport. Hermes owns the system prompt, model/provider, session continuity, reasoning, and future tools.

The design goal is deliberately narrow: VV (short name for VexaVoice) should receive minimal request context and retrieve household information on demand. Do not send bulk entity state or the full Home Assistant developer prompt.

## Current Home Assistant deployment

Home Assistant:

- Host: `10.0.10.117:8123`
- Current observed version: Core `2026.8.3`, OS `18.2`
- HACS: `2.0.5`
- Existing fallback integration: `local_openai`, title `VexaVoice`, loaded
- Existing fallback conversation entity: `conversation.vexavoice_vexavoice_ai_agent`

The new integration was installed through HACS:

- Repository: `brotherbrown831/ha-hermes-conversation`
- Domain: `hermes_conversation`
- Installed version/commit: `d3196bc`
- Config entry title: `vexavoice`
- Config entry ID: `01M0T7T5TKFFVRV8S357YBC6YZ`
- Conversation entity: `conversation.vexavoice`
- Config entry state: loaded

The original `local_openai` integration remains loaded and untouched.

## Assist pipeline

A separate pipeline exists:

- Name: `Hermes VexaVoice`
- Pipeline ID: `01m0t8txqfvvdg43vztfecxnx0`
- Conversation engine: `conversation.vexavoice`
- STT: `stt.home_assistant_cloud`
- TTS: `tts.home_assistant_cloud`
- TTS voice: `AmberNeural`
- It was set as the preferred Assist pipeline on 2026-08-24 at the user’s request.

Other pipelines, including the original VexaVoice pipeline, still exist.

Voice PE hardware cannot be tested until Nolan returns home. HA Chat/service tests are available.

## Hermes VV profile

Profile path:

```text
/home/nolan/.hermes/profiles/vexavoice
```

API endpoint:

```text
http://10.0.10.212:8643/v1
```

Model advertised to HA: `vexavoice`
Model/provider: `openai/gpt-5.6-luna` via OpenRouter
Systemd service:

```text
hermes-gateway-vexavoice.service
```

Restart command (must be run from a separate shell, not inside the gateway chat):

```bash
systemctl --user restart hermes-gateway-vexavoice.service
```

Verify:

```bash
systemctl --user is-active hermes-gateway-vexavoice.service
```

Current observed service state after the latest user restart: active, PID `23481` at the time of inspection; PID may change after future restarts.

## VV privacy and memory design

Hindsight long-term memory is disabled for VV:

```yaml
memory:
  memory_enabled: false
  user_profile_enabled: false
```

This avoids recall latency and prevents unrelated personal context from entering household voice requests.

VV should receive only:

- Current user text
- Conversation ID
- Current date/time
- Source device
- Source room, when available

A tiny static identity block may contain Nolan’s name, VV’s role, concise response preference, and safety rules. Stable identity facts should be hardcoded in the focused prompt rather than retrieved through Hindsight.

## Current VV tool status

VV currently has no installed custom skills. The profile skills directory contains only `.curator_state`.

The VV API tool configuration was initially empty:

```yaml
platform_toolsets:
  api_server: []
```

An attempt was made to connect the raw `ha_mcp` server and allow only two tools using:

```yaml
platform_toolsets:
  api_server:
    - ha_mcp:ha_search
    - ha_mcp:ha_get_state
```

However, Hermes resolves the MCP server-level entry and reported:

```text
ha_mcp  all tools enabled
```

Therefore, this syntax must not be treated as an individual MCP-tool allowlist. Do not expose the raw `ha_mcp` server to VV.

The VV profile currently contains this experimental configuration, but it should be replaced with a dedicated adapter before enabling tools in production:

```yaml
mcp_servers:
  ha_mcp:
    url: http://10.0.10.117:9583/private_LPmUT6H-6386DjXEZHJybA
    timeout: 30
    connect_timeout: 15
platform_toolsets:
  api_server:
    - ha_mcp:ha_search
    - ha_mcp:ha_get_state
```

## Recommended next implementation

Build a small adapter MCP server, ideally on the Hermes VM, that exposes only purpose-built tools to VV:

1. `find_home_entities`
   - Search Home Assistant by name/room
   - Return only a small number of matching entity IDs, names, domains, and rooms
   - Never return the full inventory

2. `read_home_state`
   - Accept specific entity IDs returned by the search tool
   - Return only current state and necessary attributes
   - No history and no bulk reads

Later, after read-only operation is proven:

3. `run_approved_routine`
   - Allow only a fixed script allowlist such as `script.good_morning`, `script.bedtime_routine`, `script.leave_home`, `script.movie_mode`, `script.secure_house`, and `script.goodnight_announcement`
   - Do not expose generic `call_service`
   - Do not expose direct lock or garage operations

The adapter should call Home Assistant directly using a dedicated long-lived HA token stored outside Git. VV should see only the adapter’s small tool schemas, not the raw `ha_mcp` catalog.

## What has been verified

- Current source reviewed against a cloned current Home Assistant core tree.
- Timeout handling fixed in `conversation.py`: catches `asyncio.TimeoutError`, `aiohttp.ClientError`, and JSON `ValueError` and returns a safe unavailable response.
- Python compilation passed.
- Contract tests passed: `6 passed in 0.01s`.
- HACS custom repository added successfully.
- HACS installation succeeded.
- HA configuration check passed before restart.
- Home Assistant restarted successfully.
- New integration loaded alongside `local_openai`.
- HA service test through `conversation.vexavoice` returned `I’m Vexa.` for “What is your name?”
- HA service test with conversation ID `ha-test-001` successfully forwarded the ID.
- Assist pipeline test through the new Hermes pipeline returned `I’m Vexa.`
- The new pipeline was made preferred at user request.
- “What is the outside temperature?” correctly demonstrated the current limitation: VV cannot answer household-state questions without tools/context.
- The user inspected the OpenRouter developer prompt and found it substantially smaller and more efficient than the old HA-wrapped prompt.

## Important prompt cleanup still needed

The current OpenRouter developer prompt still includes generic Hermes material that VV does not need:

- Hermes documentation URL and `skill_view` instructions
- Linux host/kernel details
- Home directory and profile filesystem paths
- API rendering and MEDIA/file-delivery instructions
- Model/provider/platform metadata
- A malformed profile path containing `/profiles/vexavoice/profiles/vexavoice/`

The target is a tiny VV-specific prompt plus minimal per-request metadata. Prompt cleanup should be done after the adapter boundary is established or as a separate controlled change.

## Security and operational notes

- The VV API server currently binds to `0.0.0.0:8643` and has a local unsandboxed terminal backend in the profile environment. Prompt instructions are not a hard security boundary.
- Before production, restrict effective VV API tools to the adapter only and firewall port 8643 to the HA VM (`10.0.10.117`) or use a safer loopback/Tailscale arrangement.
- Never commit Hermes API keys, OpenRouter keys, HA tokens, or Telegram tokens.
- Existing `local_openai` is the rollback path. Do not delete or modify it while iterating.
- One scoped change at a time.
- Voice PE testing is deferred until Nolan is home.

## Repository files

The custom component currently contains:

```text
README.md
CONTINUATION.md
.gitignore
hacs.json
custom_components/hermes_conversation/__init__.py
custom_components/hermes_conversation/config_flow.py
custom_components/hermes_conversation/const.py
custom_components/hermes_conversation/conversation.py
custom_components/hermes_conversation/manifest.json
custom_components/hermes_conversation/strings.json
tests/test_contract.py
```

## Useful validation commands

From the repository:

```bash
python3 -m compileall -q custom_components tests
python3 -m pytest -q
```

Expected current result before adapter work: 6 passing contract tests.

## Current handoff state

The user asked to preserve the current status in Git in case the chat session is lost. This document is the source of truth for resuming.

Immediate next step: implement and test the dedicated two-tool Home Assistant adapter, then configure VV to use only that adapter. Do not add raw `ha_mcp`, Hindsight, broad skills, or direct write tools.

(◕‿◕)★
_\n"}⁨