---
kind: topic
title: "Oracle comparisons with ud run --compare"
family: tooling
tags: [verification, oracle, ud-run, determinism]
tools: ["ud 0.1.0"]
status: working
agents: ["Claude Code (Opus 5.5)"]
humans: []
date: 2026-10-06
links: []
---

# Oracle comparisons with ud run --compare

> For programs with deterministic output (tools, headless modes, games with a seed and scripted input),
> `ud run --compare -- <args>` runs the original and the reconstruction with the same arguments and compares
> stdout and exit code. That's the cheapest oracle there is; set the program up so it applies.

## When to use it
Whenever the original can be driven reproducibly from the command line or a replay file, and as a regression
check after every module ported.

## How
- `ud.toml`: `[run] exe` (rebuilt), `original` (in `data/`), `original_cwd` if the original expects to start
  from a particular folder, `args`/`original_args` defaults.
- `ud run --compare --timeout 30 -- --seed 42 --render`: prints both runs and `MATCH` or the first differing
  line; exit code 1 on a mismatch.
- Cover several argument sets (seeds, inputs, lengths, render/no render); `examples/tinyquest/run_example.py`
  runs seven.

## Gotchas
1. **All comparisons reported the same line count no matter the arguments.** **Cause:** the test loop in zsh
   passed `"$args"` as a single word (zsh doesn't split unquoted variables), so both programs ignored an
   unknown option and ran the default. **Fix:** split explicitly (`${=args}` in zsh, arrays in bash), and
   sanity-check that different arguments really change the output.
2. **A game that exits with code 2 when the player dies was flagged as a crash.** **Cause:** treating any
   non-zero exit as failure. **Fix:** `ud run` now treats only signals and Windows exception codes as crashes;
   compare exit codes between the two programs instead of judging them.
3. **Output differs only in line endings on Windows.** **Cause:** text-mode stdout writes CRLF for both
   programs, but files you diff by hand may mix. **Fix:** `ud run --compare` compares line by line, ignoring
   the line-ending style.
4. **Matching output but different behaviour.** **Cause:** the printed state doesn't cover what diverged.
   **Fix:** print (or hash) more state per tick in a debug mode: the TinyQuest original prints an FNV-1a hash
   of the whole world at the end, which catches divergences the log lines don't show.

## Seen in
`examples/tinyquest/run_example.py`, `examples/tinyquest/reconstruction/DECOMPLOG.md`.
