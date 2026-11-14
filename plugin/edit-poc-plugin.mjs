/**
 * OpenCode plugin implementing mechanism (c): hook-based argument rewriting.
 *
 * The model calls the native `edit` tool with placeholder/simple args; this hook
 * rewrites `event.input` to the deterministic computed replacement before the
 * built-in tool executes — so the native diff pipeline (metadata.files -> PatchDiff)
 * renders it, with no LLM persuasion step.
 *
 * For the POC this is deliberately simple: it detects calls whose oldString is a
 * sentinel token (EDITPOC_OLD/EDITPOC_NEW) and swaps in the computed values from a
 * JSON spec file. Replace the `rewrite()` body with real logic (e.g. LSP rename).
 *
 * Install: opencode.yml (or config) plugin entry pointing at this file.
 */

import { readFileSync } from "node:fs"
import { resolve } from "node:path"

const SPEC_FILE = process.env.MCP_EDIT_POC_SPEC ?? resolve(process.cwd(), "edit-spec.json")

function rewrite(input: any): any {
  // POC rule: sentinel replacement. Real logic (LSP, codemods, ...) goes here.
  if (typeof input?.oldString === "string" && input.oldString.includes("EDITPOC_OLD")) {
    try {
      const spec = JSON.parse(readFileSync(SPEC_FILE, "utf-8"))
      return {
        ...input,
        oldString: String(spec.oldString ?? input.oldString),
        newString: String(spec.newString ?? input.newString),
        replaceAll: Boolean(spec.replaceAll ?? input.replaceAll),
      }
    } catch {
      return input // spec missing/unreadable: leave the call as-is
    }
  }
  return input
}

export const EditPocPlugin = async (ctx: any) => {
  ctx.tool.hook("execute.before", async (event: any) => {
    if (event.tool !== "edit") return
    event.input = rewrite(event.input)
  })
  return {}
}