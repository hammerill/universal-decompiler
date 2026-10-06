# Java (LWJGL, libGDX, Slick2D, custom)

## Detection signals
`.jar` files (zip with `META-INF/MANIFEST.MF` and `.class` entries), a bundled `jre/`/`runtime/`, launcher
exes wrapping a jar (Launch4j, jpackage), `.class` files (`CAFEBABE` + class version). `ud scan` lists
libraries it sees inside the jar (lwjgl, libgdx, slick, jogl, jmonkeyengine). Obfuscation (ProGuard/Allatori
renaming to `a.b.c`) is common: renaming-only obfuscation leaves logic intact, but don't run deobfuscators
built to defeat protection (string encryption, control-flow obfuscation): stop and tell the user.

## Route
`managed-decompile`: Vineflower (`java -jar vineflower.jar data/Game.jar build/decompiled/`) produces Java
sources; restructure into a **Gradle or Maven** project; replace the bundled native libraries with
current LWJGL 3 / libGDX artifacts from Maven Central for Windows and Linux; fix decompilation errors until
`gradle build` passes.

## Required tools (`ud tools check --route java`)
Git, Python 3.12+, uv, a JDK (the game's major version or newer), Vineflower. Optional: Gradle or Maven,
7-Zip.

## Deliverable shape
`build.gradle(.kts)` or `pom.xml`, `src/main/java/...`, resources restored from the user's jar by
`tools/extract_assets.py` into a gitignored folder (or read from the user's jar at runtime), a run task for
Windows and Linux, README.

## Known limits
- Lambdas, switch-on-string/enum and synthetic accessors need cleanup; generics may be erased in places.
- Old LWJGL 2 games need porting to LWJGL 3 (different windowing/input API): that's the platform layer.
- Obfuscated names stay meaningless until you rename them (an IDE refactor, tracked in the journal).

## Verification approach
Original jar vs rebuilt jar from the same save, same inputs; log comparisons with `ud run --compare` (Java
programs often print to stdout); unit tests on pure logic classes.
