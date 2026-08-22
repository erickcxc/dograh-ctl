"""Every failure is one line and an exit code; never a traceback."""
import httpx


def test_missing_env_exits_2_with_hint(cli, no_env):
    result = cli("ping")
    assert result.exit_code == 2
    assert "DOGRAH_BASE_URL" in result.output
    assert "Traceback" not in result.output


def test_http_401_exits_1_with_status_and_detail(cli, api):
    api.get("/api/v1/organizations/telephony-configs").mock(
        return_value=httpx.Response(401, json={"detail": "Invalid API key"})
    )
    result = cli("ping")
    assert result.exit_code == 1
    assert "401" in result.output
    assert "Invalid API key" in result.output
    assert "Traceback" not in result.output


def test_connection_failure_exits_1_naming_the_host(cli, api):
    api.get("/api/v1/organizations/telephony-configs").mock(
        side_effect=httpx.ConnectError("connection refused")
    )
    result = cli("ping")
    assert result.exit_code == 1
    assert "dograh.test" in result.output
    assert "Traceback" not in result.output
