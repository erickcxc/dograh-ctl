# AGENTS.md

Notes for AI agents (Claude Code, Codex, Cursor, any MCP client) working with or on dograh-ctl.

## Using dograh-ctl to run a Dograh instance

- Preferred: the MCP server. Register it once with `dograh-ctl mcp-config` (prints the
  `claude mcp add ...` line and the JSON for other clients) or install the Claude Code plugin
  (`claude plugin marketplace add erickcxc/dograh-ctl`, then `claude plugin install dograh-ctl`),
  which registers `dograh-ops` and installs the `dograh-ctl` skill. The skill
  (`skills/dograh-ctl/SKILL.md`) is the lifecycle recipe: create -> set_prompt -> set_model ->
  validate -> publish -> number -> chat test -> call -> transcript.
- From a shell: every command accepts `--json`; parse stdout. Exit code 2 = local configuration
  (env vars missing), 1 = the instance refused or was unreachable (stderr says why). No tracebacks.
- Credentials are environment variables only: `DOGRAH_BASE_URL`, `DOGRAH_API_KEY`. Never print them,
  never write them to files, never ask a user to paste them into chat.
- Real-world side effects: `runs trigger` / `runs_trigger` and `campaigns start` / `campaigns_start`
  place phone calls and cost money; confirm with the human first. `keys create/revoke` and
  `numbers remove` are CLI-only and need `--yes`.
- Edits to an agent are drafts until `agents publish`.
- Graph-level authoring (nodes, edges, attached tools) belongs to Dograh's own MCP server at
  `{DOGRAH_BASE_URL}/api/v1/mcp`; dograh-ctl operates what that produces.

## Working on this repository

- `uv sync` then `uv run pytest` (respx-mocked HTTP; fixtures mirror the Dograh schemas pinned in
  `tests/conftest.py`) and `uv run ruff check .`. CI runs both on Python 3.10 and 3.12; `tomllib`
  is 3.11+, so do not import it in tests.
- Commands live in `dograh_ctl/commands/<group>.py` on `GuardedTyper`; all printing goes through
  `dograh_ctl/output.py`; all HTTP through `dograh_ctl/client.py`. MCP tools in `dograh_ctl/serve.py`
  wrap the same helpers; nothing may print to stdout inside `serve` (stdio transport).
- Tests first. Every command has a happy-path, an error-path, and a `--json` test.
- Releases: bump `pyproject.toml`, `dograh_ctl/__init__.py`, and `.claude-plugin/*.json` together,
  move CHANGELOG `[Unreleased]` under the version, tag `vX.Y.Z`, push; the release workflow publishes
  to PyPI via Trusted Publishing.
