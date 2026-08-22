"""runs: call runs, their metrics, transcripts, and the ways to start one."""
from __future__ import annotations

import pathlib
import sys
from typing import Optional

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
def runs_list(
    limit: int = typer.Option(10, "--limit", "-n", max=100, help="Recent runs to show (max 100)."),
):
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


def resolve_run(client: DograhClient, run_id: int, agent_id: Optional[int] = None) -> dict:
    """Fetch a run's detail. Needs the agent id; finds it in recent usage when not given."""
    if agent_id is None:
        for r in _usage_runs(client, 100).get("runs", []):
            if r.get("id") == run_id:
                agent_id = r.get("workflow_id")
                break
    if agent_id is None:
        output.fail(f"run {run_id} not in the last 100 runs; pass --agent <agent id>")
        raise typer.Exit(1)
    return client.get(f"/api/v1/workflow/{agent_id}/runs/{run_id}")


def _new_assistant_messages(before: dict, after: dict) -> list:
    old = (before.get("session_data") or {}).get("messages") or []
    new = (after.get("session_data") or {}).get("messages") or []
    return [m for m in new[len(old):] if m.get("role") == "assistant"]


@app.command("chat")
def runs_chat(
    agent_id: int,
    message: Optional[str] = typer.Option(
        None, "--message", "-m", help="Send one message, then end the session."
    ),
):
    """Text-chat with an agent (no telephony): interactive until a blank line, or one -m message."""
    client = DograhClient()
    session = client.post(f"/api/v1/workflow/{agent_id}/text-chat/sessions", json={})
    run_id = session["workflow_run_id"]
    echo = not output.state.json

    def say(messages: list) -> None:
        if echo:
            for m in messages:
                output.console.print(f"[cyan]agent>[/cyan] {m.get('content', '')}")

    say((session.get("session_data") or {}).get("messages") or [])

    def send(text: str) -> None:
        nonlocal session
        reply = client.post(
            f"/api/v1/workflow/{agent_id}/text-chat/sessions/{run_id}/messages",
            json={"text": text, "expected_revision": session.get("revision")},
        )
        say(_new_assistant_messages(session, reply))
        session = reply

    if message is not None:
        send(message)
    else:
        while True:
            if echo:
                typer.echo("you> ", nl=False)
            line = sys.stdin.readline()
            if not line or not line.strip():
                break
            send(line.strip())
    ended = client.post(
        f"/api/v1/workflow/{agent_id}/text-chat/sessions/{run_id}/end",
        json={"expected_revision": session.get("revision")},
    )
    output.ok(f"session {run_id} ended (state: {ended.get('state')})", data=ended)


@app.command("recording")
def runs_recording(
    run_id: int,
    out: Optional[pathlib.Path] = typer.Option(
        None, "--out", "-o", help="Output file (default run-<id>.wav)."
    ),
    agent_id: Optional[int] = typer.Option(None, "--agent", help="Agent id (skips the lookup)."),
    track: str = typer.Option(
        "recording", "--track", help="recording, user_recording, or bot_recording."
    ),
):
    """Download a run's recording (public artifact) to a file."""
    client = DograhClient()
    run = resolve_run(client, run_id, agent_id)
    url = run.get(f"{track}_public_url")
    if not url:
        output.fail(f"no {track.replace('_', ' ')} for run {run_id}")
        raise typer.Exit(1)
    r = client.get_public(url)
    path = out or pathlib.Path(f"run-{run_id}.wav")
    path.write_bytes(r.content)
    output.ok(
        f"saved {len(r.content)} bytes to {path}",
        data={"run_id": run_id, "path": str(path), "bytes": len(r.content)},
    )


@app.command("latency")
def runs_latency(
    limit: int = typer.Option(
        100, "--limit", "-n", max=100, help="Sample size of recent runs (server cap: 100)."
    ),
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
