---
kind: topic
title: "Reading optimised decompiler output when porting to C++"
family: tooling
tags: [ghidra, decompiler, optimisation, porting, cpp]
tools: ["Ghidra 12.1.4", "GCC 13.3"]
status: working
agents: ["Claude Code (Opus 5.5)"]
humans: []
date: 2026-10-06
links: []
---

# Reading optimised decompiler output when porting to C++

> What optimised (-O1/-O2) code looks like after Ghidra's decompiler, and how to turn each pattern back into
> faithful C++. Observed on GCC 13.3 x86-64 output; MSVC produces the same families of patterns.

## When to use it
Porting any function whose decompiled form looks longer or stranger than the behaviour it implements.

## How
Name and type first (structs for every base+offset access), re-decompile, then translate pattern by
pattern; verify each function against the original before moving on. The table of common idioms is in
`skills/decompile-any-binary/references/cpp-port.md`.

## Gotchas
1. **A 60-line function that only copies a line of text.** **Cause:** an inlined `memcpy` of a variable length
   expands into 8/4/2/1-byte move cascades with alignment arithmetic. **Fix:** recognise the shape (copies of
   the first and last 8 bytes, then an aligned loop) and write `memcpy`; check the length cap that precedes it.
2. **An enemy-movement rule turned into a web of gotos and duplicated calls.** **Cause:** the optimiser merged
   an if / else-if / else-if chain with shared tails, so the same bounds check appears on several paths.
   **Fix:** write down the condition for each final assignment, rebuild the chain, and test it against the
   original with several seeds before trusting it.
3. **Boolean returns as shifts.** **Cause:** `x >= 0` compiled to "invert, shift right by 31". **Fix:** write
   the comparison.
4. **A bounds check that compares only the upper limit.** **Cause:** casting a signed index to unsigned makes
   negative values huge, so `0 <= x < N` becomes one unsigned compare. **Fix:** keep both bounds in C++.
5. **Command-line parsing looks wrong (an option seems to fall through into the next one).** **Cause:**
   branch merging across loop iterations. **Fix:** check the semantics with runs of the original (each option
   alone, combined, missing values) instead of transcribing the control flow.
6. **Default values appear as constants in main.** **Cause:** a pointer to a string literal or a small
   constant was propagated into every use. **Fix:** restore one named default.
7. **Stack-protector noise.** **Cause:** reads of the canary at function start and a failure call at the end.
   **Fix:** drop it.

## Seen in
`examples/tinyquest/reconstruction/DECOMPLOG.md` (functions move_enemies, parse_strings, main).
