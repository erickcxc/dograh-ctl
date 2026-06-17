# dograh-ctl

A CLI to run a self-hosted [Dograh](https://github.com/dograh-hq/dograh) voice-agent platform from the terminal: manage agents, telephony, and models, and pull call metrics, without clicking through the dashboard.

Built live on the AI by Erick stream.

## Why

Dograh ships a REST API, generated SDKs, and a dashboard, but no command line. `dograh-ctl` is the missing terminal control surface, so the whole setup is scriptable.

## Setup

```bash
pip install -e .
cp .env.example .env   # then fill in your values
export DOGRAH_BASE_URL=https://your-dograh-host
export DOGRAH_API_KEY=dgr_xxx   # create one in Dograh -> Developers
```

## Usage

```bash
dograh-ctl ping            # verify connectivity + API-key auth
```

More commands are built live on stream:

- `agents list` / `agents create`
- `runs list` / `runs latency`
- `numbers list` / `numbers assign`
- `models set`

Auth is the `X-API-Key` header; the client reads `DOGRAH_BASE_URL` and `DOGRAH_API_KEY` from the environment. Your key stays in `.env` (gitignored), never in the repo.

> Next episode: wrap these commands as an MCP server so an agent can drive Dograh.

## License

MIT
