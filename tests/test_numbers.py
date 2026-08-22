"""numbers: list / assign (shipped Day 8), add / remove (Day 9)."""
import json

import httpx
from conftest import load_fixture


def _mock_numbers(api):
    api.get("/api/v1/organizations/telephony-configs").mock(
        return_value=httpx.Response(200, json=load_fixture("telephony_configs"))
    )
    api.get("/api/v1/organizations/telephony-configs/3/phone-numbers").mock(
        return_value=httpx.Response(200, json=load_fixture("phone_numbers"))
    )


def test_list_walks_every_config_and_shows_routing(cli, api):
    _mock_numbers(api)
    result = cli("numbers", "list")
    assert result.exit_code == 0, result.output
    assert "+13132283817" in result.output
    assert "Stream Call-In" in result.output


def test_list_json_is_flat_numbers_with_config_id(cli, api):
    _mock_numbers(api)
    result = cli("numbers", "list", "--json")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload[0]["address"] == "+13132283817"
    assert payload[0]["telephony_configuration_id"] == 3


def test_assign_puts_inbound_workflow_on_the_matching_number(cli, api):
    _mock_numbers(api)
    put = api.put("/api/v1/organizations/telephony-configs/3/phone-numbers/11").mock(
        return_value=httpx.Response(200, json={"id": 11, "inbound_workflow_id": 9})
    )
    result = cli("numbers", "assign", "+13132283817", "9")
    assert result.exit_code == 0, result.output
    assert json.loads(put.calls.last.request.content) == {"inbound_workflow_id": 9}


def test_assign_unknown_number_exits_1(cli, api):
    _mock_numbers(api)
    result = cli("numbers", "assign", "+10000000000", "9")
    assert result.exit_code == 1
    assert "not found" in result.output
