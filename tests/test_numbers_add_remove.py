"""numbers add / remove: register an owned number, or drop it from Dograh (not the carrier)."""
import json

import httpx
from conftest import load_fixture


def _mock(api):
    api.get("/api/v1/organizations/telephony-configs").mock(
        return_value=httpx.Response(200, json=load_fixture("telephony_configs"))
    )
    api.get("/api/v1/organizations/telephony-configs/3/phone-numbers").mock(
        return_value=httpx.Response(200, json=load_fixture("phone_numbers"))
    )


def test_add_registers_number_on_default_config_with_agent(cli, api):
    _mock(api)
    created = dict(load_fixture("phone_numbers")["phone_numbers"][0], id=12, address="+13135550199")
    route = api.post("/api/v1/organizations/telephony-configs/3/phone-numbers").mock(
        return_value=httpx.Response(200, json=created)
    )
    result = cli("numbers", "add", "+13135550199", "--agent", "7", "--label", "demo line", "--json")
    assert result.exit_code == 0, result.output
    body = json.loads(route.calls.last.request.content)
    assert body["address"] == "+13135550199"
    assert body["inbound_workflow_id"] == 7
    assert body["label"] == "demo line"
    assert json.loads(result.output)["id"] == 12


def test_add_accepts_explicit_config(cli, api):
    _mock(api)
    route = api.post("/api/v1/organizations/telephony-configs/9/phone-numbers").mock(
        return_value=httpx.Response(200, json={"id": 13, "address": "+13135550100"})
    )
    result = cli("numbers", "add", "+13135550100", "--config", "9")
    assert result.exit_code == 0, result.output
    assert route.call_count == 1


def test_remove_needs_yes_and_deletes_the_mapping(cli, api):
    _mock(api)
    route = api.delete("/api/v1/organizations/telephony-configs/3/phone-numbers/11").mock(
        return_value=httpx.Response(200, json={"success": True})
    )
    result = cli("numbers", "remove", "+13135550100")
    assert result.exit_code == 1 and route.call_count == 0
    result = cli("numbers", "remove", "+13135550100", "--yes")
    assert result.exit_code == 0, result.output
    assert route.call_count == 1
    assert "carrier" in result.output  # reminds that the number is not released at the carrier
