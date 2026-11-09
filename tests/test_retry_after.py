import asyncio
import json
from datetime import UTC, datetime
from functools import partial

import httpx
import pytest
from fastmcp import Client

from perseus_mcp import server
from perseus_mcp.upstream import UpstreamFailure, parse_retry_after

NOW = datetime(2026, 11, 9, 14, 0, 0, 500000, tzinfo=UTC)


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, None),
        ("", None),
        ("30", 30),
        (" 30 ", 30),
        ("0", 0),
        ("-1", None),
        ("1.5", None),
        ("private invalid header", None),
        ("Mon, 09 Nov 2026 14:00:31 GMT", 31),
        ("Mon, 09 Nov 2026 13:59:59 GMT", 0),
        ("Monday, 09-Nov-26 14:00:31 GMT", 31),
        ("Mon Nov  9 14:00:31 2026", 31),
        ("Mon, 99 Nov 2026 14:00:31 GMT", None),
    ],
)
def test_retry_after_parsing(value, expected):
    assert parse_retry_after(value, now=NOW) == expected


@pytest.mark.parametrize(
    "status,retryable",
    [
        (400, False),
        (404, False),
        (429, True),
        (500, True),
        (501, False),
        (502, True),
        (503, True),
        (504, True),
        (505, False),
        (511, False),
        (599, False),
    ],
)
@pytest.mark.parametrize(
    "header,delay",
    [
        ("30", 30),
        ("0", 0),
        (None, None),
        ("private invalid header", None),
        ("Mon, 09 Nov 2026 14:00:31 GMT", 31),
    ],
)
def test_http_retry_guidance_reaches_mcp_caller(
    monkeypatch, status, retryable, header, delay
):
    monkeypatch.delenv("PERSEUS_MCP_RETRY_POLICY", raising=False)
    monkeypatch.setattr(
        server, "parse_retry_after", partial(parse_retry_after, now=NOW)
    )
    calls = []

    def respond(request):
        calls.append(request)
        headers = {} if header is None else {"Retry-After": header}
        return httpx.Response(status, headers=headers, text="private upstream body")

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(respond)
        ) as http_client:

            async def shared():
                return http_client

            monkeypatch.setattr(server, "_shared_client", shared)
            async with Client(server.mcp) as client:
                # Python warnings are not part of the MCP result; assert the
                # structured guidance that the remote caller actually receives.
                result = await client.call_tool_mcp(
                    "get_passage", {"urn": "urn:cts:private"}
                )
                assert result.isError
                data = json.loads(result.content[0].text)
                assert data["code"] == "UPSTREAM_HTTP_ERROR"
                assert data["upstream_http_status"] == status
                assert data["retry_after_seconds"] == delay
                assert data["automatic_retry_allowed"] is retryable
                assert "private" not in result.content[0].text

    asyncio.run(run())
    assert len(calls) == 1


@pytest.mark.parametrize("status", [404, 429, 500, 501, 502, 503, 504, 505, 511])
@pytest.mark.parametrize("override", [True, False])
def test_http_policy_override_takes_precedence_without_losing_delay(
    monkeypatch, status, override
):
    monkeypatch.setenv(
        "PERSEUS_MCP_RETRY_POLICY", json.dumps({"UPSTREAM_HTTP_ERROR": override})
    )
    data = json.loads(
        UpstreamFailure(
            "UPSTREAM_HTTP_ERROR", "safe", status, retry_after_seconds=30
        ).as_json()
    )
    assert data["automatic_retry_allowed"] is override
    assert data["retry_after_seconds"] == 30


def test_unrelated_policy_override_preserves_http_status_defaults(monkeypatch):
    monkeypatch.setenv("PERSEUS_MCP_RETRY_POLICY", '{"UPSTREAM_TIMEOUT": false}')
    assert json.loads(UpstreamFailure("UPSTREAM_HTTP_ERROR", "safe", 503).as_json())[
        "automatic_retry_allowed"
    ]


@pytest.mark.parametrize("status", [429, 503])
def test_challenges_do_not_inherit_http_retry_permission(monkeypatch, status):
    monkeypatch.delenv("PERSEUS_MCP_RETRY_POLICY", raising=False)
    data = json.loads(UpstreamFailure("UPSTREAM_CHALLENGE", "safe", status).as_json())
    assert data["automatic_retry_allowed"] is False
    assert data["retry_after_seconds"] is None
