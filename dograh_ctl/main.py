"""dograh-ctl — run your self-hosted Dograh voice-agent platform from the terminal."""
from __future__ import annotations

import typer
from rich import print as rprint
from rich.console import Console
from rich.table import Table

from .client import DograhClient

app = typer.Typer(
    help="Run your self-hosted Dograh voice-agent platform from the terminal.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def ping():
    """Verify connectivity + API-key auth against your Dograh instance."""
    client = DograhClient()
    # An org-scoped read confirms the key authenticates.
    client.get("/api/v1/organizations/telephony-configs")
    rprint(f"[green]✓[/green] connected to {client.base_url} — auth OK")


# --- agents -----------------------------------------------------------------
agents_app = typer.Typer(help="Inspect voice agents (workflows).", no_args_is_help=True)
app.add_typer(agents_app, name="agents")


@agents_app.command("list")
def agents_list():
    """List the voice agents (workflows) on the instance."""
    client = DograhClient()
    workflows = client.get("/api/v1/workflow/fetch")

    table = Table(title="Agents")
    table.add_column("ID", justify="right", style="cyan")
    table.add_column("Name")
    table.add_column("Status")
    table.add_column("Runs", justify="right")
    table.add_column("Created")

    for w in workflows:
        status = w.get("status", "")
        status_cell = f"[green]{status}[/green]" if status == "active" else status
        table.add_row(
            str(w.get("id", "")),
            w.get("name", ""),
            status_cell,
            str(w.get("total_runs", 0)),
            (w.get("created_at") or "")[:10],
        )

    console.print(table)


# --- runs -------------------------------------------------------------------
runs_app = typer.Typer(help="Inspect call runs.", no_args_is_help=True)
app.add_typer(runs_app, name="runs")


@runs_app.command("list")
def runs_list(limit: int = typer.Option(10, "--limit", "-n", help="Recent runs to show.")):
    """List recent call runs (duration, disposition, model)."""
    client = DograhClient()
    data = client.get("/api/v1/organizations/usage/runs", params={"page": 1, "limit": limit})
    runs = data.get("runs", [])

    table = Table(title=f"Recent runs ({data.get('total_count', len(runs))} total)")
    table.add_column("ID", justify="right", style="cyan")
    table.add_column("Agent")
    table.add_column("Dur", justify="right")
    table.add_column("Disposition")
    table.add_column("Model")
    table.add_column("When")

    for r in runs:
        rt = (r.get("initial_context") or {}).get("runtime_configuration") or {}
        model = rt.get("realtime_model") or rt.get("llm_model") or "-"
        dur = r.get("call_duration_seconds")
        table.add_row(
            str(r.get("id", "")),
            r.get("workflow_name", ""),
            f"{dur}s" if dur is not None else "-",
            r.get("disposition", ""),
            model,
            (r.get("created_at") or "")[:19].replace("T", " "),
        )

    console.print(table)


# --- numbers ----------------------------------------------------------------
numbers_app = typer.Typer(help="Inspect and route phone numbers.", no_args_is_help=True)
app.add_typer(numbers_app, name="numbers")


def _config_ids(client: DograhClient):
    configs = client.get("/api/v1/organizations/telephony-configs")
    items = configs if isinstance(configs, list) else (
        configs.get("configurations") or configs.get("configs")
        or configs.get("items") or configs.get("data") or []
    )
    return [c["id"] for c in items]


def _phone_numbers(client: DograhClient, config_id):
    resp = client.get(f"/api/v1/organizations/telephony-configs/{config_id}/phone-numbers")
    return resp if isinstance(resp, list) else (
        resp.get("phone_numbers") or resp.get("items") or resp.get("data") or []
    )


@numbers_app.command("list")
def numbers_list():
    """List phone numbers and which agent each routes to."""
    client = DograhClient()
    table = Table(title="Phone numbers")
    table.add_column("Number", style="cyan")
    table.add_column("Label")
    table.add_column("Inbound agent")
    table.add_column("Active")
    table.add_column("Config", justify="right")
    for cid in _config_ids(client):
        for n in _phone_numbers(client, cid):
            table.add_row(
                n.get("address", ""),
                n.get("label") or "-",
                n.get("inbound_workflow_name") or "[dim]none[/dim]",
                "yes" if n.get("is_active") else "no",
                str(n.get("telephony_configuration_id", cid)),
            )
    console.print(table)


@numbers_app.command("assign")
def numbers_assign(number: str, agent_id: int):
    """Route NUMBER to AGENT_ID (sets the number's inbound workflow)."""
    client = DograhClient()
    for cid in _config_ids(client):
        for n in _phone_numbers(client, cid):
            if number in (n.get("address"), n.get("address_normalized")):
                client.request(
                    "PUT",
                    f"/api/v1/organizations/telephony-configs/{cid}/phone-numbers/{n['id']}",
                    json={"inbound_workflow_id": agent_id},
                )
                rprint(f"[green]✓[/green] {number} -> agent {agent_id}")
                return
    rprint(f"[red]✗[/red] number {number} not found")
    raise typer.Exit(1)


# ---------------------------------------------------------------------------
# Built live on stream (Day 8). Next: models set.
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    app()
