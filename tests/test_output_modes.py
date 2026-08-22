"""--json works before or after the command; --version prints the package version."""
import json
import pathlib

import httpx
from conftest import load_fixture


def test_root_json_flag_prints_raw_payload(cli, api):
    api.get("/api/v1/workflow/fetch").mock(return_value=httpx.Response(200, json=load_fixture("workflows_list")))
    result = cli("--json", "agents", "list")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload[0]["id"] == 7
    assert payload[0]["name"] == "Stream Call-In"


def test_trailing_json_flag_on_a_command(cli, api):
    api.get("/api/v1/workflow/fetch").mock(return_value=httpx.Response(200, json=load_fixture("workflows_list")))
    result = cli("agents", "list", "--json")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)[1]["status"] == "archived"


def test_version_flag():
    import tomllib
    from conftest import CliRunner

    from dograh_ctl import __version__
    from dograh_ctl.main import app

    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output
    # the package version and pyproject must never drift
    pyproject = tomllib.loads((pathlib.Path(__file__).parents[1] / "pyproject.toml").read_text())
    assert __version__ == pyproject["project"]["version"]
