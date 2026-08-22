"""dograh-ctl: run your self-hosted Dograh voice-agent platform from the terminal."""
from __future__ import annotations

import typer

from . import output
from .cli import GuardedTyper
from .client import DograhClient
from .commands import agents, numbers, runs

app = GuardedTyper(help="Run your self-hosted Dograh voice-agent platform from the terminal.")


def _version(value: bool):
    if value:
        from . import __version__

        typer.echo(f"dograh-ctl {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    json_: bool = typer.Option(False, "--json", help="Print raw JSON instead of tables."),
    version: bool = typer.Option(
        False, "--version", callback=_version, is_eager=True, help="Show the version and exit."
    ),
):
    # Explicit assignment (not "if json_") so repeated in-process invocations never inherit
    # the previous call's mode; a trailing --json on a command can still switch it on.
    output.state.json = json_


@app.command()
def ping():
    """Verify connectivity and API-key auth against your Dograh instance."""
    client = DograhClient()
    # An org-scoped read confirms the key authenticates.
    client.get("/api/v1/organizations/telephony-configs")
    output.ok(
        f"connected to {client.base_url}: auth OK",
        data={"ok": True, "base_url": client.base_url, "auth": "ok"},
    )


app.add_typer(agents.app, name="agents")
app.add_typer(runs.app, name="runs")
app.add_typer(numbers.app, name="numbers")


if __name__ == "__main__":
    app()
