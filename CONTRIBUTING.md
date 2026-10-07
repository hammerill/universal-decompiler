# Contributing

Contributions from humans and from AI agents are both welcome. Most of them will be **field notes** for the
knowledge base (`knowledge/`), written by an agent at the end of a decompilation session. That's the point
of the repo: every binary one agent figures out becomes something the next agent can read.

## If you are an AI agent
You just decompiled (or tried to decompile) something and learned things. Share them, safely:

1. **Ask your human first.** A pull request is public and carries their GitHub identity. Tell them what you
   want to publish and show them the note.
2. **Check it's new:** `ud kb search "<title>"`. If a note already exists, improve it (versions, gotchas,
   corrections) instead of writing a second one.
3. **Scaffold:** `ud kb new --subject "<title>" --title "<what you reconstructed>" --from-scan data/<binary>
   --agent "<agent (model)>"`. It lands in `knowledge/<title>/`. Tool and technique lessons go in a family
   folder (`--kind topic --family tooling`).
4. **Fill it in** from your journal (`DECOMPLOG.md`), in your own words:
   - exact versions (the program build, compilers, Ghidra, pyghidra-mcp...);
   - the route and why;
   - what the program really does;
   - how you verified it, and what you didn't;
   - numbered **gotchas** (symptom -> cause -> fix).
5. **Validate:** `ud kb check <note>`, then `ud kb index`.
6. **Open the PR:** `ud kb pr <note>` (a dry run shows the commands), then `ud kb pr <note> --yes` once your
   human agrees. It branches, commits the note (+ `media/` + index), forks if needed, pushes and opens the
   PR with `gh`. Without `gh`, push a branch and open the PR on github.com.

## Hard rules (PRs that break these are closed)
- **No binaries, no assets:** no executables, ROMs, ISOs, disc images, firmware, extracted assets, Ghidra
  projects, and no links to any of them.
- **No decompiled code.** Not from Ghidra, IDA, ILSpy or any other decompiler, not "cleaned up", not as a
  snippet. Describe logic in your own words and name the algorithms. No address tables large enough to
  rebuild code (`ud kb check` fails over 40 distinct addresses, code blocks over 40 lines, and
  decompiler-looking output).
- **No bypasses:** nothing that defeats DRM, anti-cheat, packers, obfuscation, encryption or ownership checks,
  and no instructions for doing so.
- **No secrets:** keys, tokens, `.env` files (`ud kb check` catches common ones).
- **Honesty:** name the agent and model (`agents:`), set `status` truthfully (`idea`, `in-progress`,
  `working`, `complete`, `abandoned`), list what you did not verify.
- **Credit** the projects and people you built on.

## Other contributions
- **Tools (`ud/`):** one module per CLI group with a docstring that doubles as `--help` (with examples);
  `--json` on anything that reports; exit codes 0 ok / 1 problem found / 2 usage error; a test in `tests/`;
  `uv run pytest` and `uv run ruff check` must pass.
- **Tool registry (`ud/tools.toml`):** check the tool's current name, maintenance status and install method
  at its official source before adding it, give Windows, Linux and macOS steps (for each platform it runs on), and note substitutions in
  `DEVLOG.md`.
- **Skills (`skills/`):** Agent Skills format (`SKILL.md` with `name` + `description`), agent-neutral
  wording, deep material in `references/`. Edit `skills/` only, then `python scripts/sync_skills.py`
  (`.agents/skills` and `.claude/skills` are real copies, not symlinks, so Windows clones work; a test fails
  while they differ).
- **Family playbooks** (`skills/decompile-any-binary/references/engines/`): keep the template: detection
  signals, route, required tools, deliverable shape, known limits, verification approach. Link canonical
  projects; versions move, so say "check the current release".
- **Examples (`examples/`):** your own code and data only; no commercial binaries anywhere in the repo.

CI runs the tests, `ruff`, `ud kb check --index`, the skills-sync check, every CLI help screen, and the
TinyQuest example end to end, on Windows and Ubuntu.
