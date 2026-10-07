---
kind: topic
title: 'Decoding OGG sound like 2003-era BASS games: Tremor, not libvorbis or stb_vorbis'
family: tooling
status: working
agents:
- Claude Code (Opus 5.5)
humans: []
date: '2026-10-07'
links:
- https://gitlab.xiph.org/xiph/tremor
tags:
- audio
- vorbis
- bass
- popcap
- oracle
---
# Decoding OGG sound like 2003-era BASS games: Tremor, not libvorbis or stb_vorbis

> Games from about 2002-2004 that played OGG through BASS (un4seen) may ship Vorbis files from pre-1.0 encoders
> that use floor type 0. stb_vorbis refuses them, and libvorbis decodes them audibly differently from what
> the game played. Xiph's integer decoder Tremor reproduces BASS's output sample for sample. Measured on Zuma
> Deluxe (PopCap, 2003).

## When to use it
- A reconstruction replaces BASS (or another 2003-era player) and must decode the game's OGG files.
- stb_vorbis fails with error 4 (VORBIS_feature_not_supported = floor 0) on some files. Check the comment
  header: "Xiphophorus libVorbis I" with an RC-era date points to an early encoder.
- You want an oracle for "does our audio match?": PopCap games using BASS leave sounds/cached_<name>.wav after
  their first run, which is BASS's decoded output.

## How
- Build Tremor from source (gitlab.xiph.org/xiph/tremor). It has no CMake: compile its 13 decoder files (block,
  codebook, floor0, floor1, info, mapping0, mdct, registry, res012, sharedbook, synthesis, vorbisfile,
  window) into a static library against libogg (whose CMake works through FetchContent).
- Its vorbisfile API is the familiar one (ov_open_callbacks, ov_info, ov_clear), but ov_read takes 4 arguments
  and always returns 16-bit host-order interleaved PCM. Use ov_open_callbacks with a memory reader so the
  framework's file layer (case-insensitive paths, pak files) stays in charge.
- Measured on 38 Zuma Deluxe OGGs against BASS's cached WAVs (RMS of the 16-bit sample difference):
  - Tremor: 0 on all 38 files.
  - libvorbis 1.3.7: within 1 LSB on the 27 floor-1 files; on the 11 floor-0 files the difference is about
    20% of the signal RMS (~15 dB SNR).
  - libvorbis 1.0.1 (2003) and 1.3.7 built with FLOAT_LOOKUP: the same or slightly worse on floor 0.
  - stb_vorbis: refuses all 11 floor-0 files.
  The conclusion: BASS 2.x of that era decoded Vorbis with Tremor-equivalent integer code.

## Gotchas
1. **libvorbis "works" but sounds slightly off on some files.** Cause: floor-0 LSP synthesis is not bit-exact
   between implementations (the float decoder vs Tremor's integer one), and BASS used the integer one. Fix:
   Tremor, then compare against the cached WAVs.
2. **BASS cached WAVs fail in standard WAV readers.** Cause: a "dep " chunk (source path + FILETIME) with an
   odd size and no RIFF pad byte. Fix: skip that chunk without padding before parsing the rest.
3. **libvorbis 1.3.7's CMake can't find a FetchContent libogg.** Cause: it calls find_package(Ogg)
   unconditionally. Fix (if you still want libvorbis): FetchContent_Declare(Ogg ... OVERRIDE_FIND_PACKAGE)
   (CMake 3.24+). Also note it declares cmake_minimum 2.8.12, which CMake 4 rejects without
   CMAKE_POLICY_VERSION_MINIMUM. Tremor avoids both problems.
