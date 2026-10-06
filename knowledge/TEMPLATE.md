---
# Field note: how a binary was decompiled, written so the next agent can repeat it. Keep the keys; delete the comments.
kind: title                                               # title (one program/game) | topic (a tool, technique or family)
title: "Hybrid DLL reconstruction of Foo Racer 1.2"       # what you reconstructed, in plain words
subject: "Foo Racer"                                      # the program or game's usual name
subject_version: "1.2 (GOG, Windows x86)"                 # exact build that you worked on
platform: windows                                         # windows | linux | macos | n64 | ps2 | xbox360 | ... (the original's platform)
family: native                                            # ud scan family key (native, dotnet, unity-il2cpp, unreal, n64, ...)
engine: renderware                                        # ud scan engine key, or unknown
route: hybrid-dll                                         # hybrid-dll | clean-room | static-recomp | managed-decompile | engine-project | script-recovery | other
formats: ["PE32 x86 32-bit"]                              # from ud scan
compiler: "Visual Studio 2003 (7.1)"                      # from ud scan
tools: ["Ghidra 12.1.4", "pyghidra-mcp 0.2.7", "ud 0.1.0"]
status: working                                           # idea | in-progress | working | complete | abandoned
agents: ["Claude Code (Opus 5.5)"]                        # agent + model that did the work
humans: []                                                # handles of the humans involved, if they want credit
date: 2026-10-06
links: []                                                 # public links only (never the private decomp repo)
tags: []                                                  # free-form: renderware, audio, file-format, ...
---

# Hybrid DLL reconstruction of Foo Racer 1.2

> Two to four sentences: what you reconstructed, by which route, how far it got, and how you know it matches
> the original.

## Setup
Exact versions: the program build (store, language, executable size or hash), OS, compilers, Ghidra,
pyghidra-mcp, recompilers, emulators. The versions that worked are the most useful thing you can write down.

## Route and why
Which route, what else `ud scan` offered or you considered, and why you chose this one.

## What the program really does
Subsystems and how they connect, file formats, data structures, algorithms (by name), timing, the platform
APIs it uses and what replaced them. Your own words; no decompiled code; at most a few key addresses where
they help the next agent find something.

## Build and run
The shortest path to reproduce the reconstruction's build and the asset extraction (commands, settings),
without sharing the private code.

## Verification
The oracle (scripted runs, traces, screenshots, `ud run --compare`), what matched, and what you did NOT verify.

## Gotchas
The most valuable section. Numbered; each one symptom -> cause -> fix.
1. **Symptom.** What you saw. **Cause:** what it really was. **Fix:** what worked.

## Open questions
What's unresolved, and the next step.
