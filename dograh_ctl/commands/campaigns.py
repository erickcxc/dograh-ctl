"""campaigns: outbound calling campaigns driven from a CSV of contacts.

`campaigns start` places real calls: it asks for confirmation unless --yes is passed.
"""
from __future__ import annotations

import pathlib
from typing import Optional

import httpx
import typer

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
