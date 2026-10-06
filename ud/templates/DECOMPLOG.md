# DECOMPLOG

The journal of this decompilation. **Anything that isn't written here is lost at the next context
compaction.** Log paths, addresses, function names, types, file formats, what failed and why, and the next
step. Progress reports go here too; they are not a reason to stop.

## Status
- Phase: intake <!-- intake | prior art | recon | tools | plan | inventory | vertical slice | modules | assets | verify | done -->
- Done criterion: see DECOMP_PLAN.md
- Next step: run `ud scan data/<binary>`
- Circuit breaker: <!-- "<failure>" x<count>; at 3 identical failures: stop, write down what you know, change approach or ask -->

## Facts (keep current)
| What | Value | Source |
|---|---|---|
| Binary | data/<file> | |
| Format / arch / compiler | | ud scan |

## Log
### {date}
- `ud init` run; repo set up (data/ ignored, pre-push guard installed).
