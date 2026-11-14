# mcp-edit-poc

**POC: MCP-driven edits that render as native diffs in coding agents.**

## The problem

MCP tools that modify files directly (with extra logic — LSP calls, codemods, ...)
write the file themselves. The coding agent's native diff UI never sees the change,
so users lose the review/keep/undo flow they rely on.

## The mechanisms under comparison

| # | mechanism | how it gets a native diff | deterministic? | agent-agnostic? |
|---|-----------|---------------------------|----------------|-----------------|
| a | **diff-return** | MCP tool computes the edit, returns a unified diff; the agent applies it with its native edit tool | diff is deterministic; apply is a model action | yes |
| b | **side-channel** | MCP tool prompts the *current* OpenCode session (via its local server API) to apply the diff | no (extra model turn) | OpenCode only |
| c | **hook rewrite** | model calls its native edit tool; a plugin hook rewrites the tool input to the computed values | yes (native pipeline runs the built-in tool) | per-agent hooks |

All three were chosen after verifying the facts: MCP has no server→client tool-call
primitive; no agent hook can synthesize a native edit call, but hooks *can* rewrite
an edit call's arguments; OpenCode's TUI renders a native diff only when a tool call
named `edit`/`write`/`patch` returns `metadata.files` (see `PatchDiff` in
`packages/tui/src/routes/session/index.tsx`).

## Layout

```
src/mcp_edit_poc/    MCP server (mechanisms a+b) + edit_core (diff computation)
plugin/               OpenCode plugin (mechanism c)
tests/                deterministic tests for edit_core
scripts/smoke_client.py  stdio smoke test (no agent needed)
runs/                 comparison fixtures + per-run results
run_manifest.py       run scaffolder (fresh fixture copy per run)
compare.py            scorer: results.json -> comparison table + recommendation
REPORT.md             comparison results (filled after N=5 runs per mechanism)
```

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest          # deterministic core tests
.venv/bin/python scripts/smoke_client.py   # stdio smoke test
```

OpenCode MCP registration lives in `~/.config/opencode/opencode.json`
(`mcp."mcp-edit-poc".command` points at `.venv/bin/python -m mcp_edit_poc.server`).

## Running the comparison

For each mechanism in [a-diff-return, a-write-mode, b-side-channel, c-hook-rewrite]:

1. `python runs/run_manifest.py --prepare <mechanism>` (fresh fixture copy)
2. In a coding agent with the POC server registered, perform the edit task using
   only that mechanism's tool (task: change `return 1` to `return 2` in
   `runs/<mechanism>/run-<n>/fixture.py`).
3. Fill `runs/<mechanism>/run-<n>/result.json` (schema documented in `compare.py`).
4. After N=5 runs: `python compare.py` → table + recommendation; paste into REPORT.md.

## Findings so far

- The MCP server loads over stdio in a real agent and all four tools are callable
  (edit_diff / edit_write_diff / edit_via_opencode / verify_edit).
- ToolError from invalid edits (not-found, ambiguous, identical) surfaces to the
  model as an error result — good enough to drive a retry.
- Mechanism (a) proof-of-loop passes end-to-end: compute diff -> apply with native
  edit tool -> deterministic verify (see runs/a-diff-return/run-1).
- Timed N=5 comparison across all mechanisms: pending (needs a human/scripted
  driver per run; see runs/run_manifest.py).