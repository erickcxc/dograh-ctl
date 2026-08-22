"""telephony: configs / providers."""
import json

import httpx
from conftest import load_fixture


def test_configs_lists_provider_default_and_readiness(cli, api):
    api.get("/api/v1/organizations/telephony-configs").mock(
        return_value=httpx.Response(200, json=load_fixture("telephony_configs"))
    )
    result = cli("telephony", "configs")
    assert result.exit_code == 0, result.output
    assert "Twilio (stream)" in result.output
    assert "twilio" in result.output
    assert "yes" in result.output  # default outbound


def test_configs_json_is_the_configurations_list(cli, api):
    api.get("/api/v1/organizations/telephony-configs").mock(
        return_value=httpx.Response(200, json=load_fixture("telephony_configs"))
    )
    result = cli("telephony", "configs", "--json")
    assert json.loads(result.output)[0]["id"] == 3


def test_providers_lists_metadata(cli, api):
    api.get("/api/v1/organizations/telephony-providers/metadata").mock(
        return_value=httpx.Response(200, json=load_fixture("telephony_providers"))
    )
    result = cli("telephony", "providers")
    assert result.exit_code == 0, result.output
    assert "Twilio" in result.output and "sip" in result.output
    result = cli("telephony", "providers", "--json")
    assert [p["provider"] for p in json.loads(result.output)] == ["twilio", "vonage", "sip"]
