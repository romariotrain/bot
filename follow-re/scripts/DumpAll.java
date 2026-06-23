// Ghidra headless post-script: dump decompiled functions, imports, strings.
// @category Analysis

import java.io.PrintWriter;
import java.io.File;
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileOptions;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.symbol.Symbol;
import ghidra.program.model.symbol.SymbolIterator;
import ghidra.program.model.symbol.SymbolTable;
import ghidra.program.model.data.StringDataInstance;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.DataIterator;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.ExternalManager;
import ghidra.program.model.symbol.ExternalLocation;
import ghidra.program.model.symbol.ExternalLocationIterator;

public class DumpAll extends GhidraScript {
    @Override
    public void run() throws Exception {
        String outDir = System.getenv("OUT_DIR");
        if (outDir == null) outDir = "/tmp";

        // 1) Decompiled C-like code for every function
        try (PrintWriter w = new PrintWriter(new File(outDir, "decompiled.c"))) {
            DecompInterface ifc = new DecompInterface();
            ifc.setOptions(new DecompileOptions());
            ifc.openProgram(currentProgram);
            FunctionIterator fns = currentProgram.getListing().getFunctions(true);
            int count = 0;
            while (fns.hasNext()) {
                if (monitor.isCancelled()) break;
                Function f = fns.next();
                w.println("// ===== " + f.getName() + " @ " + f.getEntryPoint() + " =====");
                DecompileResults res = ifc.decompileFunction(f, 60, monitor);
                if (res != null && res.getDecompiledFunction() != null) {
                    w.println(res.getDecompiledFunction().getC());
                } else {
                    w.println("// (decompile failed)");
                }
                w.println();
                count++;
                if (count % 200 == 0) {
                    println("decompiled " + count + " funcs");
                    w.flush();
                }
            }
            println("Total functions decompiled: " + count);
        }

        // 2) Imports
        try (PrintWriter w = new PrintWriter(new File(outDir, "imports.txt"))) {
            ExternalManager em = currentProgram.getExternalManager();
            for (String lib : em.getExternalLibraryNames()) {
                w.println("=== " + lib + " ===");
                ExternalLocationIterator it = em.getExternalLocations(lib);
                while (it.hasNext()) {
                    ExternalLocation loc = it.next();
                    w.println("  " + loc.getLabel());
                }
            }
        }

        // 3) Strings
        try (PrintWriter w = new PrintWriter(new File(outDir, "strings.txt"))) {
            DataIterator it = currentProgram.getListing().getDefinedData(true);
            while (it.hasNext()) {
                if (monitor.isCancelled()) break;
                Data d = it.next();
                if (d == null) continue;
                String t = d.getDataType().getName().toLowerCase();
                if (t.contains("string") || t.contains("unicode") || t.contains("char")) {
                    Object v = d.getValue();
                    if (v != null) {
                        String s = v.toString().replace("\n", "\\n").replace("\r", "\\r");
                        if (s.length() >= 4) {
                            w.println(d.getAddress() + "\t" + s);
                        }
                    }
                }
            }
        }

        // 4) Function index (name + entry + size)
        try (PrintWriter w = new PrintWriter(new File(outDir, "functions.tsv"))) {
            w.println("entry\tname\tsize");
            FunctionIterator fns = currentProgram.getListing().getFunctions(true);
            while (fns.hasNext()) {
                Function f = fns.next();
                w.println(f.getEntryPoint() + "\t" + f.getName() + "\t" + f.getBody().getNumAddresses());
            }
        }
    }
}
