package local.bh3.server19probe;

import android.system.Os;
import java.io.*;
import java.security.MessageDigest;
import java.util.UUID;
import org.json.JSONObject;

/** Staged user choices and recoverable save replacement / 选择暂存与可恢复换档。 */
final class LauncherStore {
    private static final Object LOCK = new Object();
    private final File root;
    LauncherStore(File root) { this.root = root; }
    File account() { return new File(root, "formal-data/account.json"); }
    private File receipt() { return new File(root, "formal-import.json"); }
    private File journal() { return new File(root, "launcher-save-import.json"); }
    JSONObject choices() throws Exception {
        File file = new File(root, "launcher-selection.json");
        return file.isFile() ? new JSONObject(new String(read(file), "UTF-8")) : new JSONObject();
    }
    void saveChoices(JSONObject value) throws Exception {
        write(new File(root, "launcher-selection.json"), value.toString().getBytes("UTF-8"));
    }
    void updateChoices(JSONObject patch) throws Exception {
        synchronized (LOCK) {
            JSONObject selected = choices();
            java.util.Iterator<String> names = patch.keys();
            while (names.hasNext()) { String name = names.next(); selected.put(name, patch.get(name)); }
            saveChoices(selected);
        }
    }
    void resourcePrepared(String expectedUri) throws Exception {
        synchronized (LOCK) {
            JSONObject selected = choices();
            if (selected.optString("resource_uri").equals(expectedUri)) {
                selected.put("resource_pending", false); saveChoices(selected);
            }
        }
    }
    static byte[] read(File file) throws Exception {
        if (file.length() > 16 * 1024 * 1024) throw new IOException("存档或选择记录过大");
        try (InputStream in = new FileInputStream(file); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[65536]; int count;
            while ((count = in.read(buffer)) != -1) {
                if (out.size() + count > 16 * 1024 * 1024) throw new IOException("存档过大");
                out.write(buffer, 0, count);
            }
            return out.toByteArray();
        }
    }
    static String hash(byte[] raw) throws Exception {
        byte[] digest = MessageDigest.getInstance("SHA-256").digest(raw);
        StringBuilder text = new StringBuilder();
        for (byte b : digest) text.append(String.format(java.util.Locale.ROOT, "%02x", b & 255));
        return text.toString();
    }
    private static void write(File target, byte[] raw) throws Exception {
        target.getParentFile().mkdirs();
        File part = new File(target.getPath() + ".part");
        try (FileOutputStream out = new FileOutputStream(part)) { out.write(raw); out.getFD().sync(); }
        Os.rename(part.getPath(), target.getPath());
    }
    private File own(String relative) throws Exception {
        File file = new File(root, relative).getCanonicalFile();
        if (!file.getPath().startsWith(root.getCanonicalPath() + File.separator)) throw new IOException("存档暂存路径无效");
        return file;
    }
    static JSONObject validateAccount(byte[] raw) throws Exception {
        JSONObject account = new JSONObject(new String(raw, "UTF-8"));
        Object schema = account.get("schema"), uid = account.get("uid");
        if (!(schema instanceof Integer || schema instanceof Long) || ((Number)schema).longValue() != 1
                || !(uid instanceof Integer || uid instanceof Long) || ((Number)uid).longValue() <= 0
                || ((Number)uid).longValue() > 0xffffffffL) throw new IOException("存档格式不匹配");
        account.getJSONObject("main");
        for (String name : new String[]{"avatar_list", "weapon_list", "stigmata_list", "material_list", "stage_list"}) account.getJSONArray(name);
        return account;
    }
    void stageSave(byte[] raw, String name, String path) throws Exception {
        validateAccount(raw);
        String staged = "launcher-staging/" + UUID.randomUUID() + ".json";
        write(own(staged), raw);
        JSONObject selected = new JSONObject();
        selected.put("save_stage", staged).put("save_sha256", hash(raw));
        selected.put("save_name", name).put("save_path", path);
        updateChoices(selected);
    }
    boolean pendingSave() throws Exception { return !choices().optString("save_stage").isEmpty(); }
    byte[] currentSave() throws Exception {
        synchronized (LOCK) {
            byte[] raw = read(account()); validateAccount(raw); return raw;
        }
    }
    private void cleanRecovery() throws Exception {
        File parent = own("launcher-save-recovery");
        File[] folders = parent.listFiles(); if (folders == null) return;
        for (File folder : folders) {
            if (!folder.isDirectory() || !folder.getCanonicalPath().startsWith(parent.getCanonicalPath() + File.separator))
                throw new IOException("临时恢复目录异常，请保留现场");
            File[] files = folder.listFiles(); if (files == null) throw new IOException("无法读取临时恢复目录");
            for (File file : files) {
                String name = file.getName();
                if (!(name.equals("account.json") || name.equals("formal-import.json")
                        || name.equals("account.json.part") || name.equals("formal-import.json.part"))
                        || !file.isFile() || !file.delete()) throw new IOException("无法清理临时恢复文件");
            }
            if (!folder.delete()) throw new IOException("无法清理临时恢复目录");
        }
    }
    private void cleanConsumedStage() throws Exception {
        JSONObject selected = choices(); String staged = selected.optString("cleanup_stage");
        if (staged.isEmpty()) return;
        File file = own(staged);
        if (!file.getParentFile().equals(own("launcher-staging")) || staged.equals(selected.optString("save_stage")))
            throw new IOException("暂存清理记录异常，请保留现场");
        if (file.exists() && (!file.isFile() || !file.delete())) throw new IOException("无法清理已导入的临时存档");
        selected.remove("cleanup_stage"); saveChoices(selected);
    }
    private void finish(JSONObject transaction) throws Exception {
        JSONObject selected = choices();
        if (selected.optString("save_stage").equals(transaction.getString("stage"))) {
            selected.remove("save_stage"); selected.remove("save_sha256");
        }
        if (!transaction.optString("retained_backup").isEmpty())
            selected.put("last_backup_path", transaction.getString("retained_backup"));
        selected.put("cleanup_stage", transaction.getString("stage")); saveChoices(selected);
        if (!journal().delete()) throw new IOException("存档导入确认尚未完成，请重试");
        cleanConsumedStage(); cleanRecovery();
    }
    /** A complete pair is committed; an interrupted pair restores the backups. */
    void recover() throws Exception {
        synchronized (LOCK) { recoverLocked(); }
    }
    private void recoverLocked() throws Exception {
        if (!journal().isFile()) { cleanConsumedStage(); cleanRecovery(); return; }
        JSONObject transaction = new JSONObject(new String(read(journal()), "UTF-8"));
        if (account().isFile() && receipt().isFile()
                && hash(read(account())).equals(transaction.getString("account_sha256"))
                && hash(read(receipt())).equals(transaction.getString("receipt_sha256"))) {
            finish(transaction); return;
        }
        File backup = own(transaction.getString("backup"));
        restore(account(), new File(backup, "account.json"), transaction.getBoolean("had_account"));
        restore(receipt(), new File(backup, "formal-import.json"), transaction.getBoolean("had_receipt"));
        if (!journal().delete()) throw new IOException("存档恢复确认失败，请保留现场");
        cleanRecovery();
    }
    private static void restore(File target, File backup, boolean existed) throws Exception {
        if (existed) write(target, read(backup));
        else if (target.exists() && !target.delete()) throw new IOException("无法恢复导入前状态");
    }
    void commitPendingSave(boolean keepBackup, File backupRoot) throws Exception {
        synchronized (LOCK) { commitPendingSaveLocked(keepBackup, backupRoot); }
    }
    private void commitPendingSaveLocked(boolean keepBackup, File backupRoot) throws Exception {
        recover();
        JSONObject selected = choices(); String staged = selected.optString("save_stage");
        if (staged.isEmpty()) return;
        byte[] raw = read(own(staged)); JSONObject value = validateAccount(raw);
        if (!hash(raw).equals(selected.getString("save_sha256"))) throw new IOException("待导入存档已改变，请重新选择");
        JSONObject imported = new JSONObject();
        imported.put("uid", value.getLong("uid")).put("source", "user-document-picker");
        imported.put("source_name", selected.optString("save_name")).put("source_path", selected.optString("save_path"));
        imported.put("sha256", hash(raw)).put("imported_at", System.currentTimeMillis());
        byte[] receiptRaw = imported.toString().getBytes("UTF-8");
        String stamp = new java.text.SimpleDateFormat("yyyyMMdd-HHmmss", java.util.Locale.ROOT).format(new java.util.Date()) + "-" + UUID.randomUUID();
        String backupName = "launcher-save-recovery/" + stamp;
        File backup = own(backupName); backup.mkdirs();
        boolean hadAccount = account().isFile(), hadReceipt = receipt().isFile();
        if (hadAccount) write(new File(backup, "account.json"), read(account()));
        if (hadReceipt) write(new File(backup, "formal-import.json"), read(receipt()));
        String retained = "";
        if (keepBackup && hadAccount) {
            if (backupRoot == null) throw new IOException("备份位置不可用，未替换存档");
            File kept = new File(backupRoot, stamp);
            write(new File(kept, "account.json"), read(new File(backup, "account.json")));
            if (hadReceipt) write(new File(kept, "formal-import.json"), read(new File(backup, "formal-import.json")));
            retained = new File(kept, "account.json").getAbsolutePath();
        }
        JSONObject transaction = new JSONObject();
        transaction.put("retained_backup", retained);
        transaction.put("backup", backupName).put("stage", staged);
        transaction.put("had_account", hadAccount).put("had_receipt", hadReceipt);
        transaction.put("account_sha256", hash(raw)).put("receipt_sha256", hash(receiptRaw));
        write(journal(), transaction.toString().getBytes("UTF-8"));
        try {
            write(account(), raw); write(receipt(), receiptRaw); finish(transaction);
        } catch (Exception failure) {
            recover();
            if (account().isFile() && receipt().isFile() && hash(read(account())).equals(hash(raw))
                    && hash(read(receipt())).equals(hash(receiptRaw)) && !pendingSave()) return;
            throw failure;
        }
    }
}
