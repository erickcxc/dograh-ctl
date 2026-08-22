"""numbers: phone numbers registered on the instance and which agent each routes to.

Buying a number is a carrier action (for Twilio: `twilio phone-numbers:buy:local ...`);
`numbers add` registers a number you already own. `numbers remove` only removes the Dograh
mapping; it does not release the number at the carrier.
"""
from __future__ import annotations

from typing import Iterator, Tuple

import typer

from .. import output
from ..cli import GuardedTyper
from ..client import DograhClient

app = GuardedTyper(help="Inspect and route phone numbers.")

NUMBER_COLUMNS = [
    ("Number", "address", {"style": "cyan"}),
    ("Label", "label"),
    ("Inbound agent", "inbound_agent"),
    ("Active", "active"),
    ("Config", "telephony_configuration_id", {"justify": "right"}),
]


def telephony_configs(client: DograhClient) -> list:
    data = client.get("/api/v1/organizations/telephony-configs")
    if isinstance(data, list):
        return data
    return data.get("configurations") or []


def phone_numbers(client: DograhClient, config_id: int) -> list:
    data = client.get(f"/api/v1/organizations/telephony-configs/{config_id}/phone-numbers")
    if isinstance(data, list):
        return data
    return data.get("phone_numbers") or []


def all_numbers(client: DograhClient) -> Iterator[Tuple[int, dict]]:
    for cfg in telephony_configs(client):
        for n in phone_numbers(client, cfg["id"]):
            n.setdefault("telephony_configuration_id", cfg["id"])
            yield cfg["id"], n


def find_number(client: DograhClient, number: str) -> Tuple[int, dict]:
    for cid, n in all_numbers(client):
        if number in (n.get("address"), n.get("address_normalized")):
            return cid, n
    output.fail(f"number {number} not found on this instance")
    raise typer.Exit(1)


@app.command("list")
def numbers_list():
    """List phone numbers and which agent each routes to."""
    client = DograhClient()
    numbers = [n for _cid, n in all_numbers(client)]
    rows = [
        {
            "address": n.get("address", ""),
            "label": n.get("label") or "-",
            "inbound_agent": n.get("inbound_workflow_name") or "none",
            "active": "yes" if n.get("is_active") else "no",
            "telephony_configuration_id": n.get("telephony_configuration_id"),
        }
        for n in numbers
    ]
    output.table(rows, NUMBER_COLUMNS, title="Phone numbers", raw=numbers)


@app.command("assign")
def numbers_assign(number: str, agent_id: int):
    """Route NUMBER to AGENT_ID (sets the number's inbound agent)."""
    client = DograhClient()
    cid, n = find_number(client, number)
    result = client.put(
        f"/api/v1/organizations/telephony-configs/{cid}/phone-numbers/{n['id']}",
        json={"inbound_workflow_id": agent_id},
    )
    output.ok(f"{number} -> agent {agent_id}", data=result)
