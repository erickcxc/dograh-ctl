"""campaigns: list / create (CSV presign + upload + create) / start / pause / status."""
import json

import httpx
from conftest import load_fixture


def test_list_shows_state_and_progress(cli, api):
    api.get("/api/v1/campaign/").mock(
        return_value=httpx.Response(200, json={"campaigns": [load_fixture("campaign")]})
    )
    result = cli("campaigns", "list")
    assert result.exit_code == 0, result.output
    assert "Aug outreach" in result.output and "created" in result.output
    result = cli("campaigns", "list", "--json")
    assert json.loads(result.output)[0]["id"] == 21


def test_create_presigns_uploads_csv_then_creates(cli, api, tmp_path):
    csv = tmp_path / "leads.csv"
    csv.write_text("phone_number,name\n+13135550100,Ada\n")
    presign = api.post("/api/v1/s3/presigned-upload-url").mock(
        return_value=httpx.Response(
            200,
            json={"upload_url": "https://minio.test/bucket/campaigns/1/leads.csv?sig=x", "file_key": "campaigns/1/leads.csv", "expires_in": 600},
        )
    )
    upload = api.put("https://minio.test/bucket/campaigns/1/leads.csv", params={"sig": "x"}).mock(
        return_value=httpx.Response(200)
    )
    create = api.post("/api/v1/campaign/create").mock(return_value=httpx.Response(200, json=load_fixture("campaign")))
    result = cli(
        "campaigns", "create", "--name", "Aug outreach", "--agent", "7", "--csv", str(csv),
        "--max-concurrency", "2", "--json",
    )
    assert result.exit_code == 0, result.output
    presign_body = json.loads(presign.calls.last.request.content)
    assert presign_body["file_name"] == "leads.csv" and presign_body["file_size"] == csv.stat().st_size
    assert upload.calls.last.request.content == csv.read_bytes()
    body = json.loads(create.calls.last.request.content)
    assert body == {
        "name": "Aug outreach",
        "workflow_id": 7,
        "source_type": "csv",
        "source_id": "campaigns/1/leads.csv",
        "max_concurrency": 2,
    }
    assert json.loads(result.output)["id"] == 21


def test_create_rejects_non_csv(cli, api, tmp_path):
    f = tmp_path / "leads.txt"
    f.write_text("x")
    result = cli("campaigns", "create", "--name", "x", "--agent", "7", "--csv", str(f))
    assert result.exit_code == 1
    assert ".csv" in result.output


def test_start_requires_yes_then_posts(cli, api):
    route = api.post("/api/v1/campaign/21/start").mock(
        return_value=httpx.Response(200, json=dict(load_fixture("campaign"), state="running"))
    )
    result = cli("campaigns", "start", "21")
    assert result.exit_code == 1 and route.call_count == 0
    result = cli("campaigns", "start", "21", "--yes")
    assert result.exit_code == 0, result.output
    assert route.call_count == 1
    assert "running" in result.output


def test_pause_posts_without_confirmation(cli, api):
    route = api.post("/api/v1/campaign/21/pause").mock(
        return_value=httpx.Response(200, json=dict(load_fixture("campaign"), state="paused"))
    )
    result = cli("campaigns", "pause", "21")
    assert result.exit_code == 0, result.output
    assert route.call_count == 1


def test_status_merges_campaign_and_progress(cli, api):
    api.get("/api/v1/campaign/21").mock(return_value=httpx.Response(200, json=load_fixture("campaign")))
    api.get("/api/v1/campaign/21/progress").mock(
        return_value=httpx.Response(200, json=load_fixture("campaign_progress"))
    )
    result = cli("campaigns", "status", "21")
    assert result.exit_code == 0, result.output
    assert "running" in result.output and "33.3" in result.output
    result = cli("campaigns", "status", "21", "--json")
    payload = json.loads(result.output)
    assert payload["campaign"]["id"] == 21 and payload["progress"]["processed_rows"] == 1
