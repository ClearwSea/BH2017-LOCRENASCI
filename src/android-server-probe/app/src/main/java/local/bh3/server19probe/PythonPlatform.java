package local.bh3.server19probe;

import android.content.Context;
import android.os.Build;
import android.util.Log;
import com.chaquo.python.android.AndroidPlatform;
import java.io.*;

/** Use the packaged native ELF ABI when a translator exposes only host ABIs. */
final class PythonPlatform {
    private static boolean asset(Context context, String abi) {
        try (InputStream in = context.getAssets().open("chaquopy/stdlib-" + abi + ".imy")) { return true; }
        catch (IOException absent) { return false; }
    }
    static AndroidPlatform create(Context context) throws IOException {
        boolean listed = false;
        for (String abi : Build.SUPPORTED_ABIS) if (asset(context, abi)) listed = true;
        if (!listed && asset(context, "armeabi-v7a")) {
            File library = new File(context.getApplicationInfo().nativeLibraryDir, "libchaquopy_java.so");
            byte[] header = new byte[20];
            try (DataInputStream in = new DataInputStream(new FileInputStream(library))) { in.readFully(header); }
            // ELF32, little endian, EM_ARM. Do not infer process ABI from the device model.
            if (header[0] == 0x7f && header[1] == 'E' && header[2] == 'L' && header[3] == 'F'
                    && header[4] == 1 && header[5] == 1 && header[18] == 40 && header[19] == 0) {
                AndroidPlatform.ABI = "armeabi-v7a";
                Log.i("Server19Python", "Using packaged ELF32 ARM Python ABI; device ABI list has no matching assets");
            }
        }
        return new AndroidPlatform(context);
    }
}
