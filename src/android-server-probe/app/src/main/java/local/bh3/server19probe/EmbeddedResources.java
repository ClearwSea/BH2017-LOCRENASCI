package local.bh3.server19probe;

import android.content.Context;
import android.system.Os;
import org.json.*;
import java.io.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.zip.*;

/** Only application-owned directories; never writes account data. */
final class EmbeddedResources {
    static final class VideoRequired extends IOException { }
    interface Progress {
        void update(String text);
        /** Bytes actually read for the named phase. Completion is reported only after validation. */
        default void stage(String phase, long completed, long total) { }
        /** The phase required no work for this launch. */
        default void skipped(String phase) { }
    }
    private static long totalBytes(Map<String, JSONObject> entries) throws Exception {
        long total = 0;
        for (JSONObject item : entries.values()) total = Math.addExact(total, item.getLong("size"));
        return total;
    }
    private static final class BytesProgress {
        final Progress target; final String phase; final long total;
        long done; int lastPercent = -1;
        BytesProgress(Progress target, String phase, long total) {
            this.target = target; this.phase = phase; this.total = Math.max(1, total);
            report(false);
        }
        void add(int bytes) { done += bytes; report(false); }
        void report(boolean complete) {
            int percent = complete ? 100 : (int)Math.min(99, (done * 100L) / total);
            if (percent != lastPercent) {
                lastPercent = percent;
                target.stage(phase, complete ? total : Math.min(done, total - 1), total);
            }
        }
        void finish() { report(true); }
    }
    static String hash(byte[] data) throws Exception {
        byte[] digest = MessageDigest.getInstance("SHA-256").digest(data);
        return hex(digest);
    }
    static String hex(byte[] bytes) {
        StringBuilder result = new StringBuilder();
        for (byte b : bytes) result.append(String.format(java.util.Locale.ROOT, "%02x", b & 255));
        return result.toString();
    }
    static byte[] read(InputStream in) throws IOException {
        try (InputStream source = in; ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[65536]; int count;
            while ((count = source.read(buffer)) != -1) out.write(buffer, 0, count);
            return out.toByteArray();
        }
    }
    static File target(Context context, String name) throws Exception {
        File root;
        String relative;
        if (name.startsWith("private/data/")) {
            root = new File(context.getFilesDir(), "data"); relative = name.substring(13);
        } else if (name.startsWith("external/assets/Video/")) {
            File external = context.getExternalFilesDir(null);
            if (external == null) throw new IOException("视频存储暂不可用");
            root = new File(external, "assets/Video"); relative = name.substring(22);
        } else throw new IOException("Unknown resource destination");
        File file = new File(root, relative).getCanonicalFile();
        if (!file.getPath().startsWith(root.getCanonicalPath() + File.separator)) throw new IOException("Invalid resource path");
        return file;
    }
    private static void extract(Context context, InputStream source, Map<String, JSONObject> expected, Progress progress, BytesProgress bytes) throws Exception {
        int done = 0, total = expected.size();
        try (ZipInputStream zip = new ZipInputStream(source)) {
            ZipEntry entry; byte[] buffer = new byte[131072];
            while ((entry = zip.getNextEntry()) != null) {
                JSONObject item = expected.remove(entry.getName());
                if (item == null) throw new IOException("资源包不匹配");
                File file = target(context, entry.getName());
                file.getParentFile().mkdirs();
                File part = new File(file.getPath() + ".part");
                MessageDigest digest = MessageDigest.getInstance("SHA-256"); long size = 0;
                try (FileOutputStream out = new FileOutputStream(part)) {
                    int count;
                    while ((count = zip.read(buffer)) != -1) {
                        out.write(buffer, 0, count); digest.update(buffer, 0, count); size += count;
                        bytes.add(count);
                    }
                    out.getFD().sync();
                }
                if (size != item.getLong("size") || !hex(digest.digest()).equals(item.getString("sha256"))) throw new IOException("Resource verification failed");
                Os.rename(part.getPath(), file.getPath());
                done++;
                if (done % 30 == 0 || done == total) progress.update("正在解压离线资源 " + done + "/" + total + "，请稍候……");
            }
        }
        if (!expected.isEmpty()) throw new IOException("Missing resources");
    }
    static boolean verified(File file, JSONObject item) throws Exception { return verified(file, item, null); }
    private static boolean verified(File file, JSONObject item, BytesProgress bytes) throws Exception {
        if (!file.isFile() || file.length() != item.getLong("size")) return false;
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (InputStream in = new FileInputStream(file)) {
            byte[] buffer = new byte[131072]; int count;
            while ((count = in.read(buffer)) != -1) { digest.update(buffer, 0, count); if (bytes != null) bytes.add(count); }
        }
        return hex(digest.digest()).equals(item.getString("sha256"));
    }
    /** Validate the entire selected pack before replacing any installed video. */
    static void verifyPack(InputStream source, Map<String, JSONObject> manifest) throws Exception {
        verifyPack(source, manifest, text -> { });
    }
    static void verifyPack(InputStream source, Map<String, JSONObject> manifest, Progress progress) throws Exception {
        Map<String, JSONObject> remaining = new HashMap<>(manifest);
        BytesProgress bytes = new BytesProgress(progress, "verify", totalBytes(manifest));
        try (ZipInputStream zip = new ZipInputStream(source)) {
            ZipEntry entry; byte[] buffer = new byte[131072];
            while ((entry = zip.getNextEntry()) != null) {
                JSONObject item = remaining.remove(entry.getName());
                if (item == null) throw new IOException("所选资源包不匹配，请选择配套视频 ZIP");
                MessageDigest digest = MessageDigest.getInstance("SHA-256"); long size = 0; int count;
                while ((count = zip.read(buffer)) != -1) {
                    size += count;
                    if (size > item.getLong("size")) throw new IOException("资源文件大小不匹配");
                    digest.update(buffer, 0, count);
                    bytes.add(count);
                }
                if (size != item.getLong("size") || !hex(digest.digest()).equals(item.getString("sha256")))
                    throw new IOException("资源包校验失败，现有资源保持不变");
            }
        }
        if (!remaining.isEmpty()) throw new IOException("资源包缺少文件");
        bytes.finish();
    }
    static synchronized void prepare(Context context, android.net.Uri videoSource, Progress progress) throws Exception {
        byte[] raw = read(context.getAssets().open("client-resources.json"));
        String version = hash(raw);
        JSONArray entries = new JSONObject(new String(raw, "UTF-8")).getJSONArray("entries");
        File receipt = new File(context.getFilesDir(), "embedded-resources.ready");
        boolean complete = receipt.isFile() && new String(read(new FileInputStream(receipt)), "UTF-8").equals(version);
        Map<String, JSONObject> expected = new HashMap<>(), videos = new HashMap<>();
        for (int i = 0; i < entries.length(); i++) {
            JSONObject item = entries.getJSONObject(i);
            File file = target(context, item.getString("path"));
            if (!file.isFile() || file.length() != item.getLong("size")) complete = false;
            (item.optString("pack", "main").equals("video") ? videos : expected).put(item.getString("path"), item);
        }
        long extractBytes = (videoSource != null ? totalBytes(videos) : 0) + (!complete ? totalBytes(expected) : 0);
        BytesProgress extractProgress = null;
        if (videoSource != null) {
            progress.update("正在校验所选资源包，请稍候……");
            verifyPack(context.getContentResolver().openInputStream(videoSource), videos, progress);
            extractProgress = new BytesProgress(progress, "extract", extractBytes);
            extract(context, context.getContentResolver().openInputStream(videoSource), new HashMap<>(videos), progress, extractProgress);
        }
        if (!complete) {
            boolean videosReady = videoSource != null;
            if (!videosReady) {
                progress.update("正在核对离线视频……");
                BytesProgress verifyProgress = new BytesProgress(progress, "verify", totalBytes(videos));
                videosReady = true;
                for (Map.Entry<String, JSONObject> item : videos.entrySet()) {
                    if (!verified(target(context, item.getKey()), item.getValue(), verifyProgress)) { videosReady = false; break; }
                }
                if (videosReady) verifyProgress.finish();
            }
            if (!videosReady) {
                throw new VideoRequired();
            }
            if (extractProgress == null) extractProgress = new BytesProgress(progress, "extract", extractBytes);
            extract(context, context.getAssets().open("client-resources.zip"), expected, progress, extractProgress);
            File part = new File(receipt.getPath() + ".part");
            try (FileOutputStream out = new FileOutputStream(part)) { out.write(version.getBytes("UTF-8")); out.getFD().sync(); }
            Os.rename(part.getPath(), receipt.getPath());
        } else if (videoSource == null) {
            progress.skipped("verify");
        }
        if (extractProgress == null) progress.skipped("extract"); else extractProgress.finish();
        // Native custom paths are ./data//bh3-server19-*, with identical ELF layout.
        NativePaths.enter(context.getFilesDir().getAbsolutePath());
    }
}
