"""Reject malformed or excessive client input before any cache or upstream access."""

import asyncio
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from perseus_mcp import server
from perseus_mcp.validation import (
    MAX_QUERY_LENGTH,
    MAX_URN_LENGTH,
    validate_text,
    validate_urn,
)

WORK = "urn:cts:greekLit:tlg0012.tlg001.perseus-grc1"


def test_captured_perseus_catalogue_and_passage_urns_remain_accepted():
    """Check real inventory/citation diversity rather than only hand-written examples."""
    urns = set()
    for path in (Path(__file__).parent / "fixtures/cts").glob("*.xml"):
        for element in server._safe_xml_fromstring(path.read_bytes()).iter():
            urns.update(
                value
                for value in element.attrib.values()
                if value.startswith("urn:cts:")
            )
            if element.text and element.text.strip().startswith("urn:cts:"):
                urns.add(element.text.strip())
    assert urns
    for urn in urns:
        assert validate_urn(urn) == urn


@pytest.mark.parametrize(
    "urn",
    [
        "urn:cts:greekLit:tlg0012",
        "urn:cts:greekLit:tlg0012:",
        "urn:cts:greekLit:tlg0012.tlg001",
        f"{WORK}:",
        f"{WORK}.copy1:1.1",
        f"{WORK}:1",
        f"{WORK}:1.1-2.10",
        f"{WORK}:preface.pr",
        f"{WORK}:1.1@Μῆνιν",
        f"{WORK}:1.1@Μη\u0302νιν[2]",
        f"{WORK}:1.1@word[01]",
        f"{WORK}:1.1@word-other",
        f"{WORK}:1.1@word[2]-1.2@other[3]",
        f"{WORK}:1.1@a-b-1.2@c-d",
        "urn:cts:anotherNamespace:author.work:chapter_A.section2",
    ],
)
def test_supported_cts_forms_remain_unchanged(urn):
    assert validate_urn(urn) == urn


@pytest.mark.parametrize(
    "urn",
    [
        "",
        " ",
        "https://example.com/",
        "not-a-urn",
        "urn:cite:greekLit:tlg0012",
        "urn:cts:greekLit",
        "URN:CTS:greekLit:tlg0012",
        "urn:cts::tlg0012",
        "urn:cts:greekLit:",
        "urn:cts:greekLit:.tlg0012",
        "urn:cts:greekLit:tlg0012..tlg001",
        f"{WORK}.",
        f"{WORK}.copy.extra:1",
        "urn:cts:greekLit:tlg0012:1",
        f"{WORK}:1:2",
        f"{WORK}:1..2",
        f"{WORK}:1.",
        f"{WORK}:1-",
        f"{WORK}:1--2",
        f"{WORK}:1@",
        f"{WORK}:1@@word",
        f"{WORK}:1@word[0]",
        f"{WORK}:1@word[-1]",
        f"{WORK}:1@word[2",
        f"{WORK}:1@word]",
        f"{WORK}:1@word[2][3]",
        f"{WORK}:1@word[2]tail",
        f"{WORK}:1#fragment",
        f"{WORK}:1?query=1",
        f"{WORK}:1%23fragment",
        f"{WORK}/../other:1",
        f"{WORK}:1\\other",
        f"{WORK}:1&extra=1",
        f" {WORK}",
        f"{WORK}:1 oops",
        f"{WORK}:1\n",
        f"{WORK}:1\x00",
        f"{WORK}:1\u200b",
        f"{WORK}:1\ud800",
    ],
)
def test_malformed_cts_forms_are_rejected(urn):
    with pytest.raises(ValueError):
        validate_urn(urn)


def test_raw_lengths_are_checked_before_trimming_or_normalizing(monkeypatch):
    prefix = "urn:cts:example:"
    urn = prefix + "a" * (MAX_URN_LENGTH - len(prefix))
    assert validate_urn(urn) == urn
    with pytest.raises(ValueError, match="urn must not exceed 1024 characters"):
        validate_urn(urn + "a")
    assert server._normalize_query_for_search("a" * MAX_QUERY_LENGTH, "latin") == (
        "a" * MAX_QUERY_LENGTH
    )

    def normalization_must_not_run(*args, **kwargs):
        """Detect expensive Greek processing before the size check."""
        pytest.fail("Oversized input reached Greek normalization")

    monkeypatch.setattr(server, "_normalize_greek_query", normalization_must_not_run)
    for query in ("a" * (MAX_QUERY_LENGTH + 1), " " * (MAX_QUERY_LENGTH + 1)):
        with pytest.raises(ValueError, match="query must not exceed 2048 characters"):
            server._normalize_query_for_search(query)


def test_normalized_query_expansion_is_also_bounded():
    # NFC decomposes U+0344 into two combining marks, potentially doubling length.
    with pytest.raises(ValueError, match="query must not exceed 2048 characters"):
        server._normalize_query_for_search("\u0344" * MAX_QUERY_LENGTH, "greek")


@pytest.fixture
def no_io(monkeypatch):
    """Make any cache lookup/write or outgoing request an immediate test failure."""

    async def forbidden(*args, **kwargs):
        """Record an invalid input escaping the boundary checks."""
        pytest.fail("Invalid input reached the cache or network")

    monkeypatch.setattr(server, "_get", forbidden)
    monkeypatch.setattr(server, "_cached_text", forbidden)


URN_TOOLS = [
    (name, "urn", {})
    for name in (
        "get_passage",
        "get_passage_plus",
        "get_passage_plaintext",
        "get_valid_references",
        "get_valid_references_json",
        "count_valid_references",
        "get_label",
        "get_first_urn",
        "get_prev_next_urn",
        "get_scaife_library_metadata",
        "get_scaife_passage_json",
        "get_scaife_passage_text",
    )
] + [
    ("search_within_text", "text_urn", {"query": "arma"}),
    ("get_passage_highlights", "passage_urn", {"query": "arma"}),
    ("search_perseus", "text_group", {"query": "arma", "author": "Homer"}),
    ("search_perseus", "work", {"query": "arma", "author": "Homer"}),
]


@pytest.mark.parametrize(("tool", "argument", "other"), URN_TOOLS)
@pytest.mark.parametrize("bad", ["not-a-urn", WORK + "#fragment", "x" * 1025])
def test_every_urn_tool_rejects_invalid_input_before_io(
    no_io, tool, argument, other, bad
):
    with pytest.raises(ValueError):
        asyncio.run(getattr(server, tool)(**other, **{argument: bad}))


TEXT_TOOLS = [
    ("search_perseus", "query", {}),
    ("search_within_text", "query", {"text_urn": WORK}),
    ("get_passage_highlights", "query", {"passage_urn": f"{WORK}:1.1"}),
    ("list_text_groups", "query", {}),
    ("find_author_names", "query", {}),
    ("get_author_resources", "author", {}),
    ("get_work_resources", "urn_or_title", {}),
    ("search_perseus", "author", {"query": "arma"}),
]


@pytest.mark.parametrize(("tool", "argument", "other"), TEXT_TOOLS)
@pytest.mark.parametrize("bad", ["x" * 2049, " " * 2049, "text\x00"])
def test_all_query_and_selector_inputs_are_bounded_before_io(
    no_io, tool, argument, other, bad
):
    with pytest.raises(ValueError):
        asyncio.run(getattr(server, tool)(**other, **{argument: bad}))


@pytest.mark.parametrize(
    ("tool", "argument", "other"),
    [
        ("get_author_resources", "author", {}),
        ("get_work_resources", "urn_or_title", {}),
        ("search_perseus", "author", {"query": "arma"}),
    ],
)
def test_mixed_selectors_do_not_treat_malformed_urns_as_names(
    no_io, tool, argument, other
):
    with pytest.raises(ValueError, match="CTS URN"):
        asyncio.run(getattr(server, tool)(**other, **{argument: "urn:cts:bad"}))


@pytest.mark.parametrize("helper", ["_cts_request", "_get_valid_references_cached"])
def test_cts_helpers_validate_before_transport_or_cache(no_io, helper):
    function = getattr(server, helper)
    args = ("GetPassage",) if helper == "_cts_request" else ()
    with pytest.raises(ValueError, match="CTS URN"):
        asyncio.run(function(*args, urn="bad"))


def test_missing_passage_urn_cannot_bypass_optional_internal_parameter(no_io):
    with pytest.raises(ValueError, match="urn is required"):
        asyncio.run(server.get_passage(None))


def test_mixed_urn_selector_is_bounded_before_trimming(no_io):
    urn = "urn:cts:namespace:" + "a" * MAX_URN_LENGTH
    with pytest.raises(ValueError, match="author must not exceed 1024 characters"):
        asyncio.run(server.get_author_resources(urn))
    with pytest.raises(ValueError, match="CTS URN"):
        asyncio.run(server.get_work_resources(" " + WORK))


def test_mcp_client_receives_actionable_validation_errors(no_io):
    async def exercise():
        """Exercise the actual registered MCP tools rather than only Python helpers."""
        async with Client(server.mcp) as client:
            with pytest.raises(ToolError, match="CTS URN"):
                await client.call_tool("get_passage", {"urn": "bad"})
            with pytest.raises(ToolError, match="2048 characters"):
                await client.call_tool("search_perseus", {"query": "a" * 2049})

    asyncio.run(exercise())


@pytest.mark.parametrize("value", [None, 3, []])
def test_direct_python_calls_require_strings(value):
    with pytest.raises(TypeError, match="must be a string"):
        validate_text(value)
