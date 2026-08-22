"""agents get / set-model / publish / validate (Day 9, built live)."""
import json

import httpx
from conftest import load_fixture


def test_get_summarizes_agent_version_nodes_and_model_override(cli, api):
    api.get("/api/v1/workflow/fetch/7").mock(
        return_value=httpx.Response(200, json=load_fixture("workflow_fetch_one"))
    )
    result = cli("agents", "get", "7")
    assert result.exit_code == 0, result.output
    assert "Stream Call-In" in result.output
    assert "draft" in result.output and "3" in result.output  # version 3, draft
    assert "agentNode" in result.output  # node summary
    assert "google_realtime" in result.output and "gemini-3.1-flash-live-preview" in result.output
    assert "abcd" not in result.output  # even masked key tails are not printed


def test_get_json_is_raw(cli, api):
    api.get("/api/v1/workflow/fetch/7").mock(
        return_value=httpx.Response(200, json=load_fixture("workflow_fetch_one"))
    )
    result = cli("agents", "get", "7", "--json")
    assert json.loads(result.output)["workflow_uuid"].startswith("0d6f3c2a")


def test_set_model_puts_complete_override_based_on_existing_override(cli, api):
    api.get("/api/v1/workflow/fetch/7").mock(
        return_value=httpx.Response(200, json=load_fixture("workflow_fetch_one"))
    )
    put = api.put("/api/v1/workflow/7").mock(return_value=httpx.Response(200, json={"id": 7}))
    result = cli("agents", "set-model", "7", "--realtime", "openai_realtime/gpt-realtime-2")
    assert result.exit_code == 0, result.output
    body = json.loads(put.calls.last.request.content)
    override = body["workflow_configurations"]["model_configuration_v2_override"]
    assert override["version"] == 2 and override["mode"] == "byok"
    rt = override["byok"]["realtime"]["realtime"]
    assert rt == {"provider": "openai_realtime", "model": "gpt-realtime-2", "api_key": "****abcd"}
    assert override["byok"]["realtime"]["llm"]["model"] == "gpt-4.1-mini"
    assert "publish" in result.output  # reminds that this saved a draft


def test_set_model_falls_back_to_org_config_when_agent_has_no_override(cli, api):
    wf = load_fixture("workflow_fetch_one")
    wf["workflow_configurations"] = {"max_call_duration": 600}
    api.get("/api/v1/workflow/fetch/7").mock(return_value=httpx.Response(200, json=wf))
    api.get("/api/v1/organizations/model-configurations/v2").mock(
        return_value=httpx.Response(200, json=load_fixture("model_config_v2"))
    )
    put = api.put("/api/v1/workflow/7").mock(return_value=httpx.Response(200, json={"id": 7}))
    result = cli("agents", "set-model", "7", "--realtime", "google_realtime/gemini-3.1-flash-live-preview")
    assert result.exit_code == 0, result.output
    body = json.loads(put.calls.last.request.content)
    assert body["workflow_configurations"]["max_call_duration"] == 600  # other keys preserved
    rt = body["workflow_configurations"]["model_configuration_v2_override"]["byok"]["realtime"]["realtime"]
    assert rt["provider"] == "google_realtime" and rt["api_key"] == "****1234"


def test_publish_posts_and_reports(cli, api):
    route = api.post("/api/v1/workflow/7/publish").mock(
        return_value=httpx.Response(200, json={"id": 7, "version_number": 4, "status": "published"})
    )
    result = cli("agents", "publish", "7")
    assert result.exit_code == 0, result.output
    assert route.call_count == 1
    assert "published" in result.output


def test_validate_posts_and_prints_result(cli, api):
    api.post("/api/v1/workflow/7/validate").mock(
        return_value=httpx.Response(200, json={"valid": True, "errors": []})
    )
    result = cli("agents", "validate", "7", "--json")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["valid"] is True


def test_set_model_creates_a_draft_first_when_agent_is_published(cli, api):
    """Live finding (rehost box): PUT /workflow/{id} with no draft returns 500; create-draft first."""
    wf = dict(load_fixture("workflow_fetch_one"), version_status="published")
    api.get("/api/v1/workflow/fetch/7").mock(return_value=httpx.Response(200, json=wf))
    draft = api.post("/api/v1/workflow/7/create-draft").mock(
        return_value=httpx.Response(200, json={"id": 7, "version_status": "draft"})
    )
    put = api.put("/api/v1/workflow/7").mock(return_value=httpx.Response(200, json={"id": 7}))
    result = cli("agents", "set-model", "7", "--realtime", "openai_realtime/gpt-realtime-2")
    assert result.exit_code == 0, result.output
    assert draft.call_count == 1 and put.call_count == 1
