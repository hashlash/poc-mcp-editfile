"""Smoke test: start the server over stdio, list tools, call edit_diff on a fixture."""

import asyncio
import hashlib
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> int:
    fixture_dir = Path(tempfile.mkdtemp(prefix="editpoc-"))
    target = fixture_dir / "hello.py"
    target.write_text("def greet():\n    print('hi')\n")

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_edit_poc.server"],
        cwd=str(Path(__file__).parent.parent),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("tools:", sorted(t.name for t in tools.tools))

            result = await session.call_tool(
                "edit_diff",
                {"path": str(target), "old_string": "print('hi')", "new_string": "print('hello')"},
            )
            print("is_error:", result.is_error)
            print("result:", result.content[0].text[:300])

            # error path: old_string not found
            result2 = await session.call_tool(
                "edit_diff",
                {"path": str(target), "old_string": "print('nope')", "new_string": "x"},
            )
            print("error-path is_error:", result2.is_error, "|", result2.content[0].text[:80])

            # verify_edit with known hash
            digest = hashlib.sha256(target.read_text().encode()).hexdigest()
            result3 = await session.call_tool("verify_edit", {"path": str(target), "expected_sha256": digest})
            print("verify:", result3.content[0].text[:120])
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))