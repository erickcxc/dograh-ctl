"""serve: the operations MCP server (agent-first).

Exposes dograh-ctl's verbs as MCP tools over stdio so an agent (Claude Code, any MCP client) can
create AND operate voice agents on a self-hosted Dograh instance through the same client and
helpers the CLI uses. Graph surgery (editing nodes and edges by hand) stays with Dograh's own MCP
server at /api/v1/mcp; this one drives the lifecycle.

Rules that keep it safe for an agent:
- Tools return dicts/lists and print nothing on stdout (stdio is the transport).
- Reads are read_only_hint=True; writes are idempotent, not destructive; the two tools that place
  real phone calls (runs_trigger, campaigns_start) are destructive_hint=True so clients confirm.
- Secrets never leave the server: api_key and friends are stripped from every payload, even masked.
- Key minting/revoking and number removal are deliberately NOT tools (CLI-only, with --yes).
- Every write returns a "next" hint so the agent knows the following step of the recipe.
"""

from __future__ import annotations

import pathlib
from typing import Any, Optional

import typer
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from .client import DograhClient
from .commands import agents as agents_cmd
from .commands import campaigns as campaigns_cmd
from .commands import models as models_cmd
from .commands import numbers as numbers_cmd
from .commands import runs as runs_cmd
from .stats import latency_summary

READ = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=True
)
WRITE = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=True
)
CALL = ToolAnnotations(
    read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=True
)

SECRET_KEYS = {
    "api_key",
    "auth_token",
    "api_secret",
    "credentials",
    "aws_access_key",
    "aws_secret_key",
}

INSTRUCTIONS = (
    "Create and operate voice agents on a self-hosted Dograh instance. The recipe: "
    "agents_create -> agents_set_prompt -> agents_set_model (optional) -> agents_validate -> "
    "agents_publish -> numbers_add or numbers_assign (route a phone number) -> agents_chat to "
    "test without telephony -> runs_trigger to place a real call (confirm with the user first, it "
    "costs money) -> runs_transcript and runs_latency to read what happened. Campaigns: "
    "campaigns_create from a CSV with a phone_number column -> campaigns_start (real calls, "
    "confirm first) -> campaigns_list / campaigns_pause. Edits to an agent are drafts until "
    "agents_publish. For graph surgery (nodes and edges) use Dograh's own MCP server at "
    "{DOGRAH_BASE_URL}/api/v1/mcp. API keys are never created or revoked from here."
)


def scrub(value: Any) -> Any:
    """Drop secret-bearing keys anywhere in a payload (masked or not)."""
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items() if k not in SECRET_KEYS}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


def _run(fn):
    """Call a CLI helper; turn its exit-style failures into a tool error with a message."""
    try:
        return fn()
    except typer.Exit as exc:  # helpers already wrote the reason to stderr
        raise RuntimeError(f"command refused (exit {exc.exit_code}); see server log") from None


def _agent_summary(wf: dict) -> dict:
    nodes = (wf.get("workflow_definition") or {}).get("nodes") or []
    counts: dict = {}
    for n in nodes:
        counts[n.get("type", "?")] = counts.get(n.get("type", "?"), 0) + 1
    override = (wf.get("workflow_configurations") or {}).get(agents_cmd.OVERRIDE_KEY)
    return {
        "id": wf.get("id"),
        "name": wf.get("name"),
        "status": wf.get("status"),
        "version_number": wf.get("version_number"),
        "version_status": wf.get("version_status"),
        "nodes": counts,
        "model_override": agents_cmd._model_summary(override),
        "workflow_uuid": wf.get("workflow_uuid"),
        "total_runs": wf.get("total_runs"),
    }


def build_server() -> MCPServer:
    server = MCPServer(
        name="dograh-ops",
        # WARNING level: nothing chatty may reach stdout (the stdio transport).
        log_level="WARNING",
        instructions=INSTRUCTIONS,
    )

    # --- agents: read --------------------------------------------------------------------
    @server.tool(annotations=READ)
    def agents_list() -> list:
        """List the voice agents (workflows): id, name, status, total runs, uuid."""
        client = DograhClient()
        return [
            {
                "id": w.get("id"),
                "name": w.get("name"),
                "status": w.get("status"),
                "total_runs": w.get("total_runs", 0),
                "workflow_uuid": w.get("workflow_uuid"),
                "created_at": w.get("created_at"),
            }
            for w in client.get("/api/v1/workflow/fetch") or []
        ]

    @server.tool(annotations=READ)
    def agents_get(agent_id: int) -> dict:
        """One agent: status, version, node summary, model override (providers/models only)."""
        client = DograhClient()
        return _agent_summary(client.get(f"/api/v1/workflow/fetch/{agent_id}"))

    @server.tool(annotations=READ)
    def agents_validate(agent_id: int) -> dict:
        """Validate the agent's current draft graph; returns valid + errors."""
        client = DograhClient()
        result = client.post(f"/api/v1/workflow/{agent_id}/validate") or {}
        return scrub(result) | {
            "next": "agents_publish to make it live"
            if result.get("valid", True) and not result.get("errors")
            else (
                "fix the listed errors (agents_set_prompt, or Dograh's MCP for graph edits), "
                "then validate again"
            )
        }

    # --- agents: lifecycle writes --------------------------------------------------------
    @server.tool(annotations=WRITE)
    def agents_create(use_case: str, description: str, call_type: str = "inbound") -> dict:
        """Create a voice agent from a use case + description (Dograh generates the graph)."""
        client = DograhClient()
        ct = "inbound" if call_type.lower().startswith("in") else "outbound"
        wf = (
            client.post(
                "/api/v1/workflow/create/template",
                json={"call_type": ct, "use_case": use_case, "activity_description": description},
            )
            or {}
        )
        return _agent_summary(wf) | {
            "next": (
                "set the exact prompt with agents_set_prompt, optionally agents_set_model, then "
                "agents_validate and agents_publish; test with agents_chat"
            )
        }

    @server.tool(annotations=WRITE)
    def agents_set_prompt(agent_id: int, prompt: str) -> dict:
        """Replace the prompt on every agentNode (saved as a draft; publish to go live)."""
        client = DograhClient()
        try:
            result = agents_cmd.update_prompt(client, agent_id, prompt)
        except ValueError as exc:
            raise RuntimeError(str(exc)) from None
        return {
            "agent_id": agent_id,
            "result": scrub(result),
            "next": (
                "agents_validate, then agents_publish "
                "(production calls still use the published version)"
            ),
        }

    @server.tool(annotations=WRITE)
    def agents_set_model(
        agent_id: int,
        realtime: Optional[str] = None,
        llm: Optional[str] = None,
        tts: Optional[str] = None,
        stt: Optional[str] = None,
    ) -> dict:
        """Per-agent model override; each value is provider/model (read-modify-write, draft)."""
        flags = (("realtime", realtime), ("llm", llm), ("tts", tts), ("stt", stt))
        changes = {k: v for k, v in flags if v}
        if not changes:
            raise ValueError("pass at least one of realtime, llm, tts, stt as provider/model")
        client = DograhClient()
        wf = agents_cmd.ensure_draft(client, agent_id)
        configs = dict(wf.get("workflow_configurations") or {})
        cfg = configs.get(agents_cmd.OVERRIDE_KEY)
        if not cfg:
            cfg = client.get(models_cmd.MODEL_CONFIG_PATH).get("configuration")
            if not cfg:
                raise RuntimeError(
                    "no org model configuration to start from; set one with models_set first"
                )
        applied = _run(lambda: models_cmd.apply_changes(cfg, changes))
        configs[agents_cmd.OVERRIDE_KEY] = cfg
        result = client.put(
            f"/api/v1/workflow/{agent_id}", json={"workflow_configurations": configs}
        )
        return {
            "agent_id": agent_id,
            "applied": applied,
            "result": scrub(result),
            "next": "agents_validate, then agents_publish",
        }

    @server.tool(annotations=WRITE)
    def agents_publish(agent_id: int) -> dict:
        """Publish the agent's draft so inbound and outbound calls use it."""
        client = DograhClient()
        result = client.post(f"/api/v1/workflow/{agent_id}/publish") or {}
        return scrub(result) | {
            "agent_id": agent_id,
            "next": (
                "agents_chat to test without telephony; numbers_add or numbers_assign to route a "
                "number; runs_trigger to place a real call (confirm with the user)"
            ),
        }

    @server.tool(annotations=WRITE)
    def agents_chat(agent_id: int, message: str) -> dict:
        """One-shot text test of an agent (no telephony): start a session, send, end."""
        client = DograhClient()
        session = client.post(f"/api/v1/workflow/{agent_id}/text-chat/sessions", json={})
        run_id = session["workflow_run_id"]
        replies = list(runs_cmd._assistant_texts(session))
        reply = client.post(
            f"/api/v1/workflow/{agent_id}/text-chat/sessions/{run_id}/messages",
            json={"text": message, "expected_revision": session.get("revision")},
        )
        replies += [m["content"] for m in runs_cmd._new_assistant_messages(session, reply)]
        ended = (
            client.post(
                f"/api/v1/workflow/{agent_id}/text-chat/sessions/{run_id}/end",
                json={"expected_revision": reply.get("revision")},
            )
            or {}
        )
        return {
            "agent_id": agent_id,
            "run_id": run_id,
            "replies": replies,
            "state": ended.get("state"),
            "next": (
                "adjust with agents_set_prompt + agents_publish, "
                "or place a real call with runs_trigger"
            ),
        }

    # --- runs ----------------------------------------------------------------------------
    @server.tool(annotations=READ)
    def runs_list(limit: int = 10) -> dict:
        """Recent call runs across all agents (max 100): id, agent, duration, disposition."""
        client = DograhClient()
        data = runs_cmd._usage_runs(client, max(1, min(limit, 100)))
        return {
            "total_count": data.get("total_count"),
            "runs": [
                runs_cmd._run_row(r) | {"workflow_id": r.get("workflow_id")}
                for r in data.get("runs", [])
            ],
        }

    @server.tool(annotations=READ)
    def runs_latency(limit: int = 100) -> dict:
        """Call-duration summary (avg/p50/p95/min/max seconds) over recent runs (max 100)."""
        client = DograhClient()
        runs = runs_cmd._usage_runs(client, max(1, min(limit, 100))).get("runs", [])
        return latency_summary(runs)

    @server.tool(annotations=CALL)
    def runs_trigger(
        agent_id: int,
        to: Optional[str] = None,
        telephony_configuration_id: Optional[int] = None,
        from_phone_number_id: Optional[int] = None,
    ) -> dict:
        """Place a REAL outbound phone call from an agent to an E.164 number (real cost)."""
        client = DograhClient()
        body: dict = {"workflow_id": agent_id}
        if to:
            body["phone_number"] = to
        if telephony_configuration_id is not None:
            body["telephony_configuration_id"] = telephony_configuration_id
        if from_phone_number_id is not None:
            body["from_phone_number_id"] = from_phone_number_id
        result = client.post("/api/v1/telephony/initiate-call", json=body) or {}
        message = result.get("message", "")
        match = runs_cmd.RUN_NAME_RE.search(message)
        run_name = match.group(1) if match else None
        run = runs_cmd._find_run_by_name(client, run_name) if run_name else None
        return {
            "run_name": run_name,
            "run_id": run.get("id") if run else None,
            "message": message,
            "next": "runs_transcript with the run_id once the call ends",
        }

    @server.tool(annotations=READ)
    def runs_transcript(run_id: int, agent_id: Optional[int] = None) -> dict:
        """A finished run's transcript as text (from its public artifact URL)."""
        client = DograhClient()
        run = _run(lambda: runs_cmd.resolve_run(client, run_id, agent_id))
        url = run.get("transcript_public_url")
        if not url:
            raise RuntimeError(
                f"no transcript for run {run_id} (not finished, or recording disabled)"
            )
        r = client.get_public(url)
        try:
            parsed = r.json()
        except ValueError:
            parsed = None
        return {"run_id": run_id, "transcript": runs_cmd._render_transcript(r.text, parsed)}

    # --- numbers + telephony -------------------------------------------------------------
    @server.tool(annotations=READ)
    def numbers_list() -> list:
        """Phone numbers and which agent each routes to."""
        client = DograhClient()
        return [
            {
                "number": n.get("address"),
                "label": n.get("label"),
                "inbound_agent": n.get("inbound_workflow_name"),
                "inbound_agent_id": n.get("inbound_workflow_id"),
                "active": bool(n.get("is_active")),
                "config_id": cid,
            }
            for cid, n in numbers_cmd.all_numbers(client)
        ]

    @server.tool(annotations=WRITE)
    def numbers_assign(number: str, agent_id: int) -> dict:
        """Route a phone number (E.164) to an agent: sets its inbound agent."""
        client = DograhClient()
        cid, n = _run(lambda: numbers_cmd.find_number(client, number))
        result = client.put(
            f"/api/v1/organizations/telephony-configs/{cid}/phone-numbers/{n['id']}",
            json={"inbound_workflow_id": agent_id},
        )
        return {
            "number": number,
            "agent_id": agent_id,
            "result": scrub(result),
            "next": "call the number, or runs_trigger for an outbound test",
        }

    @server.tool(annotations=WRITE)
    def numbers_add(
        number: str,
        agent_id: Optional[int] = None,
        label: Optional[str] = None,
        config_id: Optional[int] = None,
    ) -> dict:
        """Register a number you already own at the carrier (buy it first), optionally routed."""
        client = DograhClient()
        cid = (
            config_id
            if config_id is not None
            else _run(lambda: numbers_cmd._default_config_id(client))
        )
        body: dict = {"address": number, "is_active": True}
        if label:
            body["label"] = label
        if agent_id is not None:
            body["inbound_workflow_id"] = agent_id
        result = client.post(
            f"/api/v1/organizations/telephony-configs/{cid}/phone-numbers", json=body
        )
        return {
            "number": number,
            "config_id": cid,
            "agent_id": agent_id,
            "result": scrub(result),
            "next": "numbers_assign to change routing later; runs_trigger to test outbound",
        }

    @server.tool(annotations=READ)
    def telephony_configs() -> list:
        """Telephony configurations (provider, default outbound, number count), secrets stripped."""
        client = DograhClient()
        return scrub(numbers_cmd.telephony_configs(client))

    # --- models --------------------------------------------------------------------------
    @server.tool(annotations=READ)
    def models_show() -> dict:
        """The org model configuration: mode and provider/model per service (no secrets)."""
        client = DograhClient()
        resp = client.get(models_cmd.MODEL_CONFIG_PATH)
        rows = models_cmd.summary_rows(resp)
        summary = {r["field"]: r["value"] for r in rows}
        return summary | {"configuration": scrub(resp.get("configuration"))}

    @server.tool(annotations=WRITE)
    def models_set(
        realtime: Optional[str] = None,
        llm: Optional[str] = None,
        tts: Optional[str] = None,
        stt: Optional[str] = None,
    ) -> dict:
        """Change service blocks of the org model configuration; each value is provider/model."""
        flags = (("realtime", realtime), ("llm", llm), ("tts", tts), ("stt", stt))
        changes = {k: v for k, v in flags if v}
        if not changes:
            raise ValueError("pass at least one of realtime, llm, tts, stt as provider/model")
        client = DograhClient()
        cfg = client.get(models_cmd.MODEL_CONFIG_PATH).get("configuration")
        if not cfg:
            raise RuntimeError(
                "no organization model configuration yet; create it once in the dashboard"
            )
        applied = _run(lambda: models_cmd.apply_changes(cfg, changes))
        result = client.put(models_cmd.MODEL_CONFIG_PATH, json=cfg)
        return {
            "applied": applied,
            "result": scrub(result),
            "next": "agents_chat to hear the new model",
        }

    # --- campaigns -----------------------------------------------------------------------
    @server.tool(annotations=READ)
    def campaigns_list() -> list:
        """Campaigns with state and progress counts."""
        client = DograhClient()
        data = client.get("/api/v1/campaign/")
        items = data.get("campaigns", []) if isinstance(data, dict) else (data or [])
        return scrub(items)

    @server.tool(annotations=WRITE)
    def campaigns_create(
        name: str,
        agent_id: int,
        csv_path: str,
        config_id: Optional[int] = None,
        max_concurrency: Optional[int] = None,
    ) -> dict:
        """Create a campaign from a local CSV (phone_number column); does not start it."""
        csv = pathlib.Path(csv_path)
        if csv.suffix.lower() != ".csv" or not csv.is_file():
            raise ValueError(f"{csv} must be an existing .csv file")
        client = DograhClient()
        campaign = campaigns_cmd.create_campaign(
            client, name, agent_id, csv, config_id, max_concurrency
        )
        return scrub(campaign) | {
            "next": "campaigns_start to place the calls (confirm with the user first: real cost)"
        }

    @server.tool(annotations=CALL)
    def campaigns_start(campaign_id: int) -> dict:
        """Start a campaign. This places REAL phone calls to every contact (real cost)."""
        client = DograhClient()
        campaign = client.post(f"/api/v1/campaign/{campaign_id}/start") or {}
        return scrub(campaign) | {"next": "campaigns_list for progress; runs_transcript per call"}

    @server.tool(annotations=WRITE)
    def campaigns_pause(campaign_id: int) -> dict:
        """Pause a running campaign."""
        client = DograhClient()
        campaign = client.post(f"/api/v1/campaign/{campaign_id}/pause") or {}
        return scrub(campaign) | {"next": "campaigns_start to resume"}

    @server.tool(annotations=READ)
    def campaigns_status(campaign_id: int) -> dict:
        """A campaign and its live progress."""
        client = DograhClient()
        campaign = client.get(f"/api/v1/campaign/{campaign_id}")
        progress = client.get(f"/api/v1/campaign/{campaign_id}/progress")
        return {"campaign": scrub(campaign), "progress": scrub(progress)}

    # --- tools + keys (read) -------------------------------------------------------------
    @server.tool(annotations=READ)
    def tools_list(status: Optional[str] = None, category: Optional[str] = None) -> list:
        """Tools agents can call (HTTP APIs, MCP servers, transfers), optionally filtered."""
        client = DograhClient()
        params = {k: v for k, v in (("status", status), ("category", category)) if v}
        return scrub(client.get("/api/v1/tools/", params=params) or [])

    @server.tool(annotations=READ)
    def keys_list(include_archived: bool = False) -> list:
        """API keys: id, name, prefix, status. Full keys are never returned; minting is CLI-only."""
        client = DograhClient()
        keys = (
            client.get("/api/v1/user/api-keys", params={"include_archived": include_archived}) or []
        )
        return [
            {
                "id": k.get("id"),
                "name": k.get("name"),
                "prefix": k.get("key_prefix"),
                "active": bool(k.get("is_active")),
                "last_used_at": k.get("last_used_at"),
                "created_at": k.get("created_at"),
            }
            for k in keys
        ]

    return server
