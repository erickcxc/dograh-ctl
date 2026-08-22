"""models show / set: the org-level model configuration (v2). Secrets stay masked end to end."""
import json

import httpx
from conftest import load_fixture


def test_show_prints_mode_and_each_service(cli, api):
    api.get("/api/v1/organizations/model-configurations/v2").mock(
        return_value=httpx.Response(200, json=load_fixture("model_config_v2"))
    )
    result = cli("models", "show")
    assert result.exit_code == 0, result.output
    assert "byok" in result.output and "realtime" in result.output
    assert "openai_realtime" in result.output and "gpt-realtime-2" in result.output
    assert "gpt-4.1-mini" in result.output
    assert "****" not in result.output or "1234" not in result.output  # never echo even masked keys


def test_show_json_is_the_raw_response(cli, api):
    api.get("/api/v1/organizations/model-configurations/v2").mock(
        return_value=httpx.Response(200, json=load_fixture("model_config_v2"))
    )
    result = cli("models", "show", "--json")
    assert json.loads(result.output)["source"] == "organization_v2"


def test_set_realtime_is_read_modify_write_preserving_masked_keys(cli, api):
    api.get("/api/v1/organizations/model-configurations/v2").mock(
        return_value=httpx.Response(200, json=load_fixture("model_config_v2"))
    )
    put = api.put("/api/v1/organizations/model-configurations/v2").mock(
        return_value=httpx.Response(200, json=load_fixture("model_config_v2"))
    )
    result = cli("models", "set", "--realtime", "google_realtime/gemini-3.1-flash-live-preview")
    assert result.exit_code == 0, result.output
    body = json.loads(put.calls.last.request.content)
    assert body["version"] == 2 and body["mode"] == "byok" and body["byok"]["mode"] == "realtime"
    rt = body["byok"]["realtime"]["realtime"]
    assert rt["provider"] == "google_realtime"
    assert rt["model"] == "gemini-3.1-flash-live-preview"
    assert rt["api_key"] == "****1234"  # server re-merges the real secret; we never invent one
    assert body["byok"]["realtime"]["llm"] == {
        "provider": "openai", "model": "gpt-4.1-mini", "api_key": "****5678"
    }


def test_set_llm_changes_only_the_llm_block(cli, api):
    api.get("/api/v1/organizations/model-configurations/v2").mock(
        return_value=httpx.Response(200, json=load_fixture("model_config_v2"))
    )
    put = api.put("/api/v1/organizations/model-configurations/v2").mock(
        return_value=httpx.Response(200, json=load_fixture("model_config_v2"))
    )
    result = cli("models", "set", "--llm", "openai/gpt-4.1")
    assert result.exit_code == 0, result.output
    body = json.loads(put.calls.last.request.content)
    assert body["byok"]["realtime"]["llm"]["model"] == "gpt-4.1"
    assert body["byok"]["realtime"]["realtime"]["model"] == "gpt-realtime-2"


def test_set_rejects_bad_spec_and_needs_at_least_one_flag(cli, api):
    api.get("/api/v1/organizations/model-configurations/v2").mock(
        return_value=httpx.Response(200, json=load_fixture("model_config_v2"))
    )
    result = cli("models", "set")
    assert result.exit_code == 2
    result = cli("models", "set", "--realtime", "no-slash-here")
    assert result.exit_code == 2
    assert "provider/model" in result.output


def test_set_surfaces_server_validation_422(cli, api):
    api.get("/api/v1/organizations/model-configurations/v2").mock(
        return_value=httpx.Response(200, json=load_fixture("model_config_v2"))
    )
    api.put("/api/v1/organizations/model-configurations/v2").mock(
        return_value=httpx.Response(422, json={"detail": "Unknown realtime model"})
    )
    result = cli("models", "set", "--realtime", "google_realtime/nope")
    assert result.exit_code == 1
    assert "422" in result.output and "Unknown realtime model" in result.output
