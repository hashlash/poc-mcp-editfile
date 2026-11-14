"""Deterministic tests for the edit computation core."""

from mcp_edit_poc.edit_core import EditError, compute_edit, make_unified_diff, sha256_hex

CONTENT = "def foo():\n    return 1\n"


def test_basic_replacement():
    result = compute_edit("f.py", CONTENT, "return 1", "return 2", replace_all=False)
    assert result.after == "def foo():\n    return 2\n"
    assert result.applied is True


def test_missing_old_string():
    try:
        compute_edit("f.py", CONTENT, "return 99", "return 2", replace_all=False)
        raise AssertionError("expected EditError")
    except EditError as e:
        assert "not found" in str(e)


def test_multiple_matches_require_replace_all():
    try:
        compute_edit("f.py", "a\na\n", "a", "b", replace_all=False)
        raise AssertionError("expected EditError")
    except EditError as e:
        assert "matches" in str(e)


def test_replace_all():
    result = compute_edit("f.py", "a\na\n", "a", "b", replace_all=True)
    assert result.after == "b\nb\n"


def test_identical_strings_rejected():
    try:
        compute_edit("f.py", CONTENT, "foo", "foo", replace_all=False)
        raise AssertionError("expected EditError")
    except EditError as e:
        assert "identical" in str(e)


def test_unified_diff_shape():
    result = compute_edit("f.py", CONTENT, "return 1", "return 2", replace_all=False)
    patch = make_unified_diff("f.py", result.before, result.after)
    assert "--- a/f.py" in patch
    assert "+++ b/f.py" in patch
    assert "-    return 1" in patch
    assert "+    return 2" in patch


def test_sha256():
    assert sha256_hex("") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
