# Continuation Notes

Updated: 2026-08-24

## Project

Repository: https://github.com/brotherbrown831/ha-hermes-conversation
Local path on the Hermes VM:

```text
/home/nolan/.hermes/profiles/vexa/workspace/ha-hermes-conversation
```

Current branch: `main`
Latest published commits:

```text
24756b4 feat: add minimal Hermes conversation agent
8df4001 docs: add project plan and architecture
```

The working tree was clean after the last push.

## Goal

Build a dedicated Home Assistant conversation-agent integration for Hermes Agent. Home Assistant should provide STT, TTS, and conversation transport. Hermes should be the sole agent harness: system prompt, model/provider, session continuity, memory, reasoning, tools, and final response.

The current HA LLM integrations wrap Hermes in a second agent harness. They send a large HA developer prompt, entity inventory, HA intent instructions, tool definitions, and possibly history. This creates duplicated instructions and token overhead.

Desired architecture:

```text
HA Assist/STT
  -> minimal Hermes Conversation integration
  -> Hermes OpenAI-compatible API
  -> Hermes owns agent loop/tools/session
  -> plain text response
  -> HA TTS
```

## Current working baseline

A separate profile named `vexavoice` is already running on the Hermes VM at `10.0.10.212`.

Endpoint:

```text
http://10.0.10.212:8643/v1
```

Model advertised by `/v1/models`:

```text
vexavoice
```

Profile model/provider:

```text
openai/gpt-5.6-luna via OpenRouter
```

The endpoint was verified:

- `/health` returns HTTP 200
- unauthenticated `/v1/models` returns HTTP 401
- authenticated `/v1/models` returns HTTP 200 and advertises `vexavoice`
- API server is bound to `0.0.0.0:8643`
- systemd service `hermes-gateway-vexavoice.service` is enabled/running
- no Telegram bot is configured for this profile

The Hermes API key is stored only in the local vexavoice `.env` and must not be committed or repeated. The OpenRouter key is also only inside the Hermes profile and must never be sent to Home Assistant.

## Home Assistant state

HA instance: `10.0.10.117:8123`, HA OS 2026.7.1 according to persistent notes.

Installed and working baseline integration:

```text
skye-harris/hass_local_openai_llm
version 1.11.1
```

HA config entry:

```text
Integration: local_openai
Title: VexaVoice
State: loaded
Conversation entity: conversation.vexavoice_vexavoice_ai_agent
```

Dedicated HA Assist pipeline exists:

```text
Name: VexaVoice
Conversation engine: conversation.vexavoice_vexavoice_ai_agent
STT: stt.home_assistant_cloud
TTS: tts.home_assistant_cloud
TTS voice: AmberNeural
```

It is not the preferred/global pipeline; SkippyV2 remains preferred. The user is currently out of town and does not want to focus on Voice PE hardware or device assignment. Focus is the conversation pipeline, prompt payload, and efficiency.

Existing HA `extended_openai_conversation` was installed through HACS but is not usable: its 2.0.2 release requires `openai~=2.21.0`, which HA cannot satisfy. HACS rejects the upstream development version 3.0.0 as not usable by HACS. Do not force the old OpenAI dependency into HA.

## What the captured HA payload showed

The user supplied a complete OpenRouter developer prompt captured from the working HA request. It is saved locally at:

```text
/home/nolan/.hermes/profiles/vexa/cache/documents/doc_e7d7e2aae0b1_Untitled document.txt
```

It is JSON with:

```json
{"role":"developer","content":"..."}
```

Measured size:

```text
10,416 characters in the decoded content
approximately 2,600 tokens
```

The payload has two layers:

1. Hermes/Vexa-Voice instructions and generic Hermes runtime context.
2. Home Assistant Assist instructions and static device context.

The first layer includes irrelevant generic runtime material:

- Hermes documentation URL and `skill_view` instructions
- Linux host/kernel information
- `/home/nolan` and working-directory details
- profile filesystem paths, including a malformed path containing `/profiles/vexavoice/profiles/vexavoice/`
- API rendering and MEDIA/file-delivery instructions
- model/provider/platform metadata

The HA layer includes:

- instructions to use `GetLiveContext`
- static context listing about 59 entity/device entries
- entity names, domains, areas, and long aliases
- duplicate entries, including repeated fuge light, patio light, and master bedroom fan entries
- aquarium equipment, person entities, TVs, diagnostic sensors, and other devices not needed for a voice MVP
- conflicting instructions such as Hermes saying only approved capabilities while HA says to use intent tools such as `HassTurnOn`/`HassTurnOff`

Approximate entity-context size:

```text
~5,922 characters / ~1,480 tokens
```

## Hermes API/session observations

The vexavoice Hermes session API showed a session:

```text
api-d444179534419e9d
source: api_server
message_count: 6
api_calls: 3
```

Three baseline calls arrived from HA at `10.0.10.117` using AsyncOpenAI/Python 2.45.0:

| User input | Hermes input | output | latency | cache |
|---|---:|---:|---:|---:|
| hello | 2521 | 13 | 1.9s | first request |
| tell me a joke | 2544 | 21 | 1.9s | 2518/2544 (~99%) |
| what is the temp of the sun? | 2579 | 69 | 3.0s | 2541/2579 (~99%) |

No Hermes tools were called in those tests.

Hermes logs contain request summaries, not the full expanded HA prompt. The session DB stores prompt hash and token/caching metadata, not the complete system prompt. The captured OpenRouter request is therefore the source of truth for payload analysis.

Vexavoice session DB had one session at last inspection; the API server request created it. The actual messages were `hello`, `tell me a joke`, and `what is the temp of the sun?` with assistant responses. The session record reported input tokens 9 at the aggregate user-message field but provider calls had approximately 2.5K input tokens each; do not confuse those fields.

## Current repository contents

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

The initial implementation is a dependency-free, non-streaming MVP:

- config flow fields: base URL, API key, model, timeout
- validates `GET /v1/models`
- sends only the current user text in a Chat Completions request
- forwards `X-Hermes-Session-Id` and `X-Hermes-Session-Key`
- extracts `choices[0].message.content`
- returns an HA `ConversationResult`
- adds a plain assistant message to HA's chat log
- returns a generic safe error response on network/format errors
- no HA entity inventory, HA developer prompt, or HA tool loop by default
- no streaming yet

Minimal intended request:

```json
{
  "model": "vexavoice",
  "messages": [
    {"role": "user", "content": "What is the outside temperature?"}
  ],
  "stream": false
}
```

Headers:

```text
Authorization: Bearer <Hermes API_SERVER_KEY>
X-Hermes-Session-Id: <HA conversation ID or fallback>
X-Hermes-Session-Key: ha:<config-entry-id>
```

## Validation already completed

- Cloned current Home Assistant core into `/tmp/ha-core-current` and inspected current conversation models/entity APIs.
- Cloned current `skye-harris/hass_local_openai_llm` into `/tmp/local-openai-current` and inspected its current implementation.
- Python syntax compilation passed for all 5 Python files (4 integration files + test file).
- JSON parsing passed for `manifest.json` and `strings.json`.
- Dependency-free pytest contract tests passed:

```text
6 passed in 0.01s
```

- GitHub repository exists and is reachable.
- Changes were committed and pushed successfully.

## Important correction still needed

The initial source was written using current HA APIs but has not yet been installed into a real HA config directory. Before publishing a new version, test it in Home Assistant or against a proper HA custom-component test harness.

Potential follow-up checks:

- Confirm `hass.config_entries.async_forward_entry_setups()` works with the selected `PLATFORMS` shape.
- Confirm config flow `async_set_unique_id()` and duplicate handling.
- Confirm `conversation.ConverseError` handling behavior for all current HA versions.
- Confirm `ConversationEntity` `entity_id` is available when assistant content is appended.
- Confirm state restoration and HA chat-log behavior.
- Confirm the error result does not leak exception details.
- Add an official `translations/en.json` if HA requires it for the current flow.
- Add tests with mocked `HomeAssistant`, config entries, `ConversationInput`, and `ChatLog`.
- Test a real request against `http://10.0.10.212:8643/v1/chat/completions` using a test-only key/config, without committing credentials.

## Next implementation sequence

1. Review/fix the initial code against current HA core APIs.
2. Add a small mocked unit-test suite for config flow and conversation processing.
3. Run static validation, formatting, and tests.
4. Test the request shape against the live vexavoice API endpoint.
5. Commit/push the next version.
6. Install it alongside `local_openai` in HA as a separate test integration.
7. Test HA Chat with `What is your name?` and `What is the outside temperature?`.
8. Compare prompt tokens, cache rate, latency, response correctness, and conversation continuity against the baseline.
9. Add streaming only after non-streaming is stable.
10. Add restricted Home Assistant control separately through selected state reads and approved scripts.

## Architecture decisions

- Hermes is the sole reasoning/agent harness.
- HA is STT, TTS, transport, and conversation-agent registration.
- Do not combine HA's tool loop with Hermes's tool loop by default.
- Do not expose all ~932 HA entities.
- Use approved HA scripts for risky actions such as locks and garage control.
- Preserve `local_openai` as a fallback until the new integration is tested.
- Keep each change scoped and measurable.
- Do not commit secrets.

## Security concerns

The `vexavoice` API server currently binds to `0.0.0.0:8643` with a local unsandboxed terminal backend. Prompt instructions saying not to use shell/file tools are not a hard security boundary. Before production, restrict the actual API toolset and firewall port 8643 to HA VM `10.0.10.117` only. The current MVP work has not changed that configuration.

## User preferences

- One scoped change at a time.
- Preserve working baselines and make rollback easy.
- User is out of town: do not focus on Voice PE hardware right now.
- Focus on the conversation pipeline, payload, prompt efficiency, and measurements.
- Use current Home Assistant documentation/source when checking compatibility.
- Use Luna for initial coding; use a stronger model only for difficult HA compatibility review.
- User prefers direct, concise reporting.

## Useful commands

From the repository:

```text
python3 -m compileall -q custom_components
python3 -m pytest -q tests/test_contract.py
```

From the Hermes VM, inspect the endpoint without printing secrets:

```text
curl -sS http://127.0.0.1:8643/health
curl -sS -H 'Authorization: Bearer <key>' http://127.0.0.1:8643/v1/models
```

Profile logs:

```text
/home/nolan/.hermes/profiles/vexavoice/logs/agent.log
/home/nolan/.hermes/profiles/vexavoice/logs/gateway.log
/home/nolan/.hermes/profiles/vexavoice/logs/errors.log
```

Do not use the Hermes CLI from inside the running gateway to restart itself; the environment blocks that operation. Use a separate shell for gateway restarts.

## Immediate next action in a fresh conversation

Read this file, inspect the current repository state, then review the initial integration implementation against the current Home Assistant source before adding more features. Do not alter the working HA `local_openai` baseline.

The initial code is intentionally only a starting point. Treat real Home Assistant execution as required before claiming the integration is complete.

## Secret handling note

The Hermes API key and OpenRouter key were pasted in chat earlier and should be rotated before production. Do not place either key in GitHub, README files, tests, or continuation notes.

## Current task state at handoff

The repository contains the initial integration and tests. The implementation and tests were completed locally and the repository was pushed, but real Home Assistant installation testing has not yet been performed. Continue from API review and mocked HA tests.

## Last verified repository status

```text
branch: main
working tree: clean
latest commit: 24756b4
```

After adding this file, commit and push it before ending the session.

## Handoff checklist

- [ ] Fresh conversation reads `CONTINUATION.md`.
- [ ] Review current code against current HA core.
- [ ] Add real/mock HA tests.
- [ ] Run tests.
- [ ] Install/test in HA without replacing the working baseline.
- [ ] Add streaming only after basic path passes.
- [ ] Restrict Hermes tools/firewall before production.
- [ ] Rotate exposed Hermes API key before production.

## License

Do not choose a final license until the first release design is settled.

## Note on the generated code

The current MVP source was created quickly to establish the interface. It should be treated as prototype code until current HA execution tests pass. In particular, review error handling and config-entry lifecycle before using it as a production HACS package.

## Final resume instruction

Continue from the repository, not from memory. Read `README.md`, then this file, inspect the current branch and tests, and use live HA/Hermes behavior to verify each claim. Keep the existing working `local_openai` VexaVoice integration untouched while developing the separate Hermes Conversation component.

(◕‿◕)★
");
}
print("wrote", p)
print("chars", len(p.read_text()))
print("lines", len(p.read_text().splitlines()))
print("--- trailer ---")
print("\n".join(p.read_text().splitlines()[-12:]))
'}]}цҳа