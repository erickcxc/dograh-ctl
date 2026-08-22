# Changelog

All notable changes to dograh-ctl. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.3.0] - 2026-08-22

Agent-first release: Claude Code (or any MCP client) can now create, publish, number, test, and call a voice agent end to end through dograh-ctl.

### Added
- `serve`: full lifecycle tools (`agents_create`, `agents_set_prompt`, `agents_set_model`, `agents_validate`, `agents_publish`, `agents_chat`, `numbers_add`, `campaigns_list/create/start/pause`, `telephony_configs`, `tools_list`, `keys_list`) with `next` hints and a recipe in the server instructions. `keys_create/revoke` and `numbers_remove` stay CLI-only.
- Claude Code plugin in the repo: `.claude-plugin/plugin.json` + `marketplace.json`, plugin-root `.mcp.json` (registers `dograh-ops` via `uvx dograh-ctl serve`), the `dograh-ctl` skill (lifecycle recipe), and the `/dograh-ctl-setup` command.
- `dograh-ctl mcp-config`: prints the `claude mcp add` line and JSON for other MCP clients.
- `AGENTS.md` for agents using or working on the repo.
- `campaigns watch <id>`: live dashboard (progress bar + calls table, numbers masked to the last 4 digits).

## [0.2.1] - 2026-08-22

First PyPI release: `pip install dograh-ctl` / `uv tool install dograh-ctl`.

### Added
- PyPI publishing via GitHub Actions Trusted Publishing (`.github/workflows/release.yml`, runs on version tags).
- CHANGELOG.

### Changed
- README presents the finished command surface (32 commands, 9 groups) instead of a roadmap.
- `pyproject.toml`: `mcp>=2.0` (the server uses the 2.0 `MCPServer` API), project URLs, authors, keywords, classifiers.
- Test fixtures use a placeholder phone number.
- LICENSE names the copyright holder in full.
- Version test asserts `__version__` matches `pyproject.toml` (works on Python 3.10+).

## [0.2.0] - 2026-08-22

The full command map: 32 commands across agents, runs, numbers, models, campaigns, telephony, tools, keys, and an MCP operations server.

### Added
- agents: `get`, `set-model`, `publish`, `validate`.
- runs: `trigger` (place a call, resolves the run id), `transcript`, `recording`, `chat` (text session, no telephony).
- numbers: `add` (register a number you already own), `remove`.
- models: `show`, `set` (read-modify-write; the server re-merges masked secrets).
- campaigns: `list`, `create` (CSV upload), `start`, `pause`, `status`.
- telephony: `configs`, `providers`.
- tools: `list`.
- keys: `list`, `create` (prefix only unless `--reveal`), `revoke`.
- `serve`: MCP server over stdio exposing the operations verbs; `runs_trigger` is annotated destructive, reads are read-only, secrets are stripped from every payload. Dograh's own MCP server keeps authoring.
- `--json` on every command; `--version`.
- Mocked-HTTP test per command, fixtures pinned to the Dograh source at `dograh-hq/dograh@b32187d8`.
- CI (ruff + pytest on Python 3.10 and 3.12); install with `uv tool install git+https://github.com/erickcxc/dograh-ctl`.

### Changed
- Every failure is one line on stderr with an exit code (2 for local configuration, 1 for anything the instance refused or could not be reached for); no tracebacks.
- Verbs that place calls or cost money (`runs trigger`, `campaigns start`, `numbers remove`, `keys revoke`) require confirmation or `--yes`.
- Agent edits (`set-prompt`, `rename`, `set-model`) create a draft first when the agent is published, then save; `agents publish` promotes it.
- `runs list` / `runs latency` cap `--limit` at 100 (server limit).
- `numbers buy` / `numbers release` from the v1 map became `numbers add` / `numbers remove`: Dograh registers numbers, it does not buy or release them at the carrier.
- Requires Python 3.10+.

## [0.1.0] - 2026-06-17

First public cut, built live on Day 8 of the AI by Erick stream.

### Added
- `ping`: connectivity and API-key check.
- agents: `list`, `create`, `set-prompt`, `rename`.
- runs: `list`, `latency` (avg/p50/p95/min/max call duration).
- numbers: `list`, `assign`.
- Thin `httpx` client with `X-API-Key` auth; `typer` + `rich` output; env-only configuration (`DOGRAH_BASE_URL`, `DOGRAH_API_KEY`).

[Unreleased]: https://github.com/erickcxc/dograh-ctl/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/erickcxc/dograh-ctl/releases/tag/v0.2.0
[0.1.0]: https://github.com/erickcxc/dograh-ctl/commit/07e4c43
