"""telephony: provider configurations on the instance, and the providers Dograh supports."""
from __future__ import annotations

from .. import output
from ..cli import GuardedTyper
from ..client import DograhClient
from .numbers import telephony_configs

app = GuardedTyper(help="Telephony configurations and providers.")


@app.command("configs")
def telephony_configs_cmd():
    """List telephony configurations (provider, default outbound, number count, readiness)."""
    client = DograhClient()
    configs = telephony_configs(client)
    rows = [
        {
            "id": c.get("id"),
            "name": c.get("name", ""),
            "provider": c.get("provider", ""),
            "default_outbound": "yes" if c.get("is_default_outbound") else "no",
            "numbers": c.get("phone_number_count", 0),
            "ready": "yes" if c.get("is_ready_for_outbound", True) else "no",
            "inactive": "yes" if c.get("inactive") else "no",
        }
        for c in configs
    ]
    output.table(
        rows,
        [
            ("ID", "id", {"justify": "right", "style": "cyan"}),
            ("Name", "name"),
            ("Provider", "provider"),
            ("Default outbound", "default_outbound"),
            ("Numbers", "numbers", {"justify": "right"}),
            ("Ready", "ready"),
            ("Inactive", "inactive"),
        ],
        title="Telephony configurations",
        raw=configs,
    )


@app.command("providers")
def telephony_providers():
    """List the telephony providers this Dograh build supports (and their config fields)."""
    client = DograhClient()
    data = client.get("/api/v1/organizations/telephony-providers/metadata")
    providers = data.get("providers", []) if isinstance(data, dict) else (data or [])
    rows = [
        {
            "provider": p.get("provider", ""),
            "display_name": p.get("display_name", ""),
            "connectivity": p.get("connectivity", ""),
            "fields": ", ".join(f.get("name", "") for f in p.get("fields", [])) or "-",
            "docs": p.get("docs_url") or "-",
        }
        for p in providers
    ]
    output.table(
        rows,
        [
            ("Provider", "provider", {"style": "cyan"}),
            ("Name", "display_name"),
            ("Connectivity", "connectivity"),
            ("Config fields", "fields"),
            ("Docs", "docs"),
        ],
        title="Telephony providers",
        raw=providers,
    )
