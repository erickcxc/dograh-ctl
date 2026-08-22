"""agents set-prompt --node: reach startCall/globalNode/endCall prompts, not only agentNode."""
import json

import httpx
from conftest import load_fixture


def _agent_with_nodes():
    wf = load_fixture("workflow_fetch_one")
    wf["version_status"] = "draft"
    wf["workflow_definition"]["nodes"] = [
        {"id": "1", "type": "startCall", "data": {"prompt": "hello"}},
        {"id": "2", "type": "agentNode", "data": {"prompt": "agenda"}},
        {"id": "4", "type": "endCall", "data": {"prompt": "bye", "is_end": True}},
    ]
    return wf


def test_set_prompt_default_touches_agent_node_only(cli, api):
    api.get("/api/v1/workflow/fetch/7").mock(return_value=httpx.Response(200, json=_agent_with_nodes()))
    put = api.put("/api/v1/workflow/7").mock(return_value=httpx.Response(200, json={"id": 7}))
    assert cli("agents", "set-prompt", "7", "NEW").exit_code == 0
    nodes = {n["id"]: n["data"]["prompt"] for n in json.loads(put.calls.last.request.content)["workflow_definition"]["nodes"]}
    assert nodes == {"1": "hello", "2": "NEW", "4": "bye"}


def test_set_prompt_node_end_call(cli, api):
    api.get("/api/v1/workflow/fetch/7").mock(return_value=httpx.Response(200, json=_agent_with_nodes()))
    put = api.put("/api/v1/workflow/7").mock(return_value=httpx.Response(200, json={"id": 7}))
    result = cli("agents", "set-prompt", "7", "Say goodbye once.", "--node", "endCall")
    assert result.exit_code == 0, result.output
    nodes = {n["id"]: n["data"]["prompt"] for n in json.loads(put.calls.last.request.content)["workflow_definition"]["nodes"]}
    assert nodes == {"1": "hello", "2": "agenda", "4": "Say goodbye once."}
    assert "endCall" in result.output


def test_set_prompt_rejects_unknown_node_type(cli, api):
    result = cli("agents", "set-prompt", "7", "x", "--node", "bogus")
    assert result.exit_code == 2 and "bogus" in result.output
