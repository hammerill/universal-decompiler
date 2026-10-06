@AGENTS.md

## Claude Code specifics
- Installed as a plugin, the skills are namespaced (`/universal-decompiler:decompile-any-binary`) and a
  SessionStart hook (`hooks/hooks.json`) puts `ud` on PATH.
- In a clone, `.claude/settings.json` adds the same PATH hook, and `.claude/skills` is a copy of `skills/`.
- pyghidra-mcp: `ud mcp pyghidra --agent claude --write` writes `.mcp.json` (`"type": "http"`) in the decomp
  repo; or `claude mcp add --transport http pyghidra-mcp http://127.0.0.1:8000/mcp`.
