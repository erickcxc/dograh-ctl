"""runs: call runs, their metrics, transcripts, and the ways to start one."""
from __future__ import annotations

import typer

from .. import output
from ..cli import GuardedTyper
from ..client import DograhClient
from ..stats import latency_summary

app = GuardedTyper(help="Inspect and start call runs.")

RUN_COLUMNS = [
    ("ID", "id", {"justify": "right", "style": "cyan"}),
    ("Agent", "agent"),
    ("Dur", "dur", {"justify": "right"}),
    ("Disposition", "disposition"),
    ("Model", "model"),
    ("When", "when"),
]


def _usage_runs(client: DograhClient, limit: int) -> dict:
    data = client.get("/api/v1/organizations/usage/runs", params={"page": 1, "limit": limit})
    return data if isinstance(data, dict) else {"runs": data or [], "total_count": len(data or [])}


def _run_row(r: dict) -> dict:
    rt = (r.get("initial_context") or {}).get("runtime_configuration") or {}
    dur = r.get("call_duration_seconds")
    return {
        "id": r.get("id", ""),
        "agent": r.get("workflow_name", ""),
        "dur": f"{dur}s" if dur is not None else "-",
        "disposition": r.get("disposition", ""),
        "model": rt.get("realtime_model") or rt.get("llm_model") or "-",
        "when": (r.get("created_at") or "")[:19].replace("T", " "),
    }


@app.command("list")
def runs_list(limit: int = typer.Option(10, "--limit", "-n", help="Recent runs to show.")):
    """List recent call runs (duration, disposition, model)."""
    client = DograhClient()
    data = _usage_runs(client, limit)
    runs = data.get("runs", [])
    output.table(
        [_run_row(r) for r in runs],
        RUN_COLUMNS,
        title=f"Recent runs ({data.get('total_count', len(runs))} total)",
        raw=data,
    )


@app.command("latency")
def runs_latency(
    limit: int = typer.Option(200, "--limit", "-n", help="Sample size of recent runs."),
):
    """Summarize call-duration latency (avg/p50/p95/min/max) across recent runs."""
    client = DograhClient()
    runs = _usage_runs(client, limit).get("runs", [])
    s = latency_summary(runs)
    row = {k: ("-" if s[k] is None else s[k]) for k in ("avg", "p50", "p95", "min", "max")}
    output.table(
        [row],
        [(k, k, {"justify": "right"}) for k in ("avg", "p50", "p95", "min", "max")],
        title=f"Latency: {s['with_duration']}/{s['count']} run(s) with duration (seconds)",
        raw=s,
    )
