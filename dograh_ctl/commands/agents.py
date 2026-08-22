"""agents: the voice agents (Dograh calls them workflows)."""
from __future__ import annotations

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


@app.command("set-prompt")
def agents_set_prompt(agent_id: int, prompt: str):
    """Replace the prompt on every agentNode of an agent (saved as a new draft)."""
    client = DograhClient()
    wf = client.get(f"/api/v1/workflow/fetch/{agent_id}")
    wd = wf.get("workflow_definition") or {}
    hit = False
    for n in wd.get("nodes", []):
        if n.get("type") == "agentNode":
            n.setdefault("data", {})["prompt"] = prompt
            hit = True
    if not hit:
        output.fail("no agentNode found in this agent")
        raise typer.Exit(1)
    result = client.put(f"/api/v1/workflow/{agent_id}", json={"workflow_definition": wd})
    output.ok(
        f"agent #{agent_id} prompt updated (draft; run `agents publish {agent_id}` to go live)",
        data=result,
    )


@app.command("rename")
def agents_rename(agent_id: int, name: str):
    """Rename an agent."""
    client = DograhClient()
    result = client.put(f"/api/v1/workflow/{agent_id}", json={"name": name})
    output.ok(f"agent #{agent_id} renamed to '{name}'", data=result)
