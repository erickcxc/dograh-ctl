"""dograh-ctl: run your self-hosted Dograh voice-agent platform from the terminal."""
from __future__ import annotations

import typer

from . import output
from .cli import GuardedTyper
from .client import DograhClient
from .commands import agents, campaigns, keys, models, numbers, runs, telephony, tools

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


@app.command("mcp-config")
def mcp_config(
    name: str = typer.Option("dograh-ops", "--name", help="Server name to register."),
):
    """Print how to register the MCP server: a `claude mcp add` line plus JSON for other clients."""
    import json as _json

    cfg = {
        "mcpServers": {
            name: {
                "command": "uvx",
                "args": ["dograh-ctl", "serve"],
                "env": {
                    "DOGRAH_BASE_URL": "${DOGRAH_BASE_URL}",
                    "DOGRAH_API_KEY": "${DOGRAH_API_KEY}",
                },
            }
        }
    }
    if output.state.json:
        output.emit(cfg)
        return
    typer.echo("# Claude Code (run in a shell where DOGRAH_BASE_URL and DOGRAH_API_KEY are set):")
    typer.echo(f"claude mcp add {name} -- uvx dograh-ctl serve")
    typer.echo("")
    typer.echo("# Any MCP client (.mcp.json / settings); env values are references, not secrets:")
    typer.echo(_json.dumps(cfg, indent=2))


@app.command()
def serve():
    """Run the MCP operations server over stdio so an agent can drive Dograh through dograh-ctl."""
    from .serve import build_server

    build_server().run("stdio")


app.add_typer(agents.app, name="agents")
app.add_typer(runs.app, name="runs")
app.add_typer(numbers.app, name="numbers")
app.add_typer(models.app, name="models")
app.add_typer(campaigns.app, name="campaigns")
app.add_typer(telephony.app, name="telephony")
app.add_typer(tools.app, name="tools")
app.add_typer(keys.app, name="keys")


if __name__ == "__main__":
    app()
