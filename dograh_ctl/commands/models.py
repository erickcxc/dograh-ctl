"""models: the organization-level AI model configuration (v2).

`set` is read-modify-write: GET the stored configuration (secrets arrive masked), change one
service block, PUT the whole thing back. The server re-merges the real secrets, so this tool never
invents or prints a key.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import typer

from .. import output
from ..cli import GuardedTyper
from ..client import DograhClient

app = GuardedTyper(help="Show and change the org model configuration.")

SERVICES = ("realtime", "llm", "tts", "stt")
MODEL_CONFIG_PATH = "/api/v1/organizations/model-configurations/v2"


def parse_spec(service: str, spec: str) -> Tuple[str, str]:
    """'provider/model' -> (provider, model); exit 2 on anything else."""
    if spec.count("/") != 1 or not all(spec.split("/")):
        output.fail(
            f"--{service} expects provider/model, e.g. google_realtime/gemini-3.1-flash-live-preview"
        )
        raise typer.Exit(2)
    provider, model = spec.split("/")
    return provider, model


def active_block(cfg: dict) -> dict:
    """The service block the configuration actually uses (byok.realtime or byok.pipeline)."""
    if cfg.get("mode") != "byok":
        output.fail(
            "this organization uses Dograh-managed models; switch to BYOK in the dashboard first"
        )
        raise typer.Exit(1)
    byok = cfg.get("byok") or {}
    mode = byok.get("mode")
    block = byok.get(mode or "")
    if not mode or block is None:
        output.fail(
            "the BYOK configuration has no realtime or pipeline block to edit; "
            "set it up once in the dashboard"
        )
        raise typer.Exit(1)
    return block


def apply_changes(cfg: dict, changes: Dict[str, str]) -> List[str]:
    """Apply {service: 'provider/model'} to cfg in place. Returns human-readable change lines."""
    block = active_block(cfg)
    mode = (cfg.get("byok") or {}).get("mode")
    applied = []
    for service, spec in changes.items():
        provider, model = parse_spec(service, spec)
        if service not in block or block.get(service) is None:
            available = ", ".join(k for k in SERVICES if block.get(k))
            output.fail(f"'{service}' is not part of the {mode} configuration (available: {available})")
            raise typer.Exit(1)
        block[service]["provider"] = provider
        block[service]["model"] = model
        applied.append(f"{service} -> {provider}/{model}")
    return applied


def summary_rows(resp: dict) -> list:
    cfg = resp.get("configuration") or {}
    byok = cfg.get("byok") or {}
    block = byok.get(byok.get("mode") or "") or {}
    rows = [
        {"field": "mode", "value": cfg.get("mode") or "unset"},
        {"field": "byok mode", "value": byok.get("mode") or "-"},
    ]
    for service in SERVICES:
        svc = block.get(service) or {}
        if svc.get("provider"):
            rows.append({"field": service, "value": f"{svc['provider']}/{svc.get('model', '?')}"})
    eff = resp.get("effective_configuration") or {}
    rows.append({"field": "source", "value": resp.get("source", "-")})
    if eff.get("test_phone_number"):
        rows.append({"field": "test phone", "value": eff["test_phone_number"]})
    if eff.get("timezone"):
        rows.append({"field": "timezone", "value": eff["timezone"]})
    return rows


@app.command("show")
def models_show():
    """Show the org model configuration: mode, realtime/llm/tts/stt providers and models."""
    client = DograhClient()
    resp = client.get(MODEL_CONFIG_PATH)
    output.table(
        summary_rows(resp),
        [("Field", "field", {"style": "cyan"}), ("Value", "value")],
        title="Model configuration",
        raw=resp,
    )


@app.command("set")
def models_set(
    realtime: Optional[str] = typer.Option(
        None, "--realtime", help="provider/model for speech-to-speech."
    ),
    llm: Optional[str] = typer.Option(None, "--llm", help="provider/model for the LLM."),
    tts: Optional[str] = typer.Option(None, "--tts", help="provider/model for text-to-speech."),
    stt: Optional[str] = typer.Option(None, "--stt", help="provider/model for speech-to-text."),
):
    """Change one or more service blocks (read-modify-write; stored secrets are preserved)."""
    flags = (("realtime", realtime), ("llm", llm), ("tts", tts), ("stt", stt))
    changes = {k: v for k, v in flags if v}
    if not changes:
        output.fail("pass at least one of --realtime, --llm, --tts, --stt (provider/model)")
        raise typer.Exit(2)
    client = DograhClient()
    resp = client.get(MODEL_CONFIG_PATH)
    cfg = resp.get("configuration")
    if not cfg:
        output.fail("no organization model configuration yet; create it once in the dashboard")
        raise typer.Exit(1)
    applied = apply_changes(cfg, changes)
    result = client.put(MODEL_CONFIG_PATH, json=cfg)
    output.ok("model configuration updated: " + "; ".join(applied), data=result)
