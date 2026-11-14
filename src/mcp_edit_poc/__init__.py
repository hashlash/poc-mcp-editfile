"""POC — MCP-driven edits that render as native diffs in coding agents.

Three mechanisms under comparison:
  (a) diff-return   — MCP tool computes the edit, returns a unified diff; the agent
                      applies it with its native edit tool (native diff in the UI).
  (b) side-channel  — MCP tool prompts the CURRENT OpenCode session to apply the diff
                      (via OpenCode's local server API).
  (c) hook rewrite  — model calls the native edit tool; an OpenCode plugin hook
                      rewrites the tool input to the deterministic computed values.

Status: work in progress. See REPORT.md for comparison results when runs complete.

Layout:
  src/mcp_edit_poc/    the MCP server (mechanisms a+b) + edit computation core
  plugin/               the OpenCode plugin (mechanism c)
  tests/                deterministic core tests
  runs/                 comparison fixtures + per-run results
  compare.py            scorer: parses run results into a comparison table
"""
