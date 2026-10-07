---
name: verify-and-run
description: Build, launch and verify a reconstruction against the original binary, which is the oracle - ud build error summaries, ud run (capture stdout/stderr and log files, window screenshots on Windows, Linux and macOS, kill by exact PID at a timeout), side-by-side runs and ud run --compare for deterministic output, repeatable scenarios (seeds, scripted input, traces), and the 3-strike circuit breaker. Use whenever the reconstruction must be built, run, tested, compared with the original, or when something fails repeatedly.
---

# Verify and run

The original binary's behaviour is the reference; your reading of the code is not. A function is
`verified` only when the original and the reconstruction agree on something observable.

## Build
```bash
ud build                     # Release by default ([build] in ud.toml), 64-bit with MSVC
ud build --config Debug -D UD_WITH_SDL=OFF
ud build --json              # {ok, errors: [{file, line, code, message}], log}
```
Read the first error only, fix it, rebuild. The full log is `build/ud-build.log`.

## Run
```bash
ud run --timeout 20 --shot              # rebuilt: stdout/stderr, logs, a screenshot at 5 s, killed at 20 s
ud run --original --timeout 20 --shot   # the original, same capture
ud run --compare -- --seed 42           # both with the same args: identical stdout and exit code?
ud run --json -- <args>
```
- Output goes to `build/ud-run/<rebuilt|original>-<time>/` (stdout.txt, stderr.txt, shot-*.png, copied logs
  from `[run] logs` in `ud.toml`). **Look at the screenshots**; read them at reduced size to save tokens.
- Killing at the timeout is normal for GUI programs. A crash (signal, or a Windows exception code such as
  0xC0000005) returns 1; a plain non-zero exit code is reported, not judged.
- Processes are killed by exact PID (the process group/tree `ud run` started). Never `pkill -f`.
- Screenshots: Windows (also from WSL) via PrintWindow on the process's window; Linux X11 via
  xdotool + ImageMagick; Wayland via grim (whole screen); macOS via `screencapture` (whole screen; the
  terminal running the agent needs Screen Recording permission, otherwise the shot shows only the desktop).
  Install hints: `ud tools show screenshot-x11`.

## Make the comparison repeatable
- **Determinism:** fix seeds (command-line flag, or patch the RNG seed via the hybrid DLL), fixed time
  step, headless backend for CI.
- **Scripted input:** a replay file both programs read, or a debug key sequence; for consoles, the
  emulator's input recording.
- **Traces:** log a few key values per frame (position, health, RNG state, score) from the reconstruction;
  get the same values from the original with a debugger breakpoint script or, in the hybrid route, from the
  original code path. Diff the traces and find the first frame that differs: that's where the bug is.
- **Screens:** same save, same frame, both screenshots; compare by eye first, by pixel diff only when the
  renderer is supposed to be exact.
- **Exit and output:** `ud run --compare` for anything that prints (tools, servers, logs, headless modes).

## Circuit breaker (identical to universal-modder's)
If the same failure repeats **3 times** (same error, same mismatch, same crash), stop. Write down in
`DECOMPLOG.md` what you know: what you tried, what changed, what didn't. Then change approach (narrow it
with a trace, bisect with the hybrid's per-function switch, re-read the original function, test a smaller
case) or ask the user. Update the "Circuit breaker" line in the journal's status block.

## Recording evidence
For the done check, log in `DECOMPLOG.md`: the command, the OS and compiler, the result (MATCH, the
screenshot path, the exit code), and anything not verified with the reason.
