import pytest

from perseus_mcp import server

SETTINGS = (
    "PERSEUS_MCP_RETRY_POLICY",
    "PERSEUS_MCP_MAX_RESPONSE_BYTES",
    "PERSEUS_MCP_BODY_TIMEOUT_SECONDS",
)


@pytest.fixture(autouse=True)
def clean_configuration(monkeypatch):
    for setting in SETTINGS:
        monkeypatch.delenv(setting, raising=False)


@pytest.mark.parametrize(
    "setting,value",
    [
        (SETTINGS[0], "not JSON"),
        (SETTINGS[0], "[]"),
        (SETTINGS[0], '{"UNKNOWN": true}'),
        (SETTINGS[0], '{"UPSTREAM_TIMEOUT": "true"}'),
        (SETTINGS[1], "0"),
        (SETTINGS[1], "-1"),
        (SETTINGS[1], "1.5"),
        (SETTINGS[1], "unlimited"),
        (SETTINGS[2], "0"),
        (SETTINGS[2], "-1"),
        (SETTINGS[2], "nan"),
        (SETTINGS[2], "inf"),
        (SETTINGS[2], "unlimited"),
    ],
)
def test_invalid_configuration_prevents_server_start(monkeypatch, setting, value):
    monkeypatch.setenv(setting, value)
    calls = []
    monkeypatch.setattr(server.mcp, "run", lambda: calls.append("run"))

    with pytest.raises(ValueError, match=setting):
        server.main()

    assert calls == []


@pytest.mark.parametrize("configured", [False, True])
def test_valid_configuration_starts_server(monkeypatch, configured):
    if configured:
        monkeypatch.setenv(SETTINGS[0], '{"UPSTREAM_TIMEOUT": false}')
        monkeypatch.setenv(SETTINGS[1], "1024")
        monkeypatch.setenv(SETTINGS[2], "0.5")
    calls = []
    monkeypatch.setattr(server.mcp, "run", lambda: calls.append("run"))

    server.main()

    assert calls == ["run"]
