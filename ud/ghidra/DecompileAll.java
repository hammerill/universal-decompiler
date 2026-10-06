// Writes the decompiler's C for every non-external function to one file per function, for agents that work
// without MCP. The output is derived from the original: write it under build/ (gitignored), never commit it.
//
// Headless (Ghidra 12.x):
//   "$GHIDRA_INSTALL_DIR/support/analyzeHeadless" ghidra decomp -process game.exe -noanalysis \
//       -scriptPath "<universal-decompiler>/ud/ghidra" -postScript DecompileAll.java build/decomp
//@category universal-decompiler
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;

import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStreamWriter;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;

public class DecompileAll extends GhidraScript {

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        File dir = new File(args.length > 0 ? args[0] : "build/decomp");
        dir.mkdirs();
        DecompInterface ifc = new DecompInterface();
        ifc.openProgram(currentProgram);
        FunctionIterator it = currentProgram.getFunctionManager().getFunctions(true);
        int n = 0;
        while (it.hasNext() && !monitor.isCancelled()) {
            Function f = it.next();
            if (f.isExternal() || f.isThunk()) {
                continue;
            }
            DecompileResults r = ifc.decompileFunction(f, 60, monitor);
            String name = String.format("%s_%s.c", f.getEntryPoint().toString(), f.getName().replaceAll("[^A-Za-z0-9_]", "_"));
            try (PrintWriter w = new PrintWriter(new OutputStreamWriter(new FileOutputStream(new File(dir, name)), StandardCharsets.UTF_8))) {
                w.println("// " + f.getName() + " @ " + f.getEntryPoint() + "  (decompiler output: local only, never commit)");
                w.println(r.decompileCompleted() ? r.getDecompiledFunction().getC() : "// failed: " + r.getErrorMessage());
            }
            n++;
        }
        ifc.dispose();
        println("ud: decompiled " + n + " functions into " + dir.getAbsolutePath());
    }
}
