---
name: dograh-ctl
description: >-
  Create and operate self-hosted Dograh voice agents through dograh-ctl (CLI + the dograh-ops
  MCP server). Use whenever the user wants a voice agent built, changed, published, given a phone
  number, tested, or called; wants a call placed or a transcript, recording, or latency read back;
  wants a model flipped (Gemini Live, OpenAI Realtime, etc.); or wants an outbound campaign created,
  started, paused, or watched. Triggers: "build me a voice agent that...", "make the agent say...",
  "publish the agent", "give it a number", "call me", "call +1...", "what did the last call say",
  "show call latency", "switch the model to...", "start the campaign". Do not use for installing or
  repairing a Dograh server itself (that is the dograh-setup skill) or for hand-editing workflow
  graphs node by node (use Dograh's own MCP server at /api/v1/mcp).
---

# dograh-ctl: create and operate voice agents

You are driving a self-hosted Dograh voice-agent platform through `dograh-ctl`. Two surfaces, same
verbs: the **dograh-ops MCP tools** (preferred when the server is registered) and the **CLI**
(`dograh-ctl ... --json`, run via Bash). Both read `DOGRAH_BASE_URL` and `DOGRAH_API_KEY` from the
environment. Never print, echo, or ask to paste the key. If they are missing, run
`/dograh-ctl-setup` (or tell the user to export them) before anything else.

## The lifecycle (do these in order)

| Step | MCP tool | CLI | Notes |
|---|---|---|---|
| 1. Create | `agents_create(use_case, description, call_type)` | `dograh-ctl agents create -u ... -d ... --json` | Dograh generates the agent (graph + prompt) from the use case. |
| 2. Prompt | `agents_set_prompt(agent_id, prompt)` | `agents set-prompt <id> "<prompt>"` | Replaces the prompt on every agentNode. Saves a DRAFT. |
| 3. Model (optional) | `agents_set_model(agent_id, realtime=..., llm=...)` | `agents set-model <id> --realtime provider/model` | Per-agent override; read-modify-write, secrets stay server-side. Saves a DRAFT. `models_show` shows the org default. |
| 4. Validate | `agents_validate(agent_id)` | `agents validate <id>` | Fix errors before publishing. |
| 5. Publish | `agents_publish(agent_id)` | `agents publish <id>` | **Required.** Edits are drafts; inbound production calls use the published version. |
| 6. Number | `numbers_add(number, agent_id)` or `numbers_assign(number, agent_id)` | `numbers add +E164 --agent <id>` | Buying a number is a carrier action (Twilio CLI); Dograh only registers it. `numbers_list` first. |
| 7. Test by text | `agents_chat(agent_id, message)` | `runs chat <id> -m "..."` | No telephony, no cost. Do this before any call. |
| 8. Call | `runs_trigger(agent_id, to)` | `runs trigger <id> --to +E164 --yes` | REAL call, REAL cost. Confirm with the user first. Returns the run id. |
| 9. Read back | `runs_transcript(run_id)`, `runs_list`, `runs_latency` | `runs transcript <run>`, `runs list`, `runs latency` | Transcript appears when the call ends. |

Campaigns: `campaigns_create(name, agent_id, csv_path)` (CSV with a `phone_number` column) ->
`campaigns_start(campaign_id)` (real calls; confirm) -> `campaigns_status` / CLI `campaigns watch <id>`
(live dashboard). `campaigns_pause` to stop dialing.

## Rules that keep this safe

- Anything that places calls or costs money (`runs_trigger`, `campaigns_start`) is destructive:
  state what will happen and get a yes before calling it. Never loop calls.
- Edits are drafts until `agents_publish`. If the user says "it is not picking up the change",
  check `agents_get` -> `version_status` and publish.
- Secrets: tools return masked or scrubbed config only. `keys_create`/`keys_revoke` and
  `numbers_remove` are CLI-only on purpose; ask the user to run them.
- Provider/model strings are `provider/model`, e.g. `google_realtime/gemini-3.1-flash-live-preview`,
  `openai_realtime/gpt-realtime-2`, `openai/gpt-4.1-mini`. `models_show` tells you the current mode
  (byok realtime vs pipeline); only services that exist in that mode can be set.
- `agents_set_prompt` targets the agentNode by default. Dograh's template keeps the persona in the
  globalNode, the greeting in startCall, and the goodbye in endCall: pass `node_type` (MCP) or
  `--node globalNode|startCall|endCall` (CLI, repeatable) to change those. Always `agents_publish`
  after. Prompt contract that avoids goodbye loops: agentNode says one goodbye then calls end_call;
  endCall is one line.
- Graph surgery (nodes, edges, tools attached to nodes) is Dograh's own MCP server
  (`{DOGRAH_BASE_URL}/api/v1/mcp`, same API key). Use it for structure; use dograh-ctl for everything
  around it.

## Using the CLI from Bash

Always pass `--json` and parse the result; exit code 2 means local config (env) problems, 1 means the
instance refused (the message says why). `dograh-ctl mcp-config` prints the MCP registration if you
need to install the server for the user. `dograh-ctl --help` lists all 33 commands.

## Example: "build me a call-in agent for my stream and call my phone"

1. `agents_create(use_case="stream call-in", description="Greet viewers, ask what they are building, keep it under two minutes", call_type="inbound")` -> id 7
2. `agents_set_prompt(7, "<the prompt the user approved>")`
3. `agents_validate(7)` -> ok; `agents_publish(7)` -> version 2
4. `numbers_list()` -> pick the stream number; `numbers_assign("+1313...", 7)`
5. `agents_chat(7, "hi, I am building a CLI")` -> read the reply, adjust the prompt if needed (then publish again)
6. Ask: "Place a real call from agent 7 to +1313...? It costs money." -> `runs_trigger(7, to="+1313...")` -> run 12
7. After the call: `runs_transcript(12)`, `runs_latency()`
