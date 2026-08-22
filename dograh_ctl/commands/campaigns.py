"""campaigns: outbound calling campaigns driven from a CSV of contacts.

`campaigns start` places real calls: it asks for confirmation unless --yes is passed.
"""
from __future__ import annotations

import pathlib
import time
from typing import Optional

import httpx
import typer
from rich.console import Group
from rich.live import Live
from rich.table import Table

from .. import output
from ..cli import GuardedTyper
from ..client import DograhClient, DograhError

app = GuardedTyper(help="Create and control outbound campaigns.")

CAMPAIGN_COLUMNS = [
    ("ID", "id", {"justify": "right", "style": "cyan"}),
    ("Name", "name"),
    ("Agent", "workflow_name"),
    ("State", "state"),
    ("Rows", "total_rows", {"justify": "right"}),
    ("Done", "processed_rows", {"justify": "right"}),
    ("Failed", "failed_rows", {"justify": "right"}),
    ("Created", "created"),
]


def _row(c: dict) -> dict:
    return dict(c, created=(c.get("created_at") or "")[:10])


@app.command("list")
def campaigns_list():
    """List campaigns with state and progress counts."""
    client = DograhClient()
    data = client.get("/api/v1/campaign/")
    campaigns = data.get("campaigns", []) if isinstance(data, dict) else (data or [])
    output.table([_row(c) for c in campaigns], CAMPAIGN_COLUMNS, title="Campaigns", raw=campaigns)


@app.command("create")
def campaigns_create(
    name: str = typer.Option(..., "--name", help="Campaign name."),
    agent_id: int = typer.Option(..., "--agent", help="Agent (workflow) id that places the calls."),
    csv: pathlib.Path = typer.Option(..., "--csv", help="CSV with a phone_number column."),
    config_id: Optional[int] = typer.Option(
        None, "--config", help="Telephony configuration id (default: the org default outbound)."
    ),
    max_concurrency: Optional[int] = typer.Option(
        None, "--max-concurrency", min=1, max=100, help="Parallel calls (1-100)."
    ),
):
    """Upload a CSV and create a campaign from it (does not start it)."""
    if csv.suffix.lower() != ".csv" or not csv.is_file():
        output.fail(f"{csv} must be an existing .csv file")
        raise typer.Exit(1)
    client = DograhClient()
    data = csv.read_bytes()
    presigned = client.post(
        "/api/v1/s3/presigned-upload-url",
        json={"file_name": csv.name, "file_size": len(data), "content_type": "text/csv"},
    )
    try:
        r = httpx.put(
            presigned["upload_url"], content=data, headers={"content-type": "text/csv"}, timeout=120
        )
    except httpx.HTTPError as exc:
        raise DograhError(f"CSV upload failed: {exc}") from exc
    if r.is_error:
        raise DograhError(f"CSV upload failed ({r.status_code})", status=r.status_code)
    body = {
        "name": name,
        "workflow_id": agent_id,
        "source_type": "csv",
        "source_id": presigned["file_key"],
    }
    if config_id is not None:
        body["telephony_configuration_id"] = config_id
    if max_concurrency is not None:
        body["max_concurrency"] = max_concurrency
    campaign = client.post("/api/v1/campaign/create", json=body)
    output.ok(
        f"created campaign #{campaign.get('id')} '{name}' ({campaign.get('total_rows')} rows); "
        f"start it with `campaigns start {campaign.get('id')} --yes`",
        data=campaign,
    )


@app.command("start")
def campaigns_start(
    campaign_id: int,
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
):
    """Start a campaign. This places real calls."""
    client = DograhClient()
    output.confirm(yes, f"Start campaign #{campaign_id}? This places real calls.")
    campaign = client.post(f"/api/v1/campaign/{campaign_id}/start")
    output.ok(f"campaign #{campaign_id} state: {campaign.get('state')}", data=campaign)


@app.command("pause")
def campaigns_pause(campaign_id: int):
    """Pause a running campaign."""
    client = DograhClient()
    campaign = client.post(f"/api/v1/campaign/{campaign_id}/pause")
    output.ok(f"campaign #{campaign_id} state: {campaign.get('state')}", data=campaign)


@app.command("status")
def campaigns_status(campaign_id: int):
    """Show a campaign and its live progress."""
    client = DograhClient()
    campaign = client.get(f"/api/v1/campaign/{campaign_id}")
    progress = client.get(f"/api/v1/campaign/{campaign_id}/progress")
    row = {
        "id": campaign.get("id"),
        "name": campaign.get("name", ""),
        "state": progress.get("state") or campaign.get("state", ""),
        "progress": f"{progress.get('progress_percentage', 0)}%",
        "processed": f"{progress.get('processed_rows', 0)}/{progress.get('total_rows', 0)}",
        "failed": progress.get("failed_calls", 0),
        "rate_limit": progress.get("rate_limit", ""),
        "started": (progress.get("started_at") or "-")[:19].replace("T", " "),
    }
    output.table(
        [row],
        [
            ("ID", "id", {"justify": "right", "style": "cyan"}),
            ("Name", "name"),
            ("State", "state"),
            ("Progress", "progress"),
            ("Processed", "processed"),
            ("Failed", "failed", {"justify": "right"}),
            ("Rate", "rate_limit"),
            ("Started", "started"),
        ],
        title=f"Campaign #{campaign_id}",
        raw={"campaign": campaign, "progress": progress},
    )


TERMINAL_STATES = {"completed", "failed", "cancelled", "canceled", "stopped"}


def _mask(number) -> str:
    """Show only the last four digits of a phone number (never the full number on screen)."""
    if not number:
        return "-"
    digits = str(number)
    return "..." + digits[-4:] if len(digits) > 4 else digits


def _campaign_runs(client: DograhClient, campaign_id: int, limit: int = 8) -> list:
    data = client.get(f"/api/v1/campaign/{campaign_id}/runs", params={"page": 1, "limit": limit})
    return data.get("runs", []) if isinstance(data, dict) else (data or [])


def _snapshot(client: DograhClient, campaign_id: int) -> dict:
    return {
        "campaign": client.get(f"/api/v1/campaign/{campaign_id}"),
        "progress": client.get(f"/api/v1/campaign/{campaign_id}/progress"),
        "runs": _campaign_runs(client, campaign_id),
    }


def _bar(pct: float, width: int = 30) -> str:
    filled = int(round(max(0.0, min(100.0, pct)) / 100 * width))
    return "[green]" + "#" * filled + "[/green]" + "[dim]" + "." * (width - filled) + "[/dim]"


def _render(snap: dict, ticks: int) -> Group:
    c, p, runs = snap["campaign"], snap["progress"], snap["runs"]
    state = p.get("state") or c.get("state") or "-"
    pct = float(p.get("progress_percentage") or 0)
    head = Table.grid(padding=(0, 2))
    head.add_column(style="cyan")
    head.add_column()
    title = f"#{c.get('id')} {c.get('name', '')}  (agent: {c.get('workflow_name', '-')})"
    head.add_row("campaign", title)
    head.add_row("state", f"[bold]{state}[/bold]")
    head.add_row(
        "progress",
        f"{_bar(pct)} {pct:.0f}%  {p.get('processed_rows', 0)}/{p.get('total_rows', 0)} rows, "
        f"{p.get('failed_calls', 0)} failed",
    )
    head.add_row("refresh", f"{'.' * (ticks % 4):<3} every few seconds, Ctrl-C to stop")
    t = Table(title="Calls", title_justify="left")
    for col, opts in (
        ("Run", {"justify": "right", "style": "cyan"}),
        ("To", {}),
        ("State", {}),
        ("Dur", {"justify": "right"}),
        ("Disposition", {}),
        ("Started", {}),
    ):
        t.add_column(col, **opts)
    for r in runs:
        dur = r.get("call_duration_seconds")
        done = r.get("is_completed")
        t.add_row(
            str(r.get("id", "")),
            _mask(r.get("called_number") or r.get("phone_number")),
            "[green]done[/green]" if done else "[yellow]live[/yellow]",
            f"{dur}s" if dur is not None else "-",
            r.get("disposition") or "-",
            (r.get("created_at") or "")[11:19],
        )
    if not runs:
        t.add_row("-", "-", "[dim]waiting for the dialer[/dim]", "-", "-", "-")
    return Group(head, t)


@app.command("watch")
def campaigns_watch(
    campaign_id: int,
    interval: float = typer.Option(2.0, "--interval", min=0.5, help="Seconds between refreshes."),
    once: bool = typer.Option(False, "--once", help="Print one snapshot and exit."),
):
    """Live dashboard of a campaign: progress bar and its calls, refreshed until it finishes."""
    client = DograhClient()
    snap = _snapshot(client, campaign_id)
    if once or output.state.json:
        if output.state.json:
            output.emit(snap)
        else:
            output.console.print(_render(snap, 0))
        return
    ticks = 0
    with Live(_render(snap, ticks), console=output.console, refresh_per_second=4) as live:
        while True:
            state = (snap["progress"].get("state") or snap["campaign"].get("state") or "").lower()
            all_done = all(r.get("is_completed") for r in snap["runs"])
            if state in TERMINAL_STATES and all_done:
                break
            time.sleep(interval)
            ticks += 1
            snap = _snapshot(client, campaign_id)
            live.update(_render(snap, ticks))
    output.ok(f"campaign #{campaign_id} finished: {snap['progress'].get('state')}")
