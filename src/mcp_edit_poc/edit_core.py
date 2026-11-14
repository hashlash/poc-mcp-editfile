"""Core edit computation: search/replace with validation (LSP pluggable later).

The POC's "additional logic" layer. Deterministic, no LLM involvement: given a
file's content and a replacement request, compute the new content and a unified
diff, or explain why the edit is invalid.
"""

from __future__ import annotations

import difflib
import hashlib
from dataclasses import dataclass


class EditError(Exception):
    """Raised when an edit cannot be computed (surfaced to the model via ToolError)."""


@dataclass(frozen=True)
class EditResult:
    path: str
    old_string: str
    new_string: str
    before: str
    after: str

    @property
    def patch(self) -> str:
        return make_unified_diff(self.path, self.before, self.after)

    @property
    def applied(self) -> bool:
        return self.before != self.after


def require_replacement(old_string: str, new_string: str) -> None:
    if old_string == new_string:
        raise EditError("old_string and new_string are identical; nothing to apply.")
    if old_string == "":
        raise EditError("old_string must not be empty. Use write for creating/overwriting files.")


def apply_replacement(content: str, old_string: str, new_string: str, *, replace_all: bool) -> str:
    """Replace old_string with new_string; raise EditError if not exactly one match (or >1 without replace_all)."""
    count = content.count(old_string)
    if count == 0:
        raise EditError(
            "old_string not found in file. It must match exactly, including whitespace and indentation."
        )
    if count > 1 and not replace_all:
        raise EditError(
            f"found {count} matches for old_string, expected exactly one. "
            "Add more surrounding context to make it unique, or set replace_all=true."
        )
    return (
        content.replace(old_string, new_string)
        if replace_all
        else content.replace(old_string, new_string, 1)
    )


def compute_edit(
    path: str, content: str, old_string: str, new_string: str, *, replace_all: bool
) -> EditResult:
    require_replacement(old_string, new_string)
    after = apply_replacement(content, old_string, new_string, replace_all=replace_all)
    return EditResult(
        path=path, old_string=old_string, new_string=new_string, before=content, after=after
    )


def make_unified_diff(path: str, before: str, after: str) -> str:
    """Git-style unified diff (the format coding agents apply reliably).

    Uses lineterm="" so each diff line ends with exactly one newline; content lines
    carry their own line endings from splitlines(). Matches git's output shape
    closely enough for agents to apply it with their native tools.
    """
    lines = difflib.unified_diff(
        before.splitlines(),
        after.splitlines(),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        lineterm="",
    )
    return "\n".join(lines)


def sha256_hex(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
