"""MCP server exposing the POC edit tools.

Mechanisms implemented here:
  (a) diff-return   — edit_diff / edit_write_diff: compute the edit, return a unified
                      diff for the agent's native edit tool to apply.
  (b) side-channel  — edit_via_opencode: compute the edit, then inject a prompt into
                      the CURRENT OpenCode session (via its local server API) so the
                      live session applies the diff with its native edit tool.

Mechanism (c) (hook-based argument rewriting) is not a server feature: it is an
OpenCode plugin configured in the agent — see plugin/ for that experiment.

OpenCode server notes (verified against v2.2.6, the live local API):
  - registration: ~/.local/state/opencode/service.json -> {url, password}
  - GET  /api/session            -> {data: [{id, title, location: {directory}, time}], cursor}
  - GET  /api/session/active     -> {sessionID: {type: "running"}}
  - GET  /api/session/{id}/status, POST /api/session/{id}/prompt  ({"text": ...})
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from .edit_core import EditError, compute_edit, require_replacement, sha256_hex

mcp = MCPServer("mcp-edit-poc")

HTTP_TIMEOUT = 10

_SERVICE_REG = Path.home() / ".local/state/opencode/service.json"
_TABS_FILE = Path.home() / ".local/state/opencode/latest/tui/tabs.json"


def _read_file(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ToolError(f"File not found: {path}")
    except IsADirectoryError:
        raise ToolError(f"Path is a directory, not a file: {path}")
    except UnicodeDecodeError:
        raise ToolError(f"File is not valid UTF-8 text: {path}")


def _diff_payload(path: str, content: str, old_string: str, new_string: str, *, replace_all: bool) -> dict:
    try:
        result = compute_edit(path, content, old_string, new_string, replace_all=replace_all)
    except EditError as e:
        raise ToolError(str(e))
    return {
        "path": path,
        "diff": result.patch,
        "applied": result.applied,
        "note": "Apply this diff with your native edit tool (apply_patch/edit). Do not rewrite the file by hand.",
    }


def _unwrap(value: Any) -> Any:
    """OpenCode v2 wraps list/object payloads in {"data": ...} (often with "cursor" alongside)."""
    if isinstance(value, dict) and isinstance(value.get("data"), (list, dict)):
        return value["data"]
    return value


# ---------------------------------------------------------------------------
# Mechanism (b): OpenCode local-server side channel
# ---------------------------------------------------------------------------


class OpenCodeClient:
    def __init__(self, base_url: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.password = password

    def _request(self, path: str, payload: dict | None = None) -> Any:
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            f"{self.base_url}{path}", data=data, method="POST" if payload is not None else "GET"
        )
        req.add_header("Content-Type", "application/json")
        if self.password:
            token = base64.b64encode(f"opencode:{self.password}".encode()).decode()
            req.add_header("Authorization", f"Basic {token}")
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                return _unwrap(json.load(resp))
        except urllib.error.HTTPError as e:
            raise ToolError(f"OpenCode API {path} failed: {e.code} {e.read()[:200]!r}")
        except urllib.error.URLError as e:
            raise ToolError(f"Cannot reach OpenCode server at {self.base_url}: {e}")

    def _current_session(self) -> str:
        """The TUI's focused tab for this cwd, else the most recently viewed session in this cwd."""
        if _TABS_FILE.exists():
            try:
                tabs = json.loads(_TABS_FILE.read_text())
                entry = tabs.get("cwd", {}).get(str(Path.cwd().resolve()), {})
                ids = [t["sessionID"] for t in entry.get("tabs", []) if t.get("sessionID")]
                if ids:
                    return ids[-1]
            except (json.JSONDecodeError, OSError):
                pass

        sessions = self._request("/api/session") or []
        cwd = str(Path.cwd().resolve())
        in_cwd = [s for s in sessions if (s.get("location") or {}).get("directory") == cwd]
        if in_cwd:
            return max(in_cwd, key=lambda s: (s.get("time") or {}).get("viewed", 0))["id"]
        raise ToolError(
            "Could not determine the current OpenCode session: no TUI tab for this cwd and "
            "no session found for the working directory."
        )

    def prompt_current(self, text: str) -> dict:
        session_id = self._current_session()

        active = self._request("/api/session/active") or {}
        for info in active.values():
            if isinstance(info, dict) and info.get("type") == "running":
                raise ToolError(
                    "The current OpenCode session is mid-turn; refusing to inject (busy-guard). "
                    "Mechanism (b) requires an idle session."
                )

        return self._request(f"/api/session/{session_id}/prompt", {"text": text})


def _load_opencode_client() -> OpenCodeClient:
    if not _SERVICE_REG.exists():
        raise ToolError(
            "OpenCode service registration not found (~/.local/state/opencode/service.json). "
            "Mechanism (b) requires a running OpenCode TUI."
        )
    try:
        reg = json.loads(_SERVICE_REG.read_text())
        return OpenCodeClient(reg["url"], reg.get("password", ""))
    except (json.JSONDecodeError, KeyError, OSError) as e:
        raise ToolError(f"Cannot read OpenCode service registration: {e}")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def edit_diff(path: str, old_string: str, new_string: str, replace_all: bool = False) -> dict:
    """Compute an edit and return it as a unified diff for the agent's native edit tool to apply.

    Call with the exact old text and its replacement, then apply the returned diff with
    your native edit/apply_patch tool.
    """
    content = _read_file(path)
    try:
        require_replacement(old_string, new_string)
    except EditError as e:
        raise ToolError(str(e))
    return _diff_payload(path, content, old_string, new_string, replace_all=replace_all)


@mcp.tool()
def edit_write_diff(path: str, old_string: str, new_string: str, replace_all: bool = False) -> dict:
    """Variant of edit_diff that ALSO writes the file itself (write-mode), for comparison runs.

    Returns the diff plus confirmation the file was written. WARNING: because the file
    is already changed, the agent may skip its native edit tool and the native diff may
    not render. This variant exists to measure exactly that failure rate.
    """
    content = _read_file(path)
    try:
        result = compute_edit(path, content, old_string, new_string, replace_all=replace_all)
    except EditError as e:
        raise ToolError(str(e))
    Path(path).write_text(result.after, encoding="utf-8")
    payload = _diff_payload(path, content, old_string, new_string, replace_all=replace_all)
    payload["written"] = True
    return payload


@mcp.tool()
def edit_via_opencode(path: str, old_string: str, new_string: str, replace_all: bool = False) -> dict:
    """Mechanism (b): compute the edit, then have the CURRENT OpenCode session apply it.

    Injects a prompt into the live session instructing it to apply this exact diff with
    its native edit tool. Only works while OpenCode is running and the session is idle;
    aborts (busy-guard) if a turn is already running. The diff renders natively.
    """
    content = _read_file(path)
    try:
        result = compute_edit(path, content, old_string, new_string, replace_all=replace_all)
    except EditError as e:
        raise ToolError(str(e))
    instruction = (
        "An external tool computed an edit. Apply EXACTLY this diff to the file using your native "
        "edit/apply_patch tool, changing nothing else:\n\n"
        f"File: {path}\n\n{result.patch}"
    )
    client = _load_opencode_client()
    client.prompt_current(instruction)
    return {"path": path, "diff": result.patch, "injected": True}


@mcp.tool()
def verify_edit(path: str, expected_sha256: str | None = None, expected_content: str | None = None) -> dict:
    """Deterministic check that a file now matches the expected post-edit state.

    Provide either expected_sha256 (sha256 of the expected file content) or
    expected_content (exact text). Returns pass/fail with actual values.
    """
    content = _read_file(path)
    actual = sha256_hex(content)
    if expected_sha256 is not None:
        ok = actual == expected_sha256.strip().lower()
        return {"path": path, "pass": ok, "expected_sha256": expected_sha256, "actual_sha256": actual}
    if expected_content is not None:
        ok = content == expected_content
        return {"path": path, "pass": ok, "expected_sha256": sha256_hex(expected_content), "actual_sha256": actual}
    return {"path": path, "sha256": actual}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()