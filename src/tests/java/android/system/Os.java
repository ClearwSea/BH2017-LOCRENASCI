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
        // Windows can briefly deny a directory move while its scanner closes
        // a just-written child; keep the host shim atomic and retry only that.
        for (int attempt = 0; ; attempt++) {
            try {
                if (Files.isDirectory(Paths.get(source)) && !Files.exists(Paths.get(target)))
                    Files.move(Paths.get(source), Paths.get(target), StandardCopyOption.ATOMIC_MOVE);
                else
                    Files.move(Paths.get(source), Paths.get(target), StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
                break;
            } catch (AccessDeniedException busy) {
                if (attempt == 9) throw busy;
                try { Thread.sleep(50); } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt(); throw new IOException(interrupted);
                }
            }
        }
        calls++;
        if (crashAfter == calls) throw new Interrupted();
    }
}
