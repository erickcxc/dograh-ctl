"""tools: list (with status/category filters)."""
import json

import httpx
from conftest import load_fixture


def test_tools_list_shows_name_category_status(cli, api):
    api.get("/api/v1/tools/").mock(return_value=httpx.Response(200, json=load_fixture("tools_list")))
    result = cli("tools", "list")
    assert result.exit_code == 0, result.output
    assert "book_demo" in result.output
    assert "mcp" in result.output


def test_tools_list_passes_filters_and_json(cli, api):
    route = api.get("/api/v1/tools/").mock(return_value=httpx.Response(200, json=load_fixture("tools_list")))
    result = cli("tools", "list", "--status", "active", "--category", "mcp", "--json")
    assert result.exit_code == 0, result.output
    params = route.calls.last.request.url.params
    assert params["status"] == "active" and params["category"] == "mcp"
    assert json.loads(result.output)[1]["tool_uuid"] == "t-2222"
