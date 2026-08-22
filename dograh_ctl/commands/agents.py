"""agents: the voice agents (Dograh calls them workflows)."""
from __future__ import annotations

from typing import Optional

import typer

from .. import output
from ..cli import GuardedTyper
from ..client import DograhClient

app = GuardedTyper(help="Inspect and edit voice agents (workflows).")

AGENT_COLUMNS = [
    ("ID", "id", {"justify": "right", "style": "cyan"}),
    ("Name", "name"),
    ("Status", "status"),
    ("Runs", "runs", {"justify": "right"}),
    ("Created", "created"),
]


def ensure_draft(client: DograhClient, agent_id: int, workflow: Optional[dict] = None) -> dict:
    """Make sure the agent has a draft before a PUT.

    Live finding: PUT /workflow/{id} on a published workflow with no draft returns 500 (the change
    still persists). POST /workflow/{id}/create-draft first when version_status is not "draft".
    """
    wf = workflow if workflow is not None else client.get(f"/api/v1/workflow/fetch/{agent_id}")
    if (wf.get("version_status") or "draft") != "draft":
        client.post(f"/api/v1/workflow/{agent_id}/create-draft")
    return wf


@app.command("list")
def agents_list():
    """List the voice agents (workflows) on the instance."""
    client = DograhClient()
    workflows = client.get("/api/v1/workflow/fetch")
    rows = [
        {
            "id": w.get("id", ""),
            "name": w.get("name", ""),
            "status": w.get("status", ""),
            "runs": w.get("total_runs", 0),
            "created": (w.get("created_at") or "")[:10],
        }
        for w in workflows
    ]
    output.table(rows, AGENT_COLUMNS, title="Agents", raw=workflows)


OVERRIDE_KEY = "model_configuration_v2_override"


def _model_summary(cfg: Optional[dict]) -> str:
    """One line per configured service: provider/model only, never api keys."""
    if not cfg:
        return "none (uses the org model configuration)"
    byok = cfg.get("byok") or {}
    block = byok.get(byok.get("mode") or "") or {}
    parts = []
    for service in ("realtime", "llm", "tts", "stt"):
        svc = block.get(service) or {}
        if svc.get("provider"):
            parts.append(f"{service}={svc.get('provider')}/{svc.get('model', '?')}")
    if cfg.get("mode") == "dograh":
        parts.append("dograh-managed")
    return ", ".join(parts) or "unset"


@app.command("get")
def agents_get(agent_id: int):
    """Show one agent: status, version, node summary, and model override (secrets masked out)."""
    client = DograhClient()
    wf = client.get(f"/api/v1/workflow/fetch/{agent_id}")
    nodes = (wf.get("workflow_definition") or {}).get("nodes") or []
    counts: dict = {}
    for n in nodes:
        counts[n.get("type", "?")] = counts.get(n.get("type", "?"), 0) + 1
    override = (wf.get("workflow_configurations") or {}).get(OVERRIDE_KEY)
    rows = [
        {"field": "id", "value": wf.get("id")},
        {"field": "name", "value": wf.get("name")},
        {"field": "status", "value": wf.get("status")},
        {"field": "version", "value": f"{wf.get('version_number')} ({wf.get('version_status')})"},
        {"field": "nodes", "value": ", ".join(f"{k} x{v}" for k, v in counts.items()) or "none"},
        {"field": "model override", "value": _model_summary(override)},
        {"field": "uuid", "value": wf.get("workflow_uuid")},
    ]
    output.table(rows, [("Field", "field", {"style": "cyan"}), ("Value", "value")],
                 title=f"Agent #{agent_id}", raw=wf)


@app.command("create")
def agents_create(
    use_case: str = typer.Option(
        ..., "--use-case", "-u", help="Short use case, e.g. 'lead qualification'."
    ),
    describe: str = typer.Option(
        ..., "--describe", "-d", help="What the agent does (becomes its prompt)."
    ),
    call_type: str = typer.Option("inbound", "--call-type", help="inbound or outbound."),
):
    """Generate a new voice agent from a use case and description (shows up in the dashboard)."""
    client = DograhClient()
    ct = "inbound" if call_type.lower().startswith("in") else "outbound"
    wf = client.post(
        "/api/v1/workflow/create/template",
        json={"call_type": ct, "use_case": use_case, "activity_description": describe},
    )
    wf = wf if isinstance(wf, dict) else {}
    output.ok(f"created agent #{wf.get('id')} {wf.get('name') or use_case}", data=wf)


def update_prompt(client: DograhClient, agent_id: int, prompt: str) -> dict:
    """Set PROMPT on every agentNode (draft-first). Returns the PUT result; raises ValueError
    when the agent has no agentNode."""
    wf = ensure_draft(client, agent_id)
    wd = wf.get("workflow_definition") or {}
    hit = False
    for n in wd.get("nodes", []):
        if n.get("type") == "agentNode":
            n.setdefault("data", {})["prompt"] = prompt
            hit = True
    if not hit:
        raise ValueError("no agentNode found in this agent")
    return client.put(f"/api/v1/workflow/{agent_id}", json={"workflow_definition": wd})


@app.command("set-prompt")
def agents_set_prompt(agent_id: int, prompt: str):
    """Replace the prompt on every agentNode of an agent (saved as a new draft)."""
    client = DograhClient()
    try:
        result = update_prompt(client, agent_id, prompt)
    except ValueError as exc:
        output.fail(str(exc))
        raise typer.Exit(1) from None
    output.ok(
        f"agent #{agent_id} prompt updated (draft; run `agents publish {agent_id}` to go live)",
        data=result,
    )


@app.command("set-model")
def agents_set_model(
    agent_id: int,
    realtime: Optional[str] = typer.Option(
        None, "--realtime", help="provider/model (speech-to-speech)."
    ),
    llm: Optional[str] = typer.Option(None, "--llm", help="provider/model for the LLM."),
    tts: Optional[str] = typer.Option(None, "--tts", help="provider/model for text-to-speech."),
    stt: Optional[str] = typer.Option(None, "--stt", help="provider/model for speech-to-text."),
):
    """Per-agent model override (read-modify-write). Saves a draft: publish to make it live."""
    from .models import MODEL_CONFIG_PATH, apply_changes

    flags = (("realtime", realtime), ("llm", llm), ("tts", tts), ("stt", stt))
    changes = {k: v for k, v in flags if v}
    if not changes:
        output.fail("pass at least one of --realtime, --llm, --tts, --stt (provider/model)")
        raise typer.Exit(2)
    client = DograhClient()
    wf = ensure_draft(client, agent_id)
    configs = dict(wf.get("workflow_configurations") or {})
    cfg = configs.get(OVERRIDE_KEY)
    if not cfg:
        # No override yet: start from the org configuration so the override is complete.
        cfg = client.get(MODEL_CONFIG_PATH).get("configuration")
        if not cfg:
            output.fail(
                "no org model configuration to start from; set one up once in the dashboard"
            )
            raise typer.Exit(1)
    applied = apply_changes(cfg, changes)
    configs[OVERRIDE_KEY] = cfg
    result = client.put(f"/api/v1/workflow/{agent_id}", json={"workflow_configurations": configs})
    output.ok(
        f"agent #{agent_id} model override: " + "; ".join(applied)
        + f" (draft; run `agents publish {agent_id}` to go live)",
        data=result,
    )


@app.command("publish")
def agents_publish(agent_id: int):
    """Publish the agent's draft so calls use it."""
    client = DograhClient()
    result = client.post(f"/api/v1/workflow/{agent_id}/publish") or {}
    version = result.get("version_number")
    output.ok(
        f"agent #{agent_id} published" + (f" (version {version})" if version else ""),
        data=result,
    )


@app.command("validate")
def agents_validate(agent_id: int):
    """Validate the agent's current draft graph."""
    client = DograhClient()
    result = client.post(f"/api/v1/workflow/{agent_id}/validate") or {}
    valid = result.get("valid")
    errors = result.get("errors") or []
    if valid is False or errors:
        output.fail(f"agent #{agent_id} has {len(errors)} validation error(s): {errors}")
        if output.state.json:
            output.emit(result)
        raise typer.Exit(1)
    output.ok(f"agent #{agent_id} is valid", data=result)


@app.command("rename")
def agents_rename(agent_id: int, name: str):
    """Rename an agent."""
    client = DograhClient()
    ensure_draft(client, agent_id)
    result = client.put(f"/api/v1/workflow/{agent_id}", json={"name": name})
    output.ok(f"agent #{agent_id} renamed to '{name}'", data=result)
