"""runs: call runs, their metrics, transcripts, and the ways to start one."""
from __future__ import annotations

import pathlib
import re
import sys
import time
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


def _assistant_texts(session: dict) -> list:
    """Assistant utterances in order. Live API: session_data.turns[].assistant_message.text;
    older shape: session_data.messages[] with role/content."""
    sd = session.get("session_data") or {}
    texts = []
    for turn in sd.get("turns") or []:
        msg = turn.get("assistant_message")
        if isinstance(msg, dict):
            msg = msg.get("text") or msg.get("content")
        if msg:
            texts.append(str(msg))
    for m in sd.get("messages") or []:
        if m.get("role") == "assistant" and m.get("content"):
            texts.append(str(m["content"]))
    return texts


def _new_assistant_messages(before: dict, after: dict) -> list:
    old = _assistant_texts(before)
    new = _assistant_texts(after)
    return [{"content": t} for t in new[len(old):]]


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

    say([{"content": t} for t in _assistant_texts(session)])

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


RUN_NAME_RE = re.compile(r"(WR-[A-Z-]+-\d+)")


def _find_run_by_name(client: DograhClient, name: str, attempts: int = 5) -> Optional[dict]:
    for _ in range(attempts):
        for r in _usage_runs(client, 50).get("runs", []):
            if r.get("name") == name:
                return r
        time.sleep(1.0)
    return None


@app.command("trigger")
def runs_trigger(
    agent_id: int,
    to: Optional[str] = typer.Option(
        None, "--to", help="E.164 number to call (default: org test number)."
    ),
    config_id: Optional[int] = typer.Option(None, "--config", help="Telephony configuration id."),
    from_id: Optional[int] = typer.Option(None, "--from-id", help="Phone number id to call from."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
):
    """Place an outbound call from an agent to a number (real call, real cost)."""
    client = DograhClient()
    target = to or "the org test number"
    output.confirm(yes, f"Place a real call from agent {agent_id} to {target}?")
    body: dict = {"workflow_id": agent_id}
    if to:
        body["phone_number"] = to
    if config_id is not None:
        body["telephony_configuration_id"] = config_id
    if from_id is not None:
        body["from_phone_number_id"] = from_id
    result = client.post("/api/v1/telephony/initiate-call", json=body) or {}
    message = result.get("message", "")
    match = RUN_NAME_RE.search(message)
    run_name = match.group(1) if match else None
    run = _find_run_by_name(client, run_name) if run_name else None
    run_id = run.get("id") if run else None
    text = f"call initiated: {run_name or message}"
    if run_id is not None:
        text += f" (run id {run_id}; `runs transcript {run_id}` when it ends)"
    output.ok(text, data={"run_name": run_name, "run_id": run_id, "message": message})


def _render_transcript(body: str, parsed) -> str:
    if isinstance(parsed, list):
        lines = []
        for turn in parsed:
            if isinstance(turn, dict):
                content = turn.get("content", turn.get("text", ""))
                lines.append(f"{turn.get('role', '?')}: {content}")
            else:
                lines.append(str(turn))
        return "\n".join(lines)
    if isinstance(parsed, dict):
        turns = parsed.get("messages") or parsed.get("transcript") or parsed.get("turns")
        if isinstance(turns, list):
            return _render_transcript(body, turns)
    return body


@app.command("transcript")
def runs_transcript(
    run_id: int,
    agent_id: Optional[int] = typer.Option(None, "--agent", help="Agent id (skips the lookup)."),
):
    """Print a run's transcript (fetched from its public artifact URL)."""
    client = DograhClient()
    run = resolve_run(client, run_id, agent_id)
    url = run.get("transcript_public_url")
    if not url:
        output.fail(f"no transcript for run {run_id} (not finished, or recording disabled)")
        raise typer.Exit(1)
    r = client.get_public(url)
    body = r.text
    try:
        parsed = r.json()
    except ValueError:
        parsed = None
    text = _render_transcript(body, parsed)
    if output.state.json:
        output.emit({"run_id": run_id, "transcript": text})
    else:
        output.console.print(text)


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
