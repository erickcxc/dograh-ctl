import json

import httpx
from conftest import load_fixture


def test_ping_reports_host_and_auth_ok(cli, api):
    api.get("/api/v1/organizations/telephony-configs").mock(
        return_value=httpx.Response(200, json=load_fixture("telephony_configs"))
    )
    result = cli("ping")
    assert result.exit_code == 0, result.output
    assert "dograh.test" in result.output
    assert "auth OK" in result.output


def test_ping_json(cli, api):
    api.get("/api/v1/organizations/telephony-configs").mock(
        return_value=httpx.Response(200, json=load_fixture("telephony_configs"))
    )
    result = cli("ping", "--json")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"ok": True, "base_url": "https://dograh.test", "auth": "ok"}
