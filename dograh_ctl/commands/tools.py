"""tools: the reusable tools agents can call (HTTP APIs, MCP servers, transfers)."""
from __future__ import annotations

from typing import Optional

import typer

from .. import output
from ..cli import GuardedTyper
from ..client import DograhClient

app = GuardedTyper(help="Tools available to your agents.")


@app.command("list")
def tools_list(
    status: Optional[str] = typer.Option(None, "--status", help="active, archived, or draft."),
    category: Optional[str] = typer.Option(
        None, "--category", help="http_api, native, integration, mcp, ..."
    ),
):
    """List tools (optionally filtered by status or category)."""
    client = DograhClient()
    params = {k: v for k, v in (("status", status), ("category", category)) if v}
    tools = client.get("/api/v1/tools/", params=params) or []
    rows = [
        {
            "name": t.get("name", ""),
            "category": t.get("category", ""),
            "status": t.get("status", ""),
            "uuid": t.get("tool_uuid", ""),
            "description": (t.get("description") or "")[:60],
        }
        for t in tools
    ]
    output.table(
        rows,
        [
            ("Name", "name", {"style": "cyan"}),
            ("Category", "category"),
            ("Status", "status"),
            ("UUID", "uuid"),
            ("Description", "description"),
        ],
        title="Tools",
        raw=tools,
    )
