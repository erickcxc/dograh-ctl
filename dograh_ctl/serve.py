"""serve: the operations MCP server.

Exposes dograh-ctl's run-it verbs (agents, runs, numbers, models, campaigns) as MCP tools over
stdio, so an agent (Claude Code, any MCP client) can operate a Dograh instance through the same
client and helpers the CLI uses. Authoring (building agents) stays with Dograh's own MCP server at
/api/v1/mcp; this one never creates or edits graphs.

Rules that keep it safe for an agent:
- Tools return dicts/lists and print nothing on stdout (stdio is the transport).
- Reads are annotated read_only_hint=True; the only call-placing tool, runs_trigger, is
  destructive_hint=True so clients ask before running it.
- Secrets never leave the server: api_key fields are stripped from every payload, even masked.
"""
from __future__ import annotations

from typing import Any, Optional

import typer
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from .client import DograhClient
from .commands import models as models_cmd
from .commands import numbers as numbers_cmd
from .commands import runs as runs_cmd
from .commands.agents import OVERRIDE_KEY, _model_summary
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
    "api_key", "auth_token", "api_secret", "credentials", "aws_access_key", "aws_secret_key"
}


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


def build_server() -> MCPServer:
    server = MCPServer(
        name="dograh-ops",
        # WARNING level: nothing chatty may reach stdout (the stdio transport).
        log_level="WARNING",
        instructions=(
            "Operate a self-hosted Dograh voice-agent platform: list and inspect agents, read "
            "call runs, transcripts and latency, route phone numbers, and change model "
            "configuration. runs_trigger places a real phone call (costs money): confirm first. "
            "Building or editing agent graphs is Dograh's own MCP server, not this one."
        ),
    )

    # --- agents (read) -------------------------------------------------------------------
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
        wf = client.get(f"/api/v1/workflow/fetch/{agent_id}")
        nodes = (wf.get("workflow_definition") or {}).get("nodes") or []
        counts: dict = {}
        for n in nodes:
            counts[n.get("type", "?")] = counts.get(n.get("type", "?"), 0) + 1
        override = (wf.get("workflow_configurations") or {}).get(OVERRIDE_KEY)
        return {
            "id": wf.get("id"),
            "name": wf.get("name"),
            "status": wf.get("status"),
            "version_number": wf.get("version_number"),
            "version_status": wf.get("version_status"),
            "nodes": counts,
            "model_override": _model_summary(override),
            "workflow_uuid": wf.get("workflow_uuid"),
            "total_runs": wf.get("total_runs"),
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
        return {"run_name": run_name, "run_id": run.get("id") if run else None, "message": message}

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

    # --- numbers -------------------------------------------------------------------------
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
        return {"number": number, "agent_id": agent_id, "result": scrub(result)}

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
        return {"applied": applied, "result": scrub(result)}

    # --- campaigns -----------------------------------------------------------------------
    @server.tool(annotations=READ)
    def campaigns_status(campaign_id: int) -> dict:
        """A campaign and its live progress."""
        client = DograhClient()
        campaign = client.get(f"/api/v1/campaign/{campaign_id}")
        progress = client.get(f"/api/v1/campaign/{campaign_id}/progress")
        return {"campaign": scrub(campaign), "progress": scrub(progress)}

    return server
