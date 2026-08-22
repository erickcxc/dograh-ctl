"""runs: list / latency (shipped Day 8), trigger / transcript / recording / chat (Day 9)."""
import json

import httpx
from conftest import load_fixture


def test_list_passes_limit_and_prints_usage_payload(cli, api):
    route = api.get("/api/v1/organizations/usage/runs").mock(
        return_value=httpx.Response(200, json=load_fixture("usage_runs"))
    )
    result = cli("runs", "list", "-n", "2", "--json")
    assert result.exit_code == 0, result.output
    assert route.calls.last.request.url.params["limit"] == "2"
    payload = json.loads(result.output)
    assert payload["total_count"] == 2
    assert payload["runs"][0]["disposition"] == "completed"


def test_list_table_shows_model_disposition_and_duration(cli, api):
    api.get("/api/v1/organizations/usage/runs").mock(return_value=httpx.Response(200, json=load_fixture("usage_runs")))
    result = cli("runs", "list")
    assert result.exit_code == 0, result.output
    assert "gemini-3.1-flash-live-preview" in result.output
    assert "no-answer" in result.output
    assert "42s" in result.output


def test_latency_summarizes_call_durations(cli, api):
    api.get("/api/v1/organizations/usage/runs").mock(return_value=httpx.Response(200, json=load_fixture("usage_runs")))
    result = cli("runs", "latency", "--json")
    assert result.exit_code == 0, result.output
    s = json.loads(result.output)
    assert s["count"] == 2 and s["with_duration"] == 2
    assert s["avg"] == 30.0 and s["max"] == 42.0


def test_latency_default_sample_respects_server_cap_of_100(cli, api):
    """dograh-hq/dograh@b32187d8 organization_usage.py: usage/runs limit is le=100 (422 above)."""
    route = api.get("/api/v1/organizations/usage/runs").mock(
        return_value=httpx.Response(200, json=load_fixture("usage_runs"))
    )
    result = cli("runs", "latency")
    assert result.exit_code == 0, result.output
    assert int(route.calls.last.request.url.params["limit"]) <= 100


def test_latency_rejects_limit_above_100_locally(cli, api):
    route = api.get("/api/v1/organizations/usage/runs").mock(
        return_value=httpx.Response(200, json=load_fixture("usage_runs"))
    )
    result = cli("runs", "latency", "-n", "500")
    assert result.exit_code == 2
    assert route.call_count == 0
