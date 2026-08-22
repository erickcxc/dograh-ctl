"""agents: list / create / set-prompt / rename (shipped Day 8), get / set-model / publish / validate (Day 9)."""
import json

import httpx
from conftest import load_fixture


def test_create_posts_template_request_and_prints_new_id(cli, api):
    route = api.post("/api/v1/workflow/create/template").mock(
        return_value=httpx.Response(200, json=load_fixture("workflow_fetch_one"))
    )
    result = cli("agents", "create", "-u", "stream call-in", "-d", "Answer viewer calls", "--json")
    assert result.exit_code == 0, result.output
    sent = json.loads(route.calls.last.request.content)
    assert sent == {"call_type": "inbound", "use_case": "stream call-in", "activity_description": "Answer viewer calls"}
    assert json.loads(result.output)["id"] == 7


def test_set_prompt_rewrites_only_agent_nodes_via_put(cli, api):
    api.get("/api/v1/workflow/fetch/7").mock(return_value=httpx.Response(200, json=load_fixture("workflow_fetch_one")))
    put = api.put("/api/v1/workflow/7").mock(return_value=httpx.Response(200, json={"id": 7}))
    result = cli("agents", "set-prompt", "7", "New prompt text")
    assert result.exit_code == 0, result.output
    body = json.loads(put.calls.last.request.content)
    nodes = body["workflow_definition"]["nodes"]
    assert [n["data"].get("prompt") for n in nodes if n["type"] == "agentNode"] == ["New prompt text"]
    assert [n for n in nodes if n["type"] == "startNode"][0]["data"] == {}


def test_set_prompt_fails_cleanly_when_no_agent_node(cli, api):
    wf = load_fixture("workflow_fetch_one")
    wf["workflow_definition"]["nodes"] = [{"id": "start", "type": "startNode", "data": {}}]
    api.get("/api/v1/workflow/fetch/7").mock(return_value=httpx.Response(200, json=wf))
    result = cli("agents", "set-prompt", "7", "x")
    assert result.exit_code == 1
    assert "agentNode" in result.output


def test_rename_puts_name_only(cli, api):
    # rename reads the agent first (draft guard); the fixture is already a draft, so no create-draft
    api.get("/api/v1/workflow/fetch/7").mock(return_value=httpx.Response(200, json=load_fixture("workflow_fetch_one")))
    put = api.put("/api/v1/workflow/7").mock(return_value=httpx.Response(200, json={"id": 7, "name": "Renamed"}))
    result = cli("agents", "rename", "7", "Renamed", "--json")
    assert result.exit_code == 0, result.output
    assert json.loads(put.calls.last.request.content) == {"name": "Renamed"}
    assert json.loads(result.output)["name"] == "Renamed"


def test_set_prompt_creates_a_draft_first_when_agent_is_published(cli, api):
    """Live finding (rehost box): PUT /workflow/{id} with no draft returns 500; create-draft first."""
    wf = dict(load_fixture("workflow_fetch_one"), version_status="published")
    api.get("/api/v1/workflow/fetch/7").mock(return_value=httpx.Response(200, json=wf))
    draft = api.post("/api/v1/workflow/7/create-draft").mock(
        return_value=httpx.Response(200, json={"id": 7, "version_status": "draft"})
    )
    put = api.put("/api/v1/workflow/7").mock(return_value=httpx.Response(200, json={"id": 7}))
    result = cli("agents", "set-prompt", "7", "New prompt")
    assert result.exit_code == 0, result.output
    assert draft.call_count == 1 and put.call_count == 1


def test_rename_creates_a_draft_first_when_agent_is_published(cli, api):
    wf = dict(load_fixture("workflow_fetch_one"), version_status="published")
    api.get("/api/v1/workflow/fetch/7").mock(return_value=httpx.Response(200, json=wf))
    draft = api.post("/api/v1/workflow/7/create-draft").mock(
        return_value=httpx.Response(200, json={"id": 7, "version_status": "draft"})
    )
    put = api.put("/api/v1/workflow/7").mock(return_value=httpx.Response(200, json={"id": 7, "name": "Renamed"}))
    result = cli("agents", "rename", "7", "Renamed")
    assert result.exit_code == 0, result.output
    assert draft.call_count == 1 and put.call_count == 1
