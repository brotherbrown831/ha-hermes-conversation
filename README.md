# Home Assistant Hermes Conversation

A minimal Home Assistant conversation-agent integration for connecting Assist to a Hermes Agent OpenAI-compatible API.

## Project status

Early planning / MVP design. The first goal is a small, reliable conversation agent that lets Hermes own the agent harness instead of wrapping Hermes in a second Home Assistant LLM harness.

The current reference MVP uses Home Assistant's Local OpenAI LLM integration and a dedicated Hermes profile named `vexavoice`. That baseline works, but Home Assistant sends a large Assist-oriented developer prompt, entity inventory, and tool/context instructions. This project is intended to remove that duplication.

## Problem

Most Home Assistant OpenAI-compatible conversation integrations assume the remote endpoint is only an LLM provider. They prepare their own system prompt, entity context, tool definitions, and conversation history before calling the model.

Hermes Agent is different: its OpenAI-compatible API runs a complete agent runtime with its own system prompt, tools, memory, session handling, model/provider routing, and tool loop. Sending the normal HA payload creates two competing harnesses and unnecessary prompt overhead.

Observed reference behavior:

- HA-to-Hermes requests are approximately 2,500–2,600 input tokens before meaningful tool results.
- The reference request contains overlapping Hermes and Home Assistant instructions.
- The static HA entity context contains duplicate devices and long alias lists.
- OpenRouter prompt-cache reuse is approximately 99% after the first request, but the payload is still unnecessarily large and can grow with history.

## Design goal

Make Hermes the sole reasoning and agent harness:

```text
Home Assistant Assist
  ├── STT
  ├── conversation transport
  └── TTS
          │ text + stable session identity
          ▼
Hermes Agent API
  ├── system prompt
  ├── model/provider
  ├── memory
  ├── conversation continuity
  ├── tool loop
  └── approved Home Assistant actions
```

Home Assistant should send the current user text and stable conversation identity. It should not automatically send its full developer prompt, entity inventory, HA intent instructions, or a second set of tool definitions.

## Initial request shape

The intended minimal Chat Completions request is:

```json
{
  "model": "vexavoice",
  "messages": [
    {
      "role": "user",
      "content": "What is the outside temperature?"
    }
  ],
  "stream": true
}
```

The integration should forward session identity through Hermes headers when available:

```text
X-Hermes-Session-Id: <conversation-id>
X-Hermes-Session-Key: <stable-channel-or-device-id>
```

The Hermes API key is stored by Home Assistant as a config-entry secret and is sent only as:

```text
Authorization: Bearer <hermes-api-server-key>
```

The OpenRouter key remains inside Hermes and must never be configured in Home Assistant.

## MVP scope

- Config flow for endpoint URL, API key, and model name.
- Conversation-agent entity implementing Home Assistant's conversation API.
- OpenAI-compatible Chat Completions transport.
- Plain-text response extraction suitable for HA TTS.
- Stable Hermes session ID and session-key forwarding.
- Configurable request timeout.
- Basic connection validation against `/v1/models`.
- Clear error handling when Hermes is unavailable or returns an incompatible response.
- Optional streaming support after the basic non-streaming path is proven.
- Optional HA context mode, disabled by default, for cases where users intentionally want HA to provide context.

## Explicit non-goals for the first version

- Raw audio, STT, or TTS inside this integration.
- A second Home Assistant tool-calling loop.
- Automatic exposure of all HA entities.
- File, shell, browser, web, messaging, or administrative Hermes tools.
- Hermes profile management from Home Assistant.
- Provider-specific logic for OpenRouter, Anthropic, Gemini, or local model servers.
- Direct manipulation of locks or garage doors without an approved Hermes/HA safety boundary.

## Home Assistant control model

Conversation transport and home control are separate concerns. The integration should not assume that Hermes can safely control Home Assistant merely because the conversation endpoint works.

The preferred control design is:

```text
Hermes → restricted Home Assistant interface → approved HA script
```

Examples:

- `script.bedtime_routine`
- `script.secure_house`
- `script.goodnight_announcement`

Safety logic remains deterministic in Home Assistant. Hermes interprets natural language and selects an approved routine; it should not improvise individual lock or garage operations.

## Reference Hermes endpoint

The current development reference is a dedicated Hermes profile named `vexavoice`:

```text
Base URL: http://10.0.10.212:8643/v1
Model: vexavoice
```

Do not put real API keys in this repository. Use local secrets, Home Assistant config-entry storage, or a secret manager.

## Development plan

### Phase 0 — preserve the working baseline

Keep the existing Local OpenAI LLM integration available as a fallback. Do not replace the working VexaVoice pipeline until the new integration has been tested.

### Phase 1 — minimal conversation agent

Implement the smallest current-HA-compatible config flow and conversation entity. Send only the user text to a configurable OpenAI-compatible endpoint and return the assistant content.

Acceptance tests:

1. Add the integration through the HA UI.
2. Validate the Hermes endpoint and API key.
3. Process `What is your name?`.
4. Process `What is the outside temperature?` as a basic text request.
5. Return clean plain text to Home Assistant.
6. Report timeout and HTTP errors clearly.

### Phase 2 — continuity and streaming

Forward the HA conversation ID as Hermes session identity. Add streaming only after the non-streaming path is reliable. Verify that HA receives a complete TTS-safe response and that a multi-turn conversation does not duplicate or lose messages.

### Phase 3 — restricted Home Assistant control

Connect the `vexavoice` profile to a restricted Home Assistant MCP/tool interface or approved-action bridge. Test read-only state queries first, then harmless device actions, then approved routines. Keep locks and garage actions behind explicit confirmation and deterministic HA scripts.

### Phase 4 — efficiency and observability

Compare the custom integration to the Local OpenAI baseline:

- Input tokens
- Cached input tokens
- Output tokens
- Time to first token
- Total response latency
- Tool-call count
- Conversation-history growth
- TTS playback start time
- Response correctness

Add optional debug logging that records request sizes and timing without logging API keys or sensitive entity data by default.

## Security considerations

- Use bearer authentication for Hermes.
- Never commit API keys, tokens, or HA long-lived access tokens.
- Prefer firewalling the Hermes endpoint to the Home Assistant VM.
- The Hermes API server must not expose an unsandboxed general-purpose terminal to a broad network.
- Keep the initial HA-facing Hermes profile limited to the capabilities required for voice conversations.
- Treat entity names, states, presence, locks, cameras, vehicles, and alarms as potentially sensitive data.

## Related projects and references

- Hermes Agent: https://github.com/NousResearch/hermes-agent
- Hermes API server documentation: https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server
- Home Assistant conversation developer documentation: https://developers.home-assistant.io/docs/voice/intent-recognition/conversation/
- Current baseline integration: https://github.com/skye-harris/hass_local_openai_llm
- Current reference profile: `vexavoice`

## License

License to be selected before the first release.
