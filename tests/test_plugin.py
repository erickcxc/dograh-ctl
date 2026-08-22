"""The repo doubles as a Claude Code plugin: skill + MCP registration must stay valid."""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).parents[1]


def _frontmatter(path: pathlib.Path) -> dict:
    text = path.read_text()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, f"{path} has no YAML frontmatter"
    fm = {}
    key = None
    for line in m.group(1).splitlines():
        if re.match(r"^[a-z_]+:", line):
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip()
        elif key and line.startswith(" "):
            fm[key] = (fm[key] + " " + line.strip()).strip()
    return fm


def test_plugin_manifest_is_valid_and_versioned_like_the_package():
    from dograh_ctl import __version__

    manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert manifest["name"] == "dograh-ctl"
    assert manifest["version"] == __version__
    assert "description" in manifest and "voice" in manifest["description"].lower()


def test_marketplace_points_at_the_plugin_root():
    mp = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    assert mp["name"] == "dograh-ctl"
    assert mp["plugins"][0]["name"] == "dograh-ctl"
    assert mp["plugins"][0]["source"] in ("./", ".")


def test_mcp_json_registers_dograh_ops_via_uvx_without_secrets():
    cfg = json.loads((ROOT / ".mcp.json").read_text())
    server = cfg["mcpServers"]["dograh-ops"]
    assert server["command"] == "uvx"
    assert server["args"][:2] == ["dograh-ctl", "serve"] or server["args"] == ["dograh-ctl", "serve"]
    # env passes variable NAMES through; never literal values
    for v in (server.get("env") or {}).values():
        assert v.startswith("${") and v.endswith("}")


def test_skill_frontmatter_names_triggers_and_the_lifecycle():
    fm = _frontmatter(ROOT / "skills" / "dograh-ctl" / "SKILL.md")
    assert fm["name"] == "dograh-ctl"
    desc = fm["description"].lower()
    for needle in ("voice agent", "dograh", "call", "transcript"):
        assert needle in desc
    body = (ROOT / "skills" / "dograh-ctl" / "SKILL.md").read_text()
    for step in ("agents_create", "agents_publish", "agents_chat", "runs_trigger", "runs_transcript"):
        assert step in body


def test_setup_command_exists_and_runs_ping():
    text = (ROOT / "commands" / "dograh-ctl-setup.md").read_text()
    assert "dograh-ctl ping" in text
    assert "DOGRAH_BASE_URL" in text and "DOGRAH_API_KEY" in text
    assert "mcp-config" in text


def test_agents_md_exists_and_points_agents_at_json_and_mcp():
    text = (ROOT / "AGENTS.md").read_text()
    assert "--json" in text and "serve" in text and "mcp-config" in text


def test_mcp_config_prints_claude_mcp_add_and_json(cli):
    result = cli("mcp-config")
    assert result.exit_code == 0, result.output
    assert "claude mcp add dograh-ops -- uvx dograh-ctl serve" in result.output
    assert "${DOGRAH_API_KEY}" in result.output
    result = cli("mcp-config", "--json")
    assert json.loads(result.output)["mcpServers"]["dograh-ops"]["args"] == ["dograh-ctl", "serve"]
