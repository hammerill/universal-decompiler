"""`ud` command line: one entry point for every tool, so skills can say `ud <group> <cmd>`.

Derived from universal-modder's um/cli.py (MIT, Copyright (c) 2026 Rehan and universal-modder contributors).
"""
from __future__ import annotations

import argparse
import importlib
import sys

from ud import __doc__ as DOC, __version__

GROUPS = ["init", "scan", "tools", "mcp", "funcs", "build", "run", "assets", "publish", "kb"]


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")   # Windows consoles default to a code page
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(prog="ud", description=DOC, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"universal-decompiler {__version__}")
    sub = ap.add_subparsers(dest="group", metavar="<group>")
    for g in GROUPS:
        importlib.import_module(f"ud.{g}").register(sub)
    args = ap.parse_args(argv)
    if not getattr(args, "func", None):
        # a group without a command: show that group's help; exit 2 (usage error)
        (sub.choices.get(args.group) if args.group else ap).print_help(sys.stderr)
        sys.exit(2)
    rc = args.func(args)
    sys.exit(rc or 0)


if __name__ == "__main__":
    main()
