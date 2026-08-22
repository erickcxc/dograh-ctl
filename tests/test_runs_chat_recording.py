"""runs chat (text session, no telephony) and runs recording (download the public artifact)."""
import json

import httpx
from conftest import load_fixture


def test_chat_sends_messages_and_ends_session(cli, api):
    session = load_fixture("text_chat_session")
    create = api.post("/api/v1/workflow/7/text-chat/sessions").mock(
        return_value=httpx.Response(200, json=session)
    )
    reply = dict(session, revision=2)
    reply["session_data"] = {
        "messages": session["session_data"]["messages"]
        + [
            {"role": "user", "content": "a voice CLI"},
            {"role": "assistant", "content": "Nice. Tell me more about the CLI."},
        ]
    }
    append = api.post("/api/v1/workflow/7/text-chat/sessions/777/messages").mock(
        return_value=httpx.Response(200, json=reply)
    )
    end = api.post("/api/v1/workflow/7/text-chat/sessions/777/end").mock(
        return_value=httpx.Response(200, json=dict(reply, state="ended", is_completed=True))
    )
    result = cli("runs", "chat", "7", input="a voice CLI\n")
    assert result.exit_code == 0, result.output
    assert create.call_count == 1
    sent = json.loads(append.calls.last.request.content)
    assert sent["text"] == "a voice CLI" and sent["expected_revision"] == 1
    assert "Tell me more about the CLI." in result.output
    assert end.call_count == 1


def test_chat_one_shot_message_flag(cli, api):
    session = load_fixture("text_chat_session")
    api.post("/api/v1/workflow/7/text-chat/sessions").mock(return_value=httpx.Response(200, json=session))
    api.post("/api/v1/workflow/7/text-chat/sessions/777/messages").mock(
        return_value=httpx.Response(200, json=dict(session, revision=2))
    )
    api.post("/api/v1/workflow/7/text-chat/sessions/777/end").mock(
        return_value=httpx.Response(200, json=dict(session, state="ended"))
    )
    result = cli("runs", "chat", "7", "-m", "hello there", "--json")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["workflow_run_id"] == 777


def test_recording_downloads_public_artifact_to_file(cli, api, tmp_path):
    api.get("/api/v1/organizations/usage/runs").mock(return_value=httpx.Response(200, json=load_fixture("usage_runs")))
    run = {
        "id": 501,
        "workflow_id": 7,
        "recording_public_url": "https://dograh.test/api/v1/public/download/workflow/tok501/recording",
        "transcript_public_url": None,
    }
    api.get("/api/v1/workflow/7/runs/501").mock(return_value=httpx.Response(200, json=run))
    api.get("/api/v1/public/download/workflow/tok501/recording").mock(
        return_value=httpx.Response(200, content=b"RIFFfakewav", headers={"content-type": "audio/wav"})
    )
    out = tmp_path / "call.wav"
    result = cli("runs", "recording", "501", "--out", str(out))
    assert result.exit_code == 0, result.output
    assert out.read_bytes() == b"RIFFfakewav"


def test_recording_without_artifact_exits_1(cli, api, tmp_path):
    api.get("/api/v1/organizations/usage/runs").mock(return_value=httpx.Response(200, json=load_fixture("usage_runs")))
    api.get("/api/v1/workflow/7/runs/500").mock(
        return_value=httpx.Response(200, json={"id": 500, "workflow_id": 7, "recording_public_url": None})
    )
    result = cli("runs", "recording", "500", "--out", str(tmp_path / "x.wav"))
    assert result.exit_code == 1
    assert "no recording" in result.output
