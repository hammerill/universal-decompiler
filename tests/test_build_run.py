"""ud build (error summaries, a real scaffold build), ud run (capture, timeout kill, compare), ud assets check,
and the TinyQuest example end to end."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

import pytest
from conftest import ROOT, have_cxx, ud

from ud import build, init

GCC_LOG = """[ 50%] Building CXX object CMakeFiles/game.dir/src/world.cpp.o
/home/u/decomp/src/world.cpp:161:21: error: 'foo' was not declared in this scope
  161 |     foo();
/home/u/decomp/src/main.cpp:12: error: expected ';' before '}' token
/home/u/decomp/src/main.cpp:20:5: warning: unused variable 'x' [-Wunused-variable]
/usr/bin/ld: CMakeFiles/game.dir/src/main.cpp.o: in function `main':
main.cpp:(.text+0x1d): undefined reference to `render_frame(World const&)'
"""
MSVC_LOG = r"""  world.cpp
C:\decomp\src\world.cpp(42,10): error C2065: 'foo': undeclared identifier [C:\decomp\build\game.vcxproj]
C:\decomp\src\world.cpp(43): warning C4244: conversion from 'double' to 'float'
main.obj : error LNK2019: unresolved external symbol "void __cdecl render_frame(void)" referenced in function main [C:\decomp\build\game.vcxproj]
"""
CMAKE_LOG = """CMake Error at CMakeLists.txt:12 (add_executable):
  Cannot find source file:
    src/missing.cpp
"""


def test_parse_gcc_errors():
    errs, n, warns = build.parse_errors(GCC_LOG)
    assert n == 3 and warns == 1
    assert errs[0] == {"file": "/home/u/decomp/src/world.cpp", "line": 161, "code": None, "message": "'foo' was not declared in this scope"}
    assert errs[1]["line"] == 12
    assert "undefined reference" in errs[2]["message"]


def test_parse_msvc_and_cmake_errors():
    errs, n, warns = build.parse_errors(MSVC_LOG)
    assert n == 2 and warns == 1
    assert errs[0]["file"].endswith("world.cpp") and errs[0]["line"] == 42 and errs[0]["code"] == "C2065"
    assert errs[1]["code"] == "LNK2019"
    errs, n, _ = build.parse_errors(CMAKE_LOG)
    assert n == 1 and errs[0]["file"] == "CMakeLists.txt" and errs[0]["line"] == 12


def test_build_without_cmakelists_is_usage_error(repo):
    assert ud("build", cwd=repo).returncode == 2


@pytest.mark.skipif(not have_cxx(), reason="needs CMake and a C++ compiler")
def test_scaffold_builds_and_runs_headless(repo):
    init.init(scaffold=True)
    r = ud("build", "-D", "UD_WITH_SDL=OFF", "--json", cwd=repo)
    data = json.loads(r.stdout)
    assert r.returncode == 0, data
    assert (repo / "build" / "ud-build.log").exists()
    exe = "build/bin/game" + (".exe" if os.name == "nt" else "")
    assert any(e.replace("\\", "/").endswith(exe.split("/")[-1]) for e in data["executables"]), data
    r = ud("run", "--exe", exe, "--timeout", "30", "--json", "--", "--headless", "--frames", "3", cwd=repo)
    run = json.loads(r.stdout)
    assert r.returncode == 0 and run["exit_code"] == 0 and "vertical slice ok" in run["stdout_tail"]
    # a compile error is summarised as file:line
    main = repo / "src" / "main.cpp"
    main.write_text(main.read_text(encoding="utf-8").replace("return 0;\n}", "return undefined_symbol_xyz;\n}"), encoding="utf-8")
    r = ud("build", "-D", "UD_WITH_SDL=OFF", "--json", cwd=repo)
    data = json.loads(r.stdout)
    assert r.returncode == 1 and data["stage"] == "build"
    assert any("main.cpp" in (e["file"] or "") and "undefined_symbol_xyz" in e["message"] for e in data["errors"]), data["errors"]


def write_cfg(repo, exe_args, orig_args, extra=""):
    py = sys.executable.replace("\\", "/")
    (repo / "ud.toml").write_text(f'[run]\nexe = "{py}"\nargs = {json.dumps(exe_args)}\noriginal = "{py}"\n'
                                  f'original_args = {json.dumps(orig_args)}\noriginal_cwd = "."\n{extra}', encoding="utf-8")


def test_run_captures_and_kills_at_timeout(repo):
    write_cfg(repo, ["-c", "import time; print('started', flush=True); time.sleep(60)"], [])
    t0 = time.time()
    r = ud("run", "--timeout", "2", "--json", cwd=repo)
    res = json.loads(r.stdout)
    assert time.time() - t0 < 30
    assert r.returncode == 0 and res["timed_out"] and res["exit_code"] is None
    assert res["stdout_tail"] == ["started"]
    assert (repo / res["run_dir"] / "stdout.txt").exists()


def test_run_exit_codes_and_crash(repo):
    write_cfg(repo, ["-c", "import sys; print('dead'); sys.exit(2)"], [])
    res = json.loads(ud("run", "--json", cwd=repo).stdout)
    assert res["exit_code"] == 2 and res["ok"] and not res["crashed"]        # a normal non-zero exit isn't a crash
    if os.name != "nt":
        write_cfg(repo, ["-c", "import os, signal; os.kill(os.getpid(), signal.SIGSEGV)"], [])
        r = ud("run", "--json", cwd=repo)
        assert r.returncode == 1 and json.loads(r.stdout)["crashed"]


def test_run_collects_logs(repo):
    write_cfg(repo, ["-c", "open('game.log','w').write('frame 1\\n')"], [], extra='logs = ["*.log"]\n')
    res = json.loads(ud("run", "--json", cwd=repo).stdout)
    assert len(res["logs"]) == 1 and res["logs"][0].replace("\\", "/").endswith("game.log")


def test_run_compare_match_and_mismatch(repo):
    write_cfg(repo, ["-c", "print('a'); print('b')"], ["-c", "print('a'); print('b')"])
    r = ud("run", "--compare", "--timeout", "20", cwd=repo)
    assert r.returncode == 0 and "MATCH" in r.stdout
    write_cfg(repo, ["-c", "print('a'); print('c')"], ["-c", "print('a'); print('b')"])
    r = ud("run", "--compare", "--timeout", "20", "--json", cwd=repo)
    c = json.loads(r.stdout)["comparison"]
    assert r.returncode == 1 and c["first_difference"] == {"line": 2, "original": "b", "rebuilt": "c"}


def test_run_without_config_is_usage_error(repo):
    assert ud("run", cwd=repo).returncode == 2
    assert ud("run", "--original", cwd=repo).returncode == 2


def test_assets_check(repo):
    init.init(scaffold=True)
    script = repo / "tools" / "extract_assets.py"
    script.write_text(script.read_text(encoding="utf-8").replace('    # "models/player.dff",', '    "models/player.dff",\n    "sounds/hit.wav",'),
                      encoding="utf-8")
    r = ud("assets", "check", "--json", cwd=repo)
    res = json.loads(r.stdout)
    assert r.returncode == 1 and res["missing"] == ["models/player.dff", "sounds/hit.wav"]
    for rel in ("models/player.dff", "sounds/hit.wav"):
        (repo / "data" / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / "data" / rel).write_bytes(b"x")
    r = ud("assets", "check", cwd=repo)
    assert r.returncode == 0 and "assets OK" in r.stdout


def test_assets_check_without_script(repo):
    init.init()
    assert ud("assets", "check", cwd=repo).returncode == 2


@pytest.mark.skipif(not have_cxx(), reason="needs CMake and a C++ compiler")
def test_tinyquest_example_end_to_end(tmp_path):
    r = subprocess.run([sys.executable, str(ROOT / "examples" / "tinyquest" / "run_example.py"), "--work", str(tmp_path / "w")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-2000:]
    assert "example OK: 7 cases identical to the original" in r.stdout
