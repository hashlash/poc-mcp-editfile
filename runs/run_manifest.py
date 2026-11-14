"""Run manifest for the POC comparison.

A "run" = one agent attempt to perform the same edit task via one mechanism.
5 runs per mechanism (N=5), on a fresh copy of the fixture each time.

Each run writes runs/<mechanism>/run-<n>/result.json (see compare.py for schema).
"""

import json
import shutil
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixture.py"
EDIT = {"old_string": "return 1", "new_string": "return 2", "replace_all": False}

MECHANISMS = ["a-diff-return", "a-write-mode", "b-side-channel", "c-hook-rewrite"]
RUNS_PER_MECHANISM = 5


def reset_workdir(mechanism: str, n: int) -> Path:
    """Create a fresh working copy of the fixture for one run; returns the copy's path."""
    workdir = Path(__file__).parent / mechanism / f"run-{n}"
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True)
    target = workdir / "fixture.py"
    shutil.copyfile(FIXTURE, target)
    return target


def expected_after() -> str:
    return FIXTURE.read_text().replace(EDIT["old_string"], EDIT["new_string"])


def main() -> None:
    for m in MECHANISMS:
        for n in range(1, RUNS_PER_MECHANISM + 1):
            target = reset_workdir(m, n)
            print(f"prepared {target}")


if __name__ == "__main__":
    main()