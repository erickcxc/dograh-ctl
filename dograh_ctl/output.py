"""All printing goes through here so --json and human output never drift.

state.json is set by the root --json option (or the per-command --json alias).
"""
from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from typing import Any, Iterable, Optional, Sequence

import typer
from rich.console import Console
from rich.table import Table

state = SimpleNamespace(json=False)
console = Console()
err_console = Console(stderr=True)


def emit(data: Any) -> None:
    """Print raw JSON (used by every command in --json mode)."""
    console.print_json(json.dumps(data, default=str))


def ok(message: str, data: Any = None) -> None:
    if state.json:
        emit(data if data is not None else {"ok": True, "message": message})
    else:
        console.print(f"[green]OK[/green] {message}")


def fail(message: str) -> None:
    if state.json:
        err_console.print(json.dumps({"ok": False, "error": message}))
    else:
        err_console.print(f"[red]ERROR[/red] {message}")


def table(
    rows: Iterable[dict],
    columns: Sequence[tuple],
    title: Optional[str] = None,
    raw: Any = None,
) -> None:
    """Render rows as a rich table, or as JSON when --json is active.

    columns: sequence of (header, key) or (header, key, {"justify": ..., "style": ...}).
    raw: the JSON payload to emit instead of rows (defaults to the rows themselves).
    """
    rows = list(rows)
    if state.json:
        emit(raw if raw is not None else rows)
        return
    t = Table(title=title)
    for col in columns:
        header, _key = col[0], col[1]
        opts = col[2] if len(col) > 2 else {}
        t.add_column(header, **opts)
    for row in rows:
        cells = []
        for col in columns:
            value = row.get(col[1], "")
            cells.append("" if value is None else str(value))
        t.add_row(*cells)
    console.print(t)


def confirm(yes: bool, prompt: str) -> None:
    """Gate a verb that costs money or places a call. --yes skips the prompt.

    In --json mode there is no interactive prompt; --yes is required.
    """
    if yes:
        return
    if state.json or not sys.stdin.isatty():
        fail(f"{prompt} Re-run with --yes to confirm.")
        raise typer.Exit(1)
    if not typer.confirm(prompt, default=False):
        fail("cancelled")
        raise typer.Exit(1)
