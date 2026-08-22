"""runs trigger / transcript (Day 9, built live)."""
import json

import httpx
from conftest import load_fixture

INITIATED = {"message": "Call initiated successfully with run name WR-TEL-OUT-00012345"}


def test_trigger_needs_yes_then_calls_and_resolves_run_id_by_name(cli, api):
    call = api.post("/api/v1/telephony/initiate-call").mock(return_value=httpx.Response(200, json=INITIATED))
    api.get("/api/v1/organizations/usage/runs").mock(return_value=httpx.Response(200, json=load_fixture("usage_runs")))
    result = cli("runs", "trigger", "7", "--to", "+13135550100")
    assert result.exit_code == 1 and call.call_count == 0
    result = cli("runs", "trigger", "7", "--to", "+13135550100", "--yes")
    assert result.exit_code == 0, result.output
    assert json.loads(call.calls.last.request.content) == {"workflow_id": 7, "phone_number": "+13135550100"}
    assert "WR-TEL-OUT-00012345" in result.output
    assert "501" in result.output  # resolved from usage/runs by run name


def test_trigger_json_includes_run_id_and_name(cli, api):
    api.post("/api/v1/telephony/initiate-call").mock(return_value=httpx.Response(200, json=INITIATED))
    api.get("/api/v1/organizations/usage/runs").mock(return_value=httpx.Response(200, json=load_fixture("usage_runs")))
    result = cli("runs", "trigger", "7", "--to", "+13135550100", "--yes", "--json")
    payload = json.loads(result.output)
    assert payload["run_name"] == "WR-TEL-OUT-00012345" and payload["run_id"] == 501


def test_trigger_passes_config_and_from_number(cli, api):
    call = api.post("/api/v1/telephony/initiate-call").mock(return_value=httpx.Response(200, json=INITIATED))
    api.get("/api/v1/organizations/usage/runs").mock(return_value=httpx.Response(200, json=load_fixture("usage_runs")))
    result = cli("runs", "trigger", "7", "--to", "+13135550100", "--config", "3", "--from-id", "11", "--yes")
    assert result.exit_code == 0, result.output
    body = json.loads(call.calls.last.request.content)
    assert body["telephony_configuration_id"] == 3 and body["from_phone_number_id"] == 11


def test_trigger_surfaces_telephony_not_configured(cli, api):
    api.post("/api/v1/telephony/initiate-call").mock(
        return_value=httpx.Response(400, json={"detail": "telephony_not_configured"})
    )
    result = cli("runs", "trigger", "7", "--to", "+13135550100", "--yes")
    assert result.exit_code == 1
    assert "telephony_not_configured" in result.output


def test_transcript_fetches_public_artifact_and_prints_turns(cli, api):
    api.get("/api/v1/organizations/usage/runs").mock(return_value=httpx.Response(200, json=load_fixture("usage_runs")))
    api.get("/api/v1/workflow/7/runs/501").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 501,
                "workflow_id": 7,
                "transcript_public_url": "https://dograh.test/api/v1/public/download/workflow/tok501/transcript",
            },
        )
    )
    api.get("/api/v1/public/download/workflow/tok501/transcript").mock(
        return_value=httpx.Response(200, text="user: hi there\nassistant: hello, what are you building?\n")
    )
    result = cli("runs", "transcript", "501")
    assert result.exit_code == 0, result.output
    assert "hello, what are you building?" in result.output
    result = cli("runs", "transcript", "501", "--json")
    payload = json.loads(result.output)
    assert payload["run_id"] == 501 and "hi there" in payload["transcript"]


def test_transcript_handles_json_turns(cli, api):
    api.get("/api/v1/workflow/7/runs/501").mock(
        return_value=httpx.Response(
            200,
            json={"id": 501, "workflow_id": 7, "transcript_public_url": "https://dograh.test/api/v1/public/download/workflow/tok501/transcript"},
        )
    )
    api.get("/api/v1/public/download/workflow/tok501/transcript").mock(
        return_value=httpx.Response(200, json=[{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hey"}])
    )
    result = cli("runs", "transcript", "501", "--agent", "7")
    assert result.exit_code == 0, result.output
    assert "user" in result.output and "hey" in result.output


def test_transcript_missing_exits_1(cli, api):
    api.get("/api/v1/workflow/7/runs/500").mock(
        return_value=httpx.Response(200, json={"id": 500, "workflow_id": 7, "transcript_public_url": None})
    )
    result = cli("runs", "transcript", "500", "--agent", "7")
    assert result.exit_code == 1
    assert "no transcript" in result.output
