"""campaigns watch: a live dashboard of a campaign and its calls (one snapshot with --once)."""
import json

import httpx
from conftest import load_fixture

RUNS = {
    "runs": [
        {"id": 601, "name": "WR-CAMP-0001", "is_completed": False, "called_number": "+13135550100",
         "call_duration_seconds": None, "disposition": None, "created_at": "2026-08-21T19:12:05Z"},
        {"id": 600, "name": "WR-CAMP-0000", "is_completed": True, "called_number": "+13135550199",
         "call_duration_seconds": 41, "disposition": "completed", "created_at": "2026-08-21T19:11:00Z"},
    ],
    "total_count": 2,
}


def _mock(api):
    api.get("/api/v1/campaign/21").mock(return_value=httpx.Response(200, json=load_fixture("campaign")))
    api.get("/api/v1/campaign/21/progress").mock(
        return_value=httpx.Response(200, json=load_fixture("campaign_progress"))
    )
    api.get("/api/v1/campaign/21/runs").mock(return_value=httpx.Response(200, json=RUNS))


def test_watch_once_renders_progress_and_runs(cli, api):
    _mock(api)
    result = cli("campaigns", "watch", "21", "--once")
    assert result.exit_code == 0, result.output
    assert "Aug outreach" in result.output and "running" in result.output
    assert "1/3" in result.output and "33" in result.output  # processed + percentage
    assert "601" in result.output and "41s" in result.output and "completed" in result.output
    # phone numbers are shown masked: never the full number on screen
    assert "+13135550100" not in result.output and "0100" in result.output


def test_watch_once_json_snapshot(cli, api):
    _mock(api)
    result = cli("campaigns", "watch", "21", "--once", "--json")
    snap = json.loads(result.output)
    assert snap["campaign"]["id"] == 21 and snap["progress"]["state"] == "running"
    assert [r["id"] for r in snap["runs"]] == [601, 600]
