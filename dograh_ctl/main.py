"""dograh-ctl — run your self-hosted Dograh voice-agent platform from the terminal."""
from __future__ import annotations

import typer
from rich import print as rprint

from .client import DograhClient

app = typer.Typer(
    help="Run your self-hosted Dograh voice-agent platform from the terminal.",
    no_args_is_help=True,
)


@app.command()
def ping():
    """Verify connectivity + API-key auth against your Dograh instance."""
    client = DograhClient()
    # An org-scoped read confirms the key authenticates.
    client.get("/api/v1/organizations/telephony-configs")
    rprint(f"[green]✓[/green] connected to {client.base_url} — auth OK")


# ---------------------------------------------------------------------------
# Built live on stream (Day 8). Command groups to add:
#   agents   : list / create
#   runs     : list / latency
#   numbers  : list / assign
#   models   : set
# Next episode: wrap these as an MCP server so an agent can drive Dograh.
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    app()
