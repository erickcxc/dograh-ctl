"""serve: the operations MCP server. Tools are the run-it verbs, never authoring."""

import asyncio


def test_serve_exposes_operations_tools():
    from dograh_ctl.serve import build_server

    server = build_server()
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    assert {
        "agents_list",
        "agents_get",
        "runs_list",
        "runs_latency",
        "runs_trigger",
        "runs_transcript",
        "numbers_list",
        "numbers_assign",
        "models_show",
        "models_set",
        "campaigns_status",
    } <= names
    # authoring belongs to Dograh's own MCP at /api/v1/mcp
    assert not {"create_workflow", "save_workflow"} & names


def test_serve_trigger_tool_is_marked_destructive_and_others_read_only():
    from dograh_ctl.serve import build_server

    tools = {t.name: t for t in asyncio.run(build_server().list_tools())}
    # mcp 2.x ToolAnnotations fields are snake_case
    assert tools["runs_trigger"].annotations.destructive_hint is True
    assert tools["agents_list"].annotations.read_only_hint is True


def test_serve_is_a_cli_command(cli):
    result = cli("serve", "--help")
    assert result.exit_code == 0
    assert "MCP" in result.output


# --- lifecycle (agent-first): create -> set_prompt -> validate -> publish -> chat ------------
import json  # noqa: E402

import httpx  # noqa: E402
from conftest import load_fixture  # noqa: E402

LIFECYCLE_TOOLS = {
    "agents_create",
    "agents_set_prompt",
    "agents_set_model",
    "agents_validate",
    "agents_publish",
    "agents_chat",
    "numbers_add",
    "campaigns_list",
    "campaigns_create",
    "campaigns_start",
    "campaigns_pause",
    "telephony_configs",
    "tools_list",
    "keys_list",
}


def _tools():
    from dograh_ctl.serve import build_server

    return {t.name: t for t in asyncio.run(build_server().list_tools())}


def _call(name, **args):
    """Call a tool in-process and return its JSON payload (mcp 2.x result shapes)."""
    from dograh_ctl.serve import build_server

    result = asyncio.run(build_server().call_tool(name, args))
    if isinstance(result, tuple):  # (content, structured)
        content, structured = result
        return structured if structured else json.loads(content[0].text)
    sc = getattr(result, "structured_content", None) or getattr(result, "structuredContent", None)
    if sc:
        return sc.get("result", sc)
    return json.loads(result.content[0].text)


def test_serve_exposes_lifecycle_tools_but_never_key_minting():
    names = set(_tools())
    assert LIFECYCLE_TOOLS <= names
    assert not {"keys_create", "keys_revoke", "numbers_remove"} & names


def test_serve_lifecycle_annotations():
    tools = _tools()
    assert tools["campaigns_start"].annotations.destructive_hint is True
    for name in (
        "agents_create",
        "agents_set_prompt",
        "agents_publish",
        "numbers_add",
        "campaigns_create",
    ):
        assert tools[name].annotations.read_only_hint is False, name
        assert tools[name].annotations.destructive_hint is False, name
    for name in (
        "campaigns_list",
        "telephony_configs",
        "tools_list",
        "keys_list",
        "agents_validate",
    ):
        assert tools[name].annotations.read_only_hint is True, name


def test_serve_lifecycle_flow_create_prompt_validate_publish_chat(api):
    wf = load_fixture("workflow_fetch_one")
    api.post("/api/v1/workflow/create/template").mock(
        return_value=httpx.Response(
            200, json=dict(wf, id=9, name="Outbound demo", version_status="published")
        )
    )
    api.get("/api/v1/workflow/fetch/9").mock(
        return_value=httpx.Response(200, json=dict(wf, id=9, version_status="published"))
    )
    draft = api.post("/api/v1/workflow/9/create-draft").mock(
        return_value=httpx.Response(200, json={"id": 9})
    )
    put = api.put("/api/v1/workflow/9").mock(return_value=httpx.Response(200, json={"id": 9}))
    api.post("/api/v1/workflow/9/validate").mock(
        return_value=httpx.Response(200, json={"valid": True, "errors": []})
    )
    api.post("/api/v1/workflow/9/publish").mock(
        return_value=httpx.Response(200, json={"id": 9, "version_number": 2, "status": "published"})
    )
    session = load_fixture("text_chat_session")
    api.post("/api/v1/workflow/9/text-chat/sessions").mock(
        return_value=httpx.Response(200, json=session)
    )
    api.post(f"/api/v1/workflow/9/text-chat/sessions/{session['workflow_run_id']}/messages").mock(
        return_value=httpx.Response(200, json=session)
    )
    api.post(f"/api/v1/workflow/9/text-chat/sessions/{session['workflow_run_id']}/end").mock(
        return_value=httpx.Response(200, json=dict(session, state="completed"))
    )

    created = _call("agents_create", use_case="outbound demo", description="call people back")
    assert created["id"] == 9 and "agents_set_prompt" in created["next"]
    prompted = _call("agents_set_prompt", agent_id=9, prompt="Be brief.")
    assert draft.call_count == 1 and put.call_count == 1  # draft rule honoured
    assert json.loads(put.calls.last.request.content)["workflow_definition"]["nodes"]
    assert "agents_validate" in prompted["next"]
    assert _call("agents_validate", agent_id=9)["valid"] is True
    published = _call("agents_publish", agent_id=9)
    assert published["version_number"] == 2 and "agents_chat" in published["next"]
    chat = _call("agents_chat", agent_id=9, message="hi")
    assert chat["run_id"] == session["workflow_run_id"] and isinstance(chat["replies"], list)
    assert "api_key" not in json.dumps(created)  # scrubbed
