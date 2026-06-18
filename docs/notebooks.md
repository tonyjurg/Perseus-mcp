---
title: Example Notebooks
description: Notebook examples for direct CTS access, MCP client use, Greek and Latin workflows, and optional LLM tool calling.
permalink: /notebooks/
---

# Example Notebooks

The `examples/` directory contains Jupyter notebooks that demonstrate the
Perseus MCP workflow from direct endpoint exploration through full MCP tool
calling. Each notebook can be opened directly on GitHub or viewed through
nbviewer for a cleaner rendered notebook view.

## 00 Install and Run Perseus MCP

Explains the supported installation and launch options: PyPI with pip, isolated
uv tools, repository-local development, MCP client configuration, verification,
upgrades, uninstalling, and common setup failures.

<p class="link-actions">
  <a href="https://github.com/tonyjurg/Perseus-mcp/blob/main/examples/00_install_and_run_perseus_mcp.ipynb">GitHub</a>
  <a href="https://nbviewer.org/github/tonyjurg/Perseus-mcp/blob/main/examples/00_install_and_run_perseus_mcp.ipynb">nbviewer</a>
</p>

## 01 Basic CTS Workflow

A minimal introduction to direct CTS requests. This notebook is useful for
understanding the upstream CTS response shape before using the MCP tools.

<p class="link-actions">
  <a href="https://github.com/tonyjurg/Perseus-mcp/blob/main/examples/01_basic_cts_workflow.ipynb">GitHub</a>
  <a href="https://nbviewer.org/github/tonyjurg/Perseus-mcp/blob/main/examples/01_basic_cts_workflow.ipynb">nbviewer</a>
</p>

## 02 Search and Navigation

Shows direct Scaife JSON search and CTS navigation using valid references. Use
this notebook to see how search results and passage navigation relate.

<p class="link-actions">
  <a href="https://github.com/tonyjurg/Perseus-mcp/blob/main/examples/02_search_and_navigation.ipynb">GitHub</a>
  <a href="https://nbviewer.org/github/tonyjurg/Perseus-mcp/blob/main/examples/02_search_and_navigation.ipynb">nbviewer</a>
</p>

## 03 MCP Connection: Homer Iliad

Demonstrates an in-process FastMCP client connection, Homer resource discovery,
and Greek passage analysis for the *Iliad*.

<p class="link-actions">
  <a href="https://github.com/tonyjurg/Perseus-mcp/blob/main/examples/03_mcp_connection_homer_iliad.ipynb">GitHub</a>
  <a href="https://nbviewer.org/github/tonyjurg/Perseus-mcp/blob/main/examples/03_mcp_connection_homer_iliad.ipynb">nbviewer</a>
</p>

## 04 MCP Greek Search and Navigation

Explores MCP Greek search with Unicode Greek and Beta Code input, valid
references, and passage navigation through the exposed MCP tool surface.

<p class="link-actions">
  <a href="https://github.com/tonyjurg/Perseus-mcp/blob/main/examples/04_mcp_greek_search_and_navigation.ipynb">GitHub</a>
  <a href="https://nbviewer.org/github/tonyjurg/Perseus-mcp/blob/main/examples/04_mcp_greek_search_and_navigation.ipynb">nbviewer</a>
</p>

## 05 MCP All Tools

Catalogs the full MCP tool set with descriptions and input schemas. This is a
good reference notebook when learning what the server exposes to clients.

<p class="link-actions">
  <a href="https://github.com/tonyjurg/Perseus-mcp/blob/main/examples/05_mcp_all_tools.ipynb">GitHub</a>
  <a href="https://nbviewer.org/github/tonyjurg/Perseus-mcp/blob/main/examples/05_mcp_all_tools.ipynb">nbviewer</a>
</p>

## 06 OpenRouter LLM MCP Interaction

Shows an optional OpenRouter LLM tool-calling loop over the local MCP tools,
using an OpenRouter API key supplied outside the repository.

<p class="link-actions">
  <a href="https://github.com/tonyjurg/Perseus-mcp/blob/main/examples/06_openrouter_llm_mcp_interaction.ipynb">GitHub</a>
  <a href="https://nbviewer.org/github/tonyjurg/Perseus-mcp/blob/main/examples/06_openrouter_llm_mcp_interaction.ipynb">nbviewer</a>
</p>

## 07 MCP Advanced Search Options

Demonstrates form search, lemma search, Scaife operator-preserving queries, and
author-scoped search through the `search_perseus` MCP tool.

<p class="link-actions">
  <a href="https://github.com/tonyjurg/Perseus-mcp/blob/main/examples/07_mcp_advanced_search_options.ipynb">GitHub</a>
  <a href="https://nbviewer.org/github/tonyjurg/Perseus-mcp/blob/main/examples/07_mcp_advanced_search_options.ipynb">nbviewer</a>
</p>

## 08 MCP Cache and Search Tools

Demonstrates the advanced cache controls, paged reference helpers,
server-scoped search, reader search, passage highlights, and Scaife
metadata/text retrieval tools with runnable assertions.

<p class="link-actions">
  <a href="https://github.com/tonyjurg/Perseus-mcp/blob/main/examples/08_mcp_cache_and_search_tools.ipynb">GitHub</a>
  <a href="https://nbviewer.org/github/tonyjurg/Perseus-mcp/blob/main/examples/08_mcp_cache_and_search_tools.ipynb">nbviewer</a>
</p>

## 09 OpenRouter Philo Politeia Analysis

Uses scoped Perseus MCP searches to collect cited evidence for `πολιτεία` in
Philo of Alexandria, then asks an OpenRouter-hosted LLM to synthesize the
evidence with URN citations and explicit limits on unsupported claims.

<p class="link-actions">
  <a href="https://github.com/tonyjurg/Perseus-mcp/blob/main/examples/09_openrouter_philo_politeia_analysis.ipynb">GitHub</a>
  <a href="https://nbviewer.org/github/tonyjurg/Perseus-mcp/blob/main/examples/09_openrouter_philo_politeia_analysis.ipynb">nbviewer</a>
</p>

## 10 MCP Latin Augustine Workflow

Uses `language="latin"` for CTS inventory discovery, selects Augustine's
advertised *Epistulae* edition, retrieves valid references and Latin plaintext,
and performs a small reproducible token analysis.

<p class="link-actions">
  <a href="https://github.com/tonyjurg/Perseus-mcp/blob/main/examples/10_mcp_latin_augustine_workflow.ipynb">GitHub</a>
  <a href="https://nbviewer.org/github/tonyjurg/Perseus-mcp/blob/main/examples/10_mcp_latin_augustine_workflow.ipynb">nbviewer</a>
</p>
