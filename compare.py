"""Scorer: parse per-run results into a comparison table (run via `python compare.py`).

Each run writes runs/<mechanism>/run-<n>/result.json with this schema:

{
  "mechanism": "a-diff-return",
  "run": 1,
  "tool": "edit_diff",
  "llm_turns": 2,            // assistant turns the agent took (incl. apply + verify)
  "tokens": {"input": 1234, "output": 567, "cache_read": 0, "cache_write": 0},
  "tool_error": false,        // did the MCP tool return an error?
  "verify_pass": true,        // did verify_edit (or content check) pass?
  "native_diff": true,        // did the agent's native edit tool run with file changes?
  "notes": "..."
}

Run: for each mechanism, N=5 runs on a fresh copy of the fixture. The agent (you,
the human in the loop, or a scripted OpenCode session) performs the edit task using
that mechanism's tool; after the attempt, fill result.json.

Usage:
  python compare.py            # table + recommendation
  python compare.py --json     # machine-readable
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RUNS_DIR = Path(__file__).parent / "runs"
MECHANISMS = ["a-diff-return", "a-write-mode", "b-side-channel", "c-hook-rewrite"]
N = 5


def load_results() -> list[dict]:
    results = []
    for mechanism in MECHANISMS:
        for n in range(1, N + 1):
            path = RUNS_DIR / mechanism / f"run-{n}" / "result.json"
            if not path.exists():
                continue
            data = json.loads(path.read_text())
            data.setdefault("mechanism", mechanism)
            data.setdefault("run", n)
            results.append(data)
    return results


def summarize(results: list[dict]) -> dict:
    per: dict[str, dict] = {}
    for r in results:
        m = per.setdefault(
            r["mechanism"],
            {
                "runs": 0,
                "turns": [],
                "tokens": [],
                "tool_errors": 0,
                "verify_fails": 0,
                "native_diffs": 0,
            },
        )
        m["runs"] += 1
        m["turns"].append(r.get("llm_turns", 0))
        m["tokens"].append(sum((r.get("tokens") or {}).values()))
        m["tool_errors"] += int(bool(r.get("tool_error")))
        m["verify_fails"] += int(not r.get("verify_pass", False))
        m["native_diffs"] += int(bool(r.get("native_diff")))
    for m in per.values():
        n = max(m["runs"], 1)
        m["avg_turns"] = round(sum(m["turns"]) / n, 2)
        m["avg_tokens"] = round(sum(m["tokens"]) / n, 1)
        m["tool_error_rate"] = round(m["tool_errors"] / n, 2)
        m["verify_fail_rate"] = round(m["verify_fails"] / n, 2)
        m["native_diff_rate"] = round(m["native_diffs"] / n, 2)
    return per


def render_table(per: dict) -> str:
    header = f"{'mechanism':<16} {'runs':>4} {'avg turns':>9} {'avg tokens':>10} {'tool err':>8} {'verify fail':>11} {'native diff':>11}"
    lines = [header, "-" * len(header)]
    for mechanism in MECHANISMS:
        if mechanism not in per:
            lines.append(f"{mechanism:<16} {'—— no runs yet ——':>40}")
            continue
        m = per[mechanism]
        lines.append(
            f"{mechanism:<16} {m['runs']:>4} {m['avg_turns']:>9} {m['avg_tokens']:>10} "
            f"{m['tool_error_rate']:>8} {m['verify_fail_rate']:>11} {m['native_diff_rate']:>11}"
        )
    return "\n".join(lines)


def recommend(per: dict) -> str:
    if not per:
        return "No runs recorded yet."
    complete = {m: v for m, v in per.items() if v["runs"] >= N}
    if not complete:
        return f"Recommendation pending: {', '.join(m for m in MECHANISMS if m not in complete)} incomplete (need {N} runs each)."
    best = min(
        complete,
        key=lambda m: (
            complete[m]["verify_fail_rate"],
            complete[m]["tool_error_rate"],
            complete[m]["avg_tokens"],
        ),
    )
    return (
        f"Recommendation: {best} — lowest verify-fail rate, then tool-error rate, then token cost "
        f"(verify fail {complete[best]['verify_fail_rate']}, tool err {complete[best]['tool_error_rate']}, "
        f"avg tokens {complete[best]['avg_tokens']})."
    )


def main() -> int:
    results = load_results()
    per = summarize(results)
    if "--json" in sys.argv:
        print(json.dumps(per, indent=2))
    else:
        print(render_table(per))
        print()
        print(recommend(per))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
