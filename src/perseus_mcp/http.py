"""Fetch and validate bounded upstream responses using a shared asynchronous HTTP client."""

from __future__ import annotations

import asyncio
import math
import os
import warnings
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx

from . import upstream as _upstream

__all__ = [
    "_HTTP_CLIENT",
    "_HTTP_CLIENT_LOOP",
    "UpstreamRateLimitWarning",
    "_body_timeout_seconds",
    "_close_http_client",
    "_get",
    "_max_response_bytes",
    "_shared_client",
    "_stream_upstream",
    "aclose_http_client",
]


_HTTP_CLIENT: httpx.AsyncClient | None = None


_HTTP_CLIENT_LOOP: asyncio.AbstractEventLoop | None = None


class UpstreamRateLimitWarning(UserWarning):
    """Warn that Perseus or Scaife rejected a request because of rate limiting."""


async def _close_http_client(
    client: httpx.AsyncClient,
    client_loop: asyncio.AbstractEventLoop | None,
) -> None:
    """Close a client without failing when its owning loop has already ended."""
    if client.is_closed:
        return
    try:
        await client.aclose()
    except RuntimeError as exc:
        if (
            str(exc) != "Event loop is closed"
            or client_loop is None
            or not client_loop.is_closed()
        ):
            raise


async def _shared_client() -> httpx.AsyncClient:
    """Return a process-wide httpx.AsyncClient, reused across tool calls.

    Opening a brand new client (and therefore a new TCP/TLS connection) for
    every tool call is wasteful for a long-lived MCP server, especially for
    passage-processing workflows that make many sequential requests to the
    same Perseus/Scaife hosts. Reusing one client lets httpx pool and reuse
    connections instead.

    The client is recreated if the running event loop has changed (or the
    previous client was closed), since an httpx.AsyncClient's underlying
    transport is bound to the loop it was created on. In normal operation
    there is exactly one loop for the lifetime of the process; this check
    mainly matters for test suites that call ``asyncio.run()`` per test.
    """
    global _HTTP_CLIENT, _HTTP_CLIENT_LOOP
    running_loop = asyncio.get_running_loop()
    if (
        _HTTP_CLIENT is None
        or _HTTP_CLIENT.is_closed
        or _HTTP_CLIENT_LOOP is not running_loop
    ):
        if _HTTP_CLIENT is not None and not _HTTP_CLIENT.is_closed:
            await _close_http_client(_HTTP_CLIENT, _HTTP_CLIENT_LOOP)
        _HTTP_CLIENT = httpx.AsyncClient(follow_redirects=True)
        _HTTP_CLIENT_LOOP = running_loop
    return _HTTP_CLIENT


async def aclose_http_client() -> None:
    """Close the shared HTTP client, if one has been created.

    Not required for normal stdio server operation (the OS reclaims
    connections on process exit), but useful for tests and any embedding
    that wants a clean shutdown.
    """
    global _HTTP_CLIENT, _HTTP_CLIENT_LOOP
    client = _HTTP_CLIENT
    client_loop = _HTTP_CLIENT_LOOP
    try:
        if client is not None:
            await _close_http_client(client, client_loop)
    finally:
        _HTTP_CLIENT = None
        _HTTP_CLIENT_LOOP = None


def _max_response_bytes() -> int:
    """Read the positive response-size limit in decoded bytes, raising ValueError if invalid."""
    value = os.environ.get("PERSEUS_MCP_MAX_RESPONSE_BYTES", "16777216")
    try:
        limit = int(value)
    except ValueError:
        raise ValueError(
            "PERSEUS_MCP_MAX_RESPONSE_BYTES must be a positive integer"
        ) from None
    if limit <= 0:
        raise ValueError("PERSEUS_MCP_MAX_RESPONSE_BYTES must be a positive integer")
    return limit


def _body_timeout_seconds() -> float:
    """Read the positive finite total body deadline in seconds, defaulting to 60."""
    value = os.environ.get("PERSEUS_MCP_BODY_TIMEOUT_SECONDS", "60")
    try:
        timeout = float(value)
    except ValueError:
        raise ValueError(
            "PERSEUS_MCP_BODY_TIMEOUT_SECONDS must be a positive finite number"
        ) from None
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError(
            "PERSEUS_MCP_BODY_TIMEOUT_SECONDS must be a positive finite number"
        )
    return timeout


@asynccontextmanager
async def _stream_upstream(client, url, params, timeout):
    # HTTPX's automatic redirect handling buffers redirect bodies. Follow its
    # generated next_request explicitly so those bodies are closed unread too.
    """Yield the final streaming response and close all bodies, including unread redirects."""
    request = client.build_request("GET", url, params=params, timeout=timeout)
    for _ in range(client.max_redirects + 1):
        response = await client.send(request, stream=True, follow_redirects=False)
        try:
            if response.next_request is None:
                yield response
                return
            request = response.next_request
        finally:
            await response.aclose()
    raise httpx.TooManyRedirects("Upstream redirect limit exceeded", request=request)


async def _get(
    url: str,
    params: dict[str, Any] | None = None,
    timeout: float = 20.0,
    *,
    validator: Callable[[str], None] = _upstream.validate_text,
) -> str:
    """Fetch bounded response text, validate it, and map transport failures.

    Args:
        url: Upstream endpoint URL.
        params: Optional query parameters.
        timeout: HTTPX per-operation timeout in seconds.
        validator: Callback that rejects unexpected response text.

    Returns:
        Decoded text that passed the supplied validator.

    Raises:
        UpstreamFailure: On access challenges, HTTP/transport failures, size or
            deadline limits, or invalid payloads. No automatic retry is made.
        ValueError: If a response-size or body-deadline setting is invalid.

    The total body deadline and decoded-byte limit are configured separately
    through ``PERSEUS_MCP_BODY_TIMEOUT_SECONDS`` and
    ``PERSEUS_MCP_MAX_RESPONSE_BYTES``.
    """
    limit = _max_response_bytes()
    body_timeout = _body_timeout_seconds()
    client = await _shared_client()
    status = None
    retry_after_seconds = None
    try:
        async with _stream_upstream(client, url, params, timeout) as response:
            status = response.status_code
            retry_after_seconds = _upstream.parse_retry_after(
                response.headers.get("Retry-After")
            )
            length = response.headers.get("Content-Length", "")
            if length.isdigit() and int(length) > limit:
                raise _upstream.UpstreamFailure(
                    "UPSTREAM_RESPONSE_TOO_LARGE",
                    "The upstream response exceeds the configured size limit.",
                    status,
                )
            body = bytearray()
            # A single deadline spans the entire body, rather than restarting
            # whenever another chunk arrives (HTTPX's per-read timeout).
            async with asyncio.timeout(body_timeout):
                async for chunk in response.aiter_bytes():
                    # Count decoded bytes too: compressed and chunked responses
                    # must not bypass the limit with a misleading Content-Length.
                    if len(chunk) > limit - len(body):
                        raise _upstream.UpstreamFailure(
                            "UPSTREAM_RESPONSE_TOO_LARGE",
                            "The upstream response exceeds the configured size limit.",
                            status,
                        )
                    body.extend(chunk)
            text = body.decode(response.encoding or "utf-8", errors="replace")
            _upstream.reject_challenge(text, status)
            if status == 429:
                retry_guidance = (
                    f" Retry after {retry_after_seconds} seconds."
                    if retry_after_seconds is not None
                    else " Wait before retrying and reduce request concurrency."
                )
                warnings.warn(
                    "Upstream service rate limit (HTTP 429)."
                    f"{retry_guidance} The request was not retried automatically.",
                    UpstreamRateLimitWarning,
                    stacklevel=2,
                )
            response.raise_for_status()
            try:
                validator(text)
            except _upstream.UpstreamFailure as exc:
                exc.status = status
                raise
            return text
    except httpx.HTTPStatusError as exc:
        raise _upstream.UpstreamFailure(
            "UPSTREAM_HTTP_ERROR",
            "The upstream service returned an HTTP error.",
            exc.response.status_code,
            retry_after_seconds=retry_after_seconds,
        ) from None
    except (httpx.TimeoutException, TimeoutError):
        raise _upstream.UpstreamFailure(
            "UPSTREAM_TIMEOUT",
            "The upstream request timed out.",
            status,
        ) from None
    except httpx.NetworkError:
        raise _upstream.UpstreamFailure(
            "UPSTREAM_CONNECTION_ERROR",
            "The upstream connection failed.",
            status,
        ) from None
    except httpx.RequestError:
        raise _upstream.UpstreamFailure(
            "UPSTREAM_TRANSPORT_ERROR",
            "The upstream request could not be completed.",
            status,
        ) from None
