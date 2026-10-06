# Safety, legality, privacy

These rules keep the user, their machine and their copy safe. None of this is legal advice; when a
specific law, EULA or publisher policy matters, the user reads it themselves.

## What the tool is for
universal-decompiler is for **software the user owns**, for interoperability, preservation and study: to
keep a program running on modern systems, to understand how it works, to fix it for personal use. The
reconstruction and the extracted assets are **for local management only**.

## Ownership
- Work from the user's own install, or from dumps of discs and cartridges they own and made themselves.
- Never download binaries, ROMs, ISOs, firmware, BIOS files or assets, and never point the user to pirated
  copies. Emulators used as the oracle need the user's own BIOS/firmware dumps.
- Ask once at intake ("Do you own this software?") and log the answer in `DECOMP_PLAN.md`.

## Protections: the bright line
- **Never bypass DRM, anti-cheat, packers, obfuscators, encryption or ownership checks**: Denuvo,
  SteamStub, SecuROM, SafeDisc, StarForce, VMProtect, Themida/WinLicense, Arxan, UPX and other packers,
  .NET obfuscators, encrypted IL2CPP metadata, encrypted console executables (PS3 SELF, Switch NCA/NSP/XCI,
  retail XEX, PSP ~PSP, Wii disc partitions).
- `ud scan` reports these and exits 1. Stop and tell the user. Options to offer: a DRM-free edition they
  may own (GOG, an older disc release, an official DRM-free patch), or, for consoles, an executable they
  decrypted themselves on their own hardware with their own keys. The agent never decrypts.
- Anti-cheat means an online game: don't attach debuggers or tracers to it, and don't run the original with
  anything injected while it can reach online services.

## Nothing leaves the machine
- The decomp repo is private. `ud init` installs a git pre-push hook that runs `ud publish check`, which
  refuses pushes that would publish the original, extracted assets, Ghidra projects (they embed the binary)
  or large binaries, and refuses any remote that is a public repository. Don't disable it.
- To untrack something committed by mistake: `git rm --cached <file>` (keeps the file). `git reset --hard`
  deletes ignored files from disk when the dropped commit tracked them. If it's in older commits, rewrite
  history (e.g. `git filter-repo --invert-paths --path <file>`) before any push.
- Decompiler output stays in the gitignored `build/`. The reconstruction is code derived from the original
  and is treated the same way: local only.
- Field notes in `knowledge/` describe what was learned in your own words: no decompiled code, no address
  tables large enough to rebuild code, no assets. `ud kb check` enforces this. PRs only with the user's OK.

## Why publication is blocked
re3 and reVC, reverse-engineered reconstructions of GTA III and Vice City that shipped no game assets,
were taken down from GitHub by a Take-Two DMCA notice in February 2021, restored after a counter-notice,
followed by a lawsuit against the developers in September 2021 and a second takedown in October 2021;
the parties settled in 2023. Shipping no assets did not protect the code. That's why universal-decompiler
treats the reconstruction itself as private.

## The user's machine
- Ask before installing anything, deleting anything, or changing system settings. `ud tools check` prints
  install steps for the user; it never runs them.
- Kill processes by exact PID (`ud run` does). Never `pkill -f` (it matches the agent's own shell) or
  name-pattern kills.
- Bind servers you start (pyghidra-mcp, debug stubs) to `127.0.0.1`. Don't touch servers or processes you
  didn't start, even on a port you wanted.
- Running the original for comparison: it's the user's program on the user's machine. For hybrid
  (DLL-injection) work, use a copy of the install inside `data/`, not the user's live install.

## When to stop and ask
- Ownership is unclear, or the binary is protected.
- A complete decompilation of the same version already exists.
- A step would delete or overwrite the user's files, or install software.
- Anything that publishes: PRs, pushes, uploads.
