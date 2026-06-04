---
title: Documentation
description: Guides and architecture notes for the Perseus MCP server.
permalink: /
---

<section class="hero" markdown="1">

# Perseus MCP Documentation

Perseus MCP is a local FastMCP server that gives MCP-capable clients structured tools for Greek text research against Perseus CTS and Scaife search.

</section>

<section class="doc-grid" markdown="1">

<a class="doc-card" href="{{ '/enduser/' | relative_url }}">
  <h2>End-User Guide</h2>
  <p>Install the server, connect it to an MCP client, discover URNs, retrieve passages, and troubleshoot common setup issues.</p>
</a>

<a class="doc-card" href="{{ '/architecture/' | relative_url }}">
  <h2>Architecture</h2>
  <p>Understand the FastMCP host, upstream services, request helpers, tool behavior, error model, and extension points.</p>
</a>

</section>

## Quick Start

Install dependencies from the project root:

```bash
uv sync
```

Run the server:

```bash
uv run server.py
```

Configure an MCP-capable client with the same local command:

```bash
uv --directory /full/path/to/Perseus-mcp run server.py
```
