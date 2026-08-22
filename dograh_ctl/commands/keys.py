"""keys: the organization API keys (the same kind dograh-ctl authenticates with).

`keys create` prints only the key prefix unless --reveal is passed; the full key is returned
by Dograh exactly once and is never logged by this tool.
"""
from __future__ import annotations

import typer

from .. import output
from ..cli import GuardedTyper
from ..client import DograhClient

app = GuardedTyper(help="Manage organization API keys.")


@app.command("list")
def keys_list(
    all_: bool = typer.Option(False, "--all", help="Include archived (revoked) keys."),
):
    """List API keys (prefix, status, last used). Full keys are never shown."""
    client = DograhClient()
    keys = client.get("/api/v1/user/api-keys", params={"include_archived": all_}) or []
    rows = [
        {
            "id": k.get("id"),
            "name": k.get("name", ""),
            "prefix": k.get("key_prefix", ""),
            "status": "active" if k.get("is_active") else "archived",
            "last_used": (k.get("last_used_at") or "never")[:19].replace("T", " "),
            "created": (k.get("created_at") or "")[:10],
        }
        for k in keys
    ]
    output.table(
        rows,
        [
            ("ID", "id", {"justify": "right", "style": "cyan"}),
            ("Name", "name"),
            ("Prefix", "prefix"),
            ("Status", "status"),
            ("Last used", "last_used"),
            ("Created", "created"),
        ],
        title="API keys",
        raw=keys,
    )


@app.command("create")
def keys_create(
    name: str,
    reveal: bool = typer.Option(
        False, "--reveal", help="Print the full key once (it cannot be retrieved later)."
    ),
):
    """Create an API key. Prints the prefix only unless --reveal is passed."""
    client = DograhClient()
    created = client.post("/api/v1/user/api-keys", json={"name": name}) or {}
    public = {k: v for k, v in created.items() if k != "api_key"}
    if reveal:
        output.ok(
            f"created key #{created.get('id')} {created.get('key_prefix')}... "
            f"full key (shown once): {created.get('api_key')}",
            data=created,
        )
    else:
        output.ok(
            f"created key #{created.get('id')} {created.get('key_prefix')}... "
            "(full key hidden; re-run with --reveal to print it once)",
            data=public,
        )


@app.command("revoke")
def keys_revoke(
    key_id: int,
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
):
    """Revoke (archive) an API key. It stops authenticating immediately."""
    client = DograhClient()
    output.confirm(yes, f"Revoke API key #{key_id}? It stops working immediately.")
    result = client.delete(f"/api/v1/user/api-keys/{key_id}")
    output.ok(f"key #{key_id} revoked", data=result)
