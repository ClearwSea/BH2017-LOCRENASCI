package local.bh3.server19probe;

import android.content.Context;
import android.system.Os;
import java.io.*;

/** Startup setting only; never edits account data or an installed native library. */
final class DamageMode {
    private static File file(Context context) { return new File(context.getFilesDir(), "damage-mode.bin"); }
    static int current(Context context) {
        try (DataInputStream in = new DataInputStream(new FileInputStream(file(context)))) {
            int value = Integer.reverseBytes(in.readInt()); return value == 1 ? 1 : 20;
        } catch (IOException absent) { return 20; }
    }
    static void requireCanApply(Context context, int mode) throws IOException {
        if (mode != 1 && mode != 20) throw new IOException("无效伤害倍率");
        if (current(context) == mode) return;
        try (BufferedReader in = new BufferedReader(new FileReader("/proc/self/maps"))) {
            String line;
            while ((line = in.readLine()) != null) if (line.contains("libil2cpp.so"))
                throw new IOException("伤害设置已保存。请从最近任务彻底退出游戏并重新打开应用，再点击开始游戏，使新倍率生效。");
        }
    }
    static void apply(Context context, int mode) throws Exception {
        requireCanApply(context, mode);
        File destination = file(context), part = new File(destination.getPath() + ".part");
        try (FileOutputStream out = new FileOutputStream(part)) {
            out.write(new byte[]{(byte)mode, 0, 0, 0}); out.getFD().sync();
        }
        Os.rename(part.getPath(), destination.getPath());
    }
}
