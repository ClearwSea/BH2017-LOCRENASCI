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
    interface Progress { void update(String text); }
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
    static void extract(Context context, InputStream source, Map<String, JSONObject> expected, Progress progress) throws Exception {
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
                    }
                    out.getFD().sync();
                }
                if (size != item.getLong("size") || !hex(digest.digest()).equals(item.getString("sha256"))) throw new IOException("Resource verification failed");
                Os.rename(part.getPath(), file.getPath());
                done++;
                if (done % 30 == 0 || done == total) progress.update("首次准备离线资源 " + done + "/" + total + "，请稍候……");
            }
        }
        if (!expected.isEmpty()) throw new IOException("Missing resources");
    }
    static boolean verified(File file, JSONObject item) throws Exception {
        if (!file.isFile() || file.length() != item.getLong("size")) return false;
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (InputStream in = new FileInputStream(file)) {
            byte[] buffer = new byte[131072]; int count;
            while ((count = in.read(buffer)) != -1) digest.update(buffer, 0, count);
        }
        return hex(digest.digest()).equals(item.getString("sha256"));
    }
    /** Validate the entire selected pack before replacing any installed video. */
    static void verifyPack(InputStream source, Map<String, JSONObject> manifest) throws Exception {
        Map<String, JSONObject> remaining = new HashMap<>(manifest);
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
                }
                if (size != item.getLong("size") || !hex(digest.digest()).equals(item.getString("sha256")))
                    throw new IOException("资源包校验失败，现有资源保持不变");
            }
        }
        if (!remaining.isEmpty()) throw new IOException("资源包缺少文件");
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
        if (videoSource != null) {
            progress.update("正在校验所选资源包，请稍候……");
            verifyPack(context.getContentResolver().openInputStream(videoSource), videos);
            extract(context, context.getContentResolver().openInputStream(videoSource), new HashMap<>(videos), progress);
        }
        if (!complete) {
            boolean videosReady = videoSource != null;
            progress.update("正在核对离线视频……");
            if (!videosReady) {
                videosReady = true;
                for (Map.Entry<String, JSONObject> item : videos.entrySet()) {
                    if (!verified(target(context, item.getKey()), item.getValue())) { videosReady = false; break; }
                }
            }
            if (!videosReady) {
                throw new VideoRequired();
            }
            extract(context, context.getAssets().open("client-resources.zip"), expected, progress);
            File part = new File(receipt.getPath() + ".part");
            try (FileOutputStream out = new FileOutputStream(part)) { out.write(version.getBytes("UTF-8")); out.getFD().sync(); }
            Os.rename(part.getPath(), receipt.getPath());
        }
        // Native custom paths are ./data//bh3-server19-*, with identical ELF layout.
        NativePaths.enter(context.getFilesDir().getAbsolutePath());
    }
}
