"""universal-decompiler: the `ud` CLI an AI coding agent uses to turn a binary the user owns into a
compilable C++/CMake PC reconstruction (or, for vendor engines, a recovered project).

Groups (see `ud <group> --help`; every reporting command takes --json):
  init      set up the current git repo as a decomp repo: data/, .gitignore, journal + plan, pre-push guard
  scan      identify a binary or install folder: format, arch, compiler, debug info, middleware, engine,
            protections; ranked routes, the playbook to read, the tools each route needs
  tools     check the tools a route needs; print exact install steps (never installs anything)
  mcp       print or write the pyghidra-mcp config for your agent
  funcs     the function progress tracker (decomp/progress.json): import, list, set, stats
  build     configure and build the CMake project; full log + short error summary
  run       launch the rebuilt program (or the original), capture output and logs, screenshot, kill by PID
  assets    check that tools/extract_assets.py found everything it needs in data/
  publish   refuse to publish: tracked binaries/assets, public remotes (used by the pre-push hook)
  kb        the knowledge base: search field notes, write one, check it, open a PR

Exit codes: 0 ok, 1 problem found, 2 usage error.
"""

__version__ = "0.1.0"
