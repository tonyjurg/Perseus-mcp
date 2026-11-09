import asyncio
import json
import sys
from pathlib import Path

import pytest

from perseus_mcp.upstream import UpstreamFailure
from scripts import check_cts_upstream as monitor

FIXTURES = Path(__file__).parent / "fixtures/cts"
MANIFEST = json.loads((FIXTURES / "sources.json").read_text(encoding="utf-8"))
SOURCES = MANIFEST["responses"] + MANIFEST["probes"]


def mock_sources(monkeypatch, replacement=None, overrides=None):
    calls = []
    bodies = {
        source["url"]: (FIXTURES / f"{source['operation']}.xml").read_text(
            encoding="utf-8"
        )
        if "root" in source
        else f"<{source['local_root']}/>"
        for source in SOURCES
    }
    if replacement is not None:
        bodies[MANIFEST["responses"][0]["url"]] = replacement
    bodies.update(overrides or {})

    async def get(url):
        calls.append(url)
        body = bodies[url]
        if isinstance(body, Exception):
            raise body
        return body

    monkeypatch.setattr(monitor.server, "_get", get)
    return calls


def test_monitor_checks_all_manifest_urls_against_exact_roots(monkeypatch):
    calls = mock_sources(monkeypatch)
    results = asyncio.run(monitor.check_sources(MANIFEST))
    assert calls == [source["url"] for source in SOURCES]
    assert all(result["ok"] for result in results)
    assert [result["observed_root"] for result in results] == [
        source.get("root", source.get("local_root")) for source in SOURCES
    ]


@pytest.mark.parametrize(
    "body,code,observed",
    [
        (
            '<GetPassage xmlns="https://example.invalid/cts-next"/>',
            "ROOT_OR_NAMESPACE_CHANGED",
            "{https://example.invalid/cts-next}GetPassage",
        ),
        (
            '<TEI xmlns="http://www.tei-c.org/ns/1.0"/>',
            "ROOT_OR_NAMESPACE_CHANGED",
            "{http://www.tei-c.org/ns/1.0}TEI",
        ),
        ("<Unexpected/>", "INVALID_PAYLOAD", "Unexpected"),
        ("<broken>", "INVALID_PAYLOAD", None),
        (
            UpstreamFailure("UPSTREAM_CHALLENGE", "safe", 403),
            "UPSTREAM_CHALLENGE",
            None,
        ),
        (TimeoutError(), "UPSTREAM_TIMEOUT", None),
    ],
)
def test_monitor_reports_drift_or_failure_and_continues(
    monkeypatch, body, code, observed
):
    calls = mock_sources(monkeypatch, body)
    results = asyncio.run(monitor.check_sources(MANIFEST))
    assert len(calls) == 7
    assert results[0]["ok"] is False
    assert results[0]["error"] == code
    assert results[0]["observed_root"] == observed
    assert results[0]["outcome"] == (
        "failed" if code in monitor.FORMAT_FAILURES else "inconclusive"
    )
    assert all(result["ok"] for result in results[1:])


def test_monitor_ignores_prefix_spelling(monkeypatch):
    body = (FIXTURES / "GetPassage.xml").read_text(encoding="utf-8")
    mock_sources(
        monkeypatch, body.replace("xmlns:cts", "xmlns:new").replace("cts:", "new:")
    )
    assert asyncio.run(monitor.check_sources(MANIFEST))[0]["ok"]


@pytest.mark.parametrize("changed", [False, True])
def test_monitor_exit_code_and_saved_report(monkeypatch, tmp_path, changed):
    mock_sources(monkeypatch, "<GetPassage/>" if changed else None)
    report = tmp_path / "report.json"
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setattr(sys, "argv", ["check_cts_upstream.py", "--report", str(report)])
    assert monitor.main() == int(changed)
    saved = json.loads(report.read_text(encoding="utf-8"))
    assert len(saved["results"]) == 7
    assert saved["outcome"] == ("failed" if changed else "ok")
    assert saved["baseline_captured"] == MANIFEST["captured"]
    assert "Live CTS format check" in summary.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "error",
    [
        UpstreamFailure("UPSTREAM_CHALLENGE", "safe", 403),
        UpstreamFailure("UPSTREAM_TIMEOUT", "safe"),
        TimeoutError(),
        UpstreamFailure("UPSTREAM_HTTP_ERROR", "safe", 503),
        UpstreamFailure("UPSTREAM_CONNECTION_ERROR", "safe"),
        UpstreamFailure("UPSTREAM_CTS_ERROR", "safe"),
        UpstreamFailure("UPSTREAM_RESPONSE_TOO_LARGE", "safe"),
    ],
)
def test_inconclusive_only_run_exits_zero_and_is_not_reported_as_ok(
    monkeypatch, tmp_path, error
):
    calls = []

    async def get(url):
        calls.append(url)
        raise error

    monkeypatch.setattr(monitor.server, "_get", get)
    report = tmp_path / "report.json"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary.md"))
    monkeypatch.setattr(sys, "argv", ["check_cts_upstream.py", "--report", str(report)])
    assert monitor.main() == 0
    saved = json.loads(report.read_text(encoding="utf-8"))
    assert saved["outcome"] == "inconclusive"
    assert saved["inconclusive"] == 7
    assert saved["failed"] == 0
    assert len(calls) == 7
    assert "INCONCLUSIVE" in (tmp_path / "summary.md").read_text(encoding="utf-8")


def test_drift_still_fails_when_another_endpoint_is_inconclusive(monkeypatch, tmp_path):
    mock_sources(
        monkeypatch,
        "<GetPassage/>",
        {SOURCES[1]["url"]: UpstreamFailure("UPSTREAM_CHALLENGE", "safe", 403)},
    )
    report = tmp_path / "report.json"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary.md"))
    monkeypatch.setattr(sys, "argv", ["check_cts_upstream.py", "--report", str(report)])
    assert monitor.main() == 1
    saved = json.loads(report.read_text(encoding="utf-8"))
    assert saved["failed"] == saved["inconclusive"] == 1
    assert saved["outcome"] == "failed"


@pytest.mark.parametrize(
    "source", MANIFEST["probes"], ids=lambda source: source["operation"]
)
def test_new_probes_reject_known_malformed_response(monkeypatch, source):
    malformed = (FIXTURES / "navigation-malformed.html").read_text(encoding="utf-8")
    mock_sources(monkeypatch, overrides={source["url"]: malformed})
    results = asyncio.run(monitor.check_sources(MANIFEST))
    result = next(
        result for result in results if result["operation"] == source["operation"]
    )
    assert result["outcome"] == "failed"
    assert result["error"] == "INVALID_PAYLOAD"
