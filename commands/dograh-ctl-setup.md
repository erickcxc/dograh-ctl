---
description: Check dograh-ctl is installed and authenticated, and register the dograh-ops MCP server for this project.
---

Get dograh-ctl ready for this session. Do these checks in order and stop at the first failure with a one-line fix for the user.

1. Is `dograh-ctl` on PATH? Run `dograh-ctl --version`. If not: `uv tool install dograh-ctl` (or `pip install dograh-ctl`).
2. Are `DOGRAH_BASE_URL` and `DOGRAH_API_KEY` set in the environment? Check with `test -n "$DOGRAH_BASE_URL" && test -n "$DOGRAH_API_KEY" && echo ok`. Never print their values. If missing, tell the user to export them (the API key is created in Dograh under Developers) and stop.
3. Does the instance answer? Run `dograh-ctl ping`. Expect `OK connected to <host>: auth OK`.
4. Is the MCP server registered? Run `claude mcp list` and look for `dograh-ops`. If missing, run `dograh-ctl mcp-config` and apply its `claude mcp add` line, then tell the user to restart the session so the tools load.
5. Report: version, host (not the key), ping result, MCP status, and the one-line next step: "say what agent you want built".
