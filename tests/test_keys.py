"""keys: list / create / revoke. The raw key is shown once, and only with --reveal."""
import json

import httpx
from conftest import load_fixture

NEW_KEY = {
    "id": 3,
    "name": "stream demo",
    "key_prefix": "dgr_new1",
    "api_key": "dgr_new1_FULL_RAW_KEY_VALUE",
    "created_at": "2026-08-21T19:00:00Z",
}


def test_list_shows_prefix_and_status_never_a_full_key(cli, api):
    api.get("/api/v1/user/api-keys").mock(return_value=httpx.Response(200, json=load_fixture("api_keys")))
    result = cli("keys", "list")
    assert result.exit_code == 0, result.output
    assert "dgr_ab12" in result.output and "dograh-ctl laptop" in result.output
    assert "archived" in result.output or "no" in result.output


def test_create_hides_the_raw_key_by_default(cli, api):
    route = api.post("/api/v1/user/api-keys").mock(return_value=httpx.Response(200, json=NEW_KEY))
    result = cli("keys", "create", "stream demo")
    assert result.exit_code == 0, result.output
    assert json.loads(route.calls.last.request.content) == {"name": "stream demo"}
    assert "dgr_new1" in result.output
    assert "FULL_RAW_KEY_VALUE" not in result.output
    assert "--reveal" in result.output


def test_create_reveal_prints_the_raw_key_once(cli, api):
    api.post("/api/v1/user/api-keys").mock(return_value=httpx.Response(200, json=NEW_KEY))
    result = cli("keys", "create", "stream demo", "--reveal")
    assert result.exit_code == 0, result.output
    assert "dgr_new1_FULL_RAW_KEY_VALUE" in result.output


def test_create_json_also_hides_unless_reveal(cli, api):
    api.post("/api/v1/user/api-keys").mock(return_value=httpx.Response(200, json=NEW_KEY))
    result = cli("keys", "create", "stream demo", "--json")
    payload = json.loads(result.output)
    assert payload["key_prefix"] == "dgr_new1" and "api_key" not in payload


def test_revoke_requires_yes_then_deletes(cli, api):
    route = api.delete("/api/v1/user/api-keys/2").mock(
        return_value=httpx.Response(200, json={"success": True, "message": "API key archived successfully"})
    )
    result = cli("keys", "revoke", "2")
    assert result.exit_code == 1 and route.call_count == 0
    assert "--yes" in result.output
    result = cli("keys", "revoke", "2", "--yes")
    assert result.exit_code == 0, result.output
    assert route.call_count == 1
