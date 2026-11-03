package android.system;

import java.io.IOException;
import java.nio.file.*;

/** Host-only syscall shim; production resolves Android's Os.rename. */
public final class Os {
    public static int calls, crashAfter;
    public static boolean failReceipt;
    public static String failReceiptTarget;
    public static final class Interrupted extends Error { }
    public static void rename(String source, String target) throws IOException {
        if (failReceipt && target.equals(failReceiptTarget)) {
            failReceipt = false; throw new IOException("injected receipt install failure");
        }
        Files.move(Paths.get(source), Paths.get(target), StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
        calls++;
        if (crashAfter == calls) throw new Interrupted();
    }
}
