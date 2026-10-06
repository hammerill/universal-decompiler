// Exports every function of the current program as JSON for `ud funcs import`:
//   {"program", "image_base", "functions": [{"address", "name", "namespace", "size", "thunk", "external"}]}
//
// Headless (Ghidra 12.x):
//   "$GHIDRA_INSTALL_DIR/support/analyzeHeadless" ghidra decomp -import data/game.exe \
//       -scriptPath "<universal-decompiler>/ud/ghidra" -postScript ExportFunctions.java build/functions.json
//   (re-export after renaming: replace "-import data/game.exe" with "-process game.exe -noanalysis")
// GUI: Script Manager > universal-decompiler > ExportFunctions (asks for the output file).
//@category universal-decompiler
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;

import java.io.FileOutputStream;
import java.io.OutputStreamWriter;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;

public class ExportFunctions extends GhidraScript {

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String out = args.length > 0 ? args[0] : askFile("Export functions for ud", "Save").getAbsolutePath();
        FunctionIterator it = currentProgram.getFunctionManager().getFunctions(true);
        int n = 0;
        try (PrintWriter w = new PrintWriter(new OutputStreamWriter(new FileOutputStream(out), StandardCharsets.UTF_8))) {
            w.println("{\"program\": " + q(currentProgram.getName()) + ", \"image_base\": "
                + q("0x" + currentProgram.getImageBase().toString()) + ", \"functions\": [");
            while (it.hasNext() && !monitor.isCancelled()) {
                Function f = it.next();
                if (n++ > 0) {
                    w.println(",");
                }
                w.print("  {\"address\": " + q(String.format("0x%x", f.getEntryPoint().getOffset())) + ", \"name\": " + q(f.getName())
                    + ", \"namespace\": " + q(f.getParentNamespace().getName(true))
                    + ", \"size\": " + f.getBody().getNumAddresses()
                    + ", \"thunk\": " + f.isThunk() + ", \"external\": " + f.isExternal() + "}");
            }
            w.println();
            w.println("]}");
        }
        println("ud: exported " + n + " functions to " + out);
    }

    private static String q(String s) {
        StringBuilder b = new StringBuilder("\"");
        for (char c : s.toCharArray()) {
            switch (c) {
                case '"': b.append("\\\""); break;
                case '\\': b.append("\\\\"); break;
                case '\n': b.append("\\n"); break;
                case '\r': b.append("\\r"); break;
                case '\t': b.append("\\t"); break;
                default:
                    if (c < 0x20) {
                        b.append(String.format("\\u%04x", (int) c));
                    } else {
                        b.append(c);
                    }
            }
        }
        return b.append('"').toString();
    }
}
