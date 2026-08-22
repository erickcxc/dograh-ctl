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
