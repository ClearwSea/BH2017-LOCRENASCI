package local.bh3.server19probe;

import android.system.Os;
import java.io.*;
import java.security.MessageDigest;
import java.util.UUID;
import org.json.JSONArray;
import org.json.JSONObject;

/** Staged user choices and recoverable save replacement / 选择暂存与可恢复换档。 */
final class LauncherStore {
    private static final Object LOCK = new Object();
    private final File root;
    LauncherStore(File root) { this.root = root; }
    File account() { return new File(root, "formal-data/account.json"); }
    private File receipt() { return new File(root, "formal-import.json"); }
    private File journal() { return new File(root, "launcher-save-import.json"); }
    private File editorJournal() { return new File(root, "launcher-editor-selection.json"); }
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

    /** The selected document may still be staged and must not be imported by the editor. */
    private byte[] editorSelected() throws Exception {
        JSONObject selected = choices(); String staged = selected.optString("save_stage");
        if (!staged.isEmpty()) {
            File source = own(staged);
            if (!source.getParentFile().equals(own("launcher-staging"))) throw new IOException("存档暂存路径无效");
            byte[] raw = read(source); validateAccount(raw);
            if (!hash(raw).equals(selected.getString("save_sha256"))) throw new IOException("所选存档已改变，请重新选择");
            return raw;
        }
        byte[] raw = currentSave(); JSONObject value = validateAccount(raw);
        if (!receipt().isFile() || new JSONObject(new String(read(receipt()), "UTF-8")).getLong("uid") != value.getLong("uid"))
            throw new IOException("当前存档身份与导入记录不符");
        return raw;
    }

    private File editorAutoRoot(File backupRoot, boolean create) throws Exception {
        if (backupRoot == null) throw new IOException("备份位置不可用");
        File automatic = new File(backupRoot, "auto");
        if (create && !automatic.isDirectory() && !automatic.mkdirs()) throw new IOException("无法创建自动备份目录");
        if (!backupRoot.getCanonicalFile().equals(automatic.getCanonicalFile().getParentFile()) ||
                !"auto".equals(automatic.getCanonicalFile().getName())) throw new IOException("自动备份目录无效");
        return automatic;
    }

    /** Discover only app-generated backups; an absent directory means no history. */
    JSONArray editorSources(File backupRoot) throws Exception {
        synchronized (LOCK) {
            JSONArray list = new JSONArray();
            JSONObject selected = choices();
            boolean hasSelected = !selected.optString("save_stage").isEmpty() || account().isFile();
            if (hasSelected) {
                byte[] raw = editorSelected();
                boolean pending = !selected.optString("save_stage").isEmpty();
                JSONObject account = validateAccount(raw);
                list.put(new JSONObject().put("id", "selected")
                    .put("title", pending ? "当前选择：" + selected.optString("save_name", "待导入存档") : "当前存档")
                    .put("detail", (pending ? "尚未导入" : "已导入") + "  ·  舰长 Lv."
                        + account.getJSONObject("main").optInt("level", 0) + "  ·  UID " + account.getLong("uid"))
                    .put("sha256", hash(raw)));
            }
            if (backupRoot == null) return list;
            File automatic = editorAutoRoot(backupRoot, false);
            if (!automatic.exists()) return list;
            java.util.ArrayList<File> backups = automaticBackups(automatic);
            backups.sort((left, right) -> {
                int date = Long.compare(right.lastModified(), left.lastModified());
                return date != 0 ? date : right.getName().compareTo(left.getName());
            });
            for (File backup : backups) {
                File file = new File(backup, "account.json");
                if (!file.isFile()) continue; // Interrupted backup: do not present it as a usable save.
                byte[] raw = read(file); JSONObject account = validateAccount(raw);
                String stamp = backup.getName().substring(0, 15);
                String date = stamp.substring(0, 4) + "-" + stamp.substring(4, 6) + "-" + stamp.substring(6, 8)
                    + " " + stamp.substring(9, 11) + ":" + stamp.substring(11, 13);
                File metadata = new File(backup, "metadata.json");
                boolean edited = metadata.isFile() && "editor".equals(new JSONObject(new String(read(metadata), "UTF-8")).optString("source"));
                String summary = "舰长 Lv." + account.getJSONObject("main").optInt("level", 0)
                    + "  ·  UID " + account.getLong("uid");
                list.put(new JSONObject().put("id", "history:" + backup.getName())
                    .put("title", date + "  ·  " + (edited ? "编辑前" : "历史备份"))
                    .put("detail", summary).put("path", file.getAbsolutePath()).put("sha256", hash(raw)));
            }
            return list;
        }
    }

    byte[] editorSource(String sourceId, File backupRoot) throws Exception {
        synchronized (LOCK) {
            if ("selected".equals(sourceId)) return editorSelected();
            if (!sourceId.startsWith("history:")) throw new IOException("未知存档来源");
            String name = sourceId.substring("history:".length());
            File automatic = editorAutoRoot(backupRoot, false);
            for (File folder : automaticBackups(automatic)) if (folder.getName().equals(name)) {
                byte[] raw = read(new File(folder, "account.json")); validateAccount(raw); return raw;
            }
            throw new IOException("历史备份不存在或已被轮换");
        }
    }

    static final class EditorSnapshot {
        final byte[] source;
        final String sourceHash, targetHash, targetToken;
        EditorSnapshot(byte[] source, String sourceHash, String targetHash, String targetToken) {
            this.source = source; this.sourceHash = sourceHash; this.targetHash = targetHash; this.targetToken = targetToken;
        }
    }
    private String editorTargetToken() throws Exception {
        String pending = choices().optString("save_stage");
        return !pending.isEmpty() ? "pending:" + pending : account().isFile() ? "formal" : "none";
    }
    /** Capture selection identity together with bytes while selection updates are excluded. */
    EditorSnapshot editorSnapshot(String sourceId, File backupRoot) throws Exception {
        synchronized (LOCK) {
            String token = editorTargetToken();
            byte[] target = "none".equals(token) ? null : editorSelected();
            byte[] source = sourceId == null ? null : "selected".equals(sourceId) ? target : editorSource(sourceId, backupRoot);
            if (sourceId != null && source == null) throw new IOException("当前未选择存档");
            return new EditorSnapshot(source, source == null ? "" : hash(source), target == null ? "" : hash(target), token);
        }
    }
    interface EditorAction { void run() throws Exception; }
    void withEditorLock(EditorAction action) throws Exception { synchronized (LOCK) { action.run(); } }
    void requireEditorTarget(String token, String expectedHash) throws Exception {
        synchronized (LOCK) {
            EditorSnapshot now = editorSnapshot(null, null);
            if (!now.targetToken.equals(token) || !now.targetHash.equals(expectedHash))
                throw new IOException("当前选择在编辑期间发生变化，请重新读取");
        }
    }

    /** Reserve a unique name, without creating a directory before the shared file lock is held. */
    File editorBackupTarget(File backupRoot) throws Exception {
        synchronized (LOCK) {
            File automatic = editorAutoRoot(backupRoot, true); automaticBackups(automatic);
            String stamp = new java.text.SimpleDateFormat("yyyyMMdd-HHmmss", java.util.Locale.ROOT)
                .format(new java.util.Date()) + "-" + UUID.randomUUID();
            return new File(automatic, stamp);
        }
    }

    private static boolean equivalent(Object left, Object right) throws Exception {
        if (left == right || (left == JSONObject.NULL && right == JSONObject.NULL)) return true;
        if (left instanceof JSONObject && right instanceof JSONObject) {
            JSONObject a = (JSONObject)left, b = (JSONObject)right;
            if (a.length() != b.length()) return false;
            java.util.Iterator<String> keys = a.keys();
            while (keys.hasNext()) {
                String key = keys.next();
                if (!b.has(key) || !equivalent(a.get(key), b.get(key))) return false;
            }
            return true;
        }
        if (left instanceof JSONArray && right instanceof JSONArray) {
            JSONArray a = (JSONArray)left, b = (JSONArray)right;
            if (a.length() != b.length()) return false;
            for (int i = 0; i < a.length(); i++) if (!equivalent(a.get(i), b.get(i))) return false;
            return true;
        }
        if (left instanceof Number && right instanceof Number) {
            boolean leftDecimal = left instanceof Double || left instanceof Float || left instanceof java.math.BigDecimal;
            boolean rightDecimal = right instanceof Double || right instanceof Float || right instanceof java.math.BigDecimal;
            return leftDecimal == rightDecimal &&
                new java.math.BigDecimal(left.toString()).compareTo(new java.math.BigDecimal(right.toString())) == 0;
        }
        return left != null && left.equals(right);
    }

    /** Reserve a name only if the currently selected target is not already backed up. */
    File editorBackupForTarget(File backupRoot) throws Exception {
        synchronized (LOCK) {
            if ("none".equals(editorTargetToken())) return null;
            JSONObject original = validateAccount(editorSelected());
            File automatic = editorAutoRoot(backupRoot, true);
            for (File folder : automaticBackups(automatic)) {
                File existing = new File(folder, "account.json");
                if (existing.isFile() && equivalent(original, validateAccount(read(existing)))) return null;
            }
            return editorBackupTarget(backupRoot);
        }
    }

    /** Publish only verified, complete backup directories; interrupted staging is never listed. */
    private void writeVerifiedBackup(File backupRoot, File target, byte[] account, byte[] importReceipt,
                                     boolean editor) throws Exception {
        File automatic = editorAutoRoot(backupRoot, true);
        if (!automatic.getCanonicalFile().equals(target.getCanonicalFile().getParentFile()) || target.exists())
            throw new IOException("自动备份目标无效");
        File stagingRoot = new File(backupRoot, ".editor-backup-staging");
        if (!backupRoot.getCanonicalFile().equals(stagingRoot.getCanonicalFile().getParentFile()))
            throw new IOException("自动备份暂存目录无效");
        if (!stagingRoot.isDirectory() && !stagingRoot.mkdirs()) throw new IOException("无法创建备份暂存目录");
        File staging = new File(stagingRoot, UUID.randomUUID().toString());
        if (!staging.mkdir()) throw new IOException("无法暂存自动备份");
        write(new File(staging, "account.json"), account);
        if (!java.util.Arrays.equals(account, read(new File(staging, "account.json"))))
            throw new IOException("备份校验失败，未保存");
        if (importReceipt != null) {
            write(new File(staging, "formal-import.json"), importReceipt);
            if (!java.util.Arrays.equals(importReceipt, read(new File(staging, "formal-import.json"))))
                throw new IOException("备份校验失败，未保存");
        }
        if (editor) write(new File(staging, "metadata.json"), "{\"source\":\"editor\"}".getBytes("UTF-8"));
        if (target.exists()) throw new IOException("自动备份目标已存在");
        Os.rename(staging.getPath(), target.getPath());
    }

    void editorBackupComplete(File backupRoot, File target) throws Exception {
        editorBackupComplete(backupRoot, target, null);
    }
    private void editorBackupComplete(File backupRoot, File target, File protectedHistory) throws Exception {
        synchronized (LOCK) {
            File automatic = editorAutoRoot(backupRoot, false);
            File canonical = target.getCanonicalFile();
            boolean found = false;
            for (File folder : automaticBackups(automatic))
                if (canonical.equals(folder.getCanonicalFile())) { found = true; break; }
            if (!automatic.getCanonicalFile().equals(canonical.getParentFile()) || !target.getName().equals(canonical.getName()) ||
                    !found) throw new IOException("自动备份目录无效");
            validateAccount(read(new File(canonical, "account.json")));
            File metadata = new File(canonical, "metadata.json");
            if (!metadata.isFile()) write(metadata, "{\"source\":\"editor\"}".getBytes("UTF-8"));
            trimAutomaticBackups(automatic, canonical, protectedHistory);
        }
    }

    /** Save a selected-but-not-imported document without changing the running account. */
    void saveEditedPending(String expectedHash, byte[] edited, File backupRoot) throws Exception {
        saveEditedPending(expectedHash, edited, backupRoot, true);
    }
    void saveEditedPending(String expectedHash, byte[] edited, File backupRoot, boolean backupOnce) throws Exception {
        synchronized (LOCK) {
            JSONObject selected = choices();
            if (selected.optString("save_stage").isEmpty()) throw new IOException("所选待导入存档已改变，请重新读取");
            byte[] old = editorSelected();
            if (!hash(old).equals(expectedHash)) throw new IOException("所选存档在编辑期间发生变化，请重新读取");
            JSONObject before = validateAccount(old), after = validateAccount(edited);
            if (before.getLong("uid") != after.getLong("uid")) throw new IOException("不能修改存档身份");
            File backup = backupOnce ? editorBackupForTarget(backupRoot) : null;
            if (backup != null) {
                writeVerifiedBackup(backupRoot, backup, old, null, true);
                editorBackupComplete(backupRoot, backup);
            }
            // stageSave writes a new file first, then atomically changes the selection record.
            stageSave(edited, selected.optString("save_name"), selected.optString("save_path"));
        }
    }

    /** Caller holds server19_stage's file lock when the destination is the formal account. */
    void saveEditedHistory(String sourceId, String sourceHash, String destinationHash,
                           byte[] edited, File backupRoot) throws Exception {
        saveEditedHistory(sourceId, sourceHash, destinationHash, edited, backupRoot, true);
    }
    void saveEditedHistory(String sourceId, String sourceHash, String destinationHash,
                           byte[] edited, File backupRoot, boolean backupOnce) throws Exception {
        synchronized (LOCK) {
            if (!sourceId.startsWith("history:")) throw new IOException("请选择历史备份");
            byte[] source = editorSource(sourceId, backupRoot);
            JSONObject selected = choices();
            boolean pending = !selected.optString("save_stage").isEmpty();
            boolean existing = pending || account().isFile();
            if (!existing && receipt().exists()) throw new IOException("当前存档记录不完整，请先恢复");
            byte[] destination = existing ? editorSelected() : null;
            if (!hash(source).equals(sourceHash)) throw new IOException("历史备份在编辑期间发生变化，请重新读取");
            if (existing ? !hash(destination).equals(destinationHash) : !destinationHash.isEmpty())
                throw new IOException("当前选择在编辑期间发生变化，请重新读取");
            if (validateAccount(source).getLong("uid") != validateAccount(edited).getLong("uid"))
                throw new IOException("不能修改历史存档身份");
            File protectedHistory = new File(editorAutoRoot(backupRoot, false), sourceId.substring("history:".length()));
            File backup = existing && backupOnce ? editorBackupForTarget(backupRoot) : null;
            if (pending && backup != null) {
                writeVerifiedBackup(backupRoot, backup, destination, null, true);
                editorBackupComplete(backupRoot, backup, protectedHistory);
            }
            if (existing && !pending) replaceFormalFromEditor(edited, "历史存档", backupRoot, protectedHistory, backup != null);
            else stageSave(edited, "历史存档", "应用内自动备份");
        }
    }

    /** Save a new template after verifying the original destination has not changed.
     * Caller holds server19_stage's file lock when the destination is formal. */
    void saveNewEdited(String destinationHash, byte[] edited, File backupRoot) throws Exception {
        saveNewEdited(destinationHash, edited, backupRoot, true);
    }
    void saveNewEdited(String destinationHash, byte[] edited, File backupRoot, boolean backupOnce) throws Exception {
        synchronized (LOCK) {
            validateAccount(edited);
            boolean pending = pendingSave();
            boolean existing = pending || account().isFile();
            if (!existing && receipt().exists()) throw new IOException("当前存档记录不完整，请先恢复");
            byte[] destination = existing ? editorSelected() : null;
            if (destinationHash == null || (existing ? !hash(destination).equals(destinationHash) : !destinationHash.isEmpty()))
                throw new IOException("当前选择在编辑期间发生变化，请重新读取");
            File backup = existing && backupOnce ? editorBackupForTarget(backupRoot) : null;
            if (pending && backup != null) {
                writeVerifiedBackup(backupRoot, backup, destination, null, true);
                editorBackupComplete(backupRoot, backup);
            }
            if (existing && !pending) replaceFormalFromEditor(edited, "新建存档", backupRoot, null, backup != null);
            else stageSave(edited, "新建存档", "应用内存档编辑器");
        }
    }

    /** Cover both selection staging and the existing recoverable account/receipt import. */
    private void replaceFormalFromEditor(byte[] edited, String name, File backupRoot, File protectedHistory, boolean backupOnce) throws Exception {
        if (editorJournal().exists()) throw new IOException("尚有未恢复的编辑事务");
        JSONObject saved = new JSONObject();
        saved.put("previous", choices()).put("edited_sha256", hash(edited));
        saved.put("uid", validateAccount(edited).getLong("uid"));
        write(editorJournal(), saved.toString().getBytes("UTF-8"));
        try {
            stageSave(edited, name, "应用内存档编辑器");
            commitPendingSaveLocked(backupOnce, backupRoot, protectedHistory);
            recoverEditorSelection();
        } catch (Exception error) {
            recoverLocked();
            boolean committed = recoverEditorSelection();
            if (!committed) throw error;
        }
    }

    /** Return true only when the full import finished, including selection cleanup. */
    private boolean recoverEditorSelection() throws Exception {
        if (!editorJournal().isFile()) return false;
        JSONObject transaction = new JSONObject(new String(read(editorJournal()), "UTF-8"));
        JSONObject selected = choices();
        boolean committed = selected.optString("save_stage").isEmpty() && account().isFile() && receipt().isFile()
            && hash(read(account())).equals(transaction.getString("edited_sha256"))
            && new JSONObject(new String(read(receipt()), "UTF-8")).getLong("uid") == transaction.getLong("uid");
        if (!committed) saveChoices(transaction.getJSONObject("previous"));
        if (!editorJournal().delete()) throw new IOException("无法确认编辑事务，请保留现场");
        return committed;
    }

    /** Convenience for creating the first pending save. */
    void saveNewEdited(byte[] edited) throws Exception {
        saveNewEdited("", edited, null);
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
        synchronized (LOCK) { recoverLocked(); recoverEditorSelection(); }
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
    /** Only inspect app-generated folders. Older manual backups stay outside this directory. */
    private static java.util.ArrayList<File> automaticBackups(File directory) throws IOException {
        File root = directory.getCanonicalFile();
        File[] entries = root.listFiles();
        if (entries == null) throw new IOException("无法读取自动备份目录，未替换存档");
        java.util.ArrayList<File> backups = new java.util.ArrayList<>();
        for (File entry : entries) {
            if (!entry.getName().matches("[0-9]{8}-[0-9]{6}-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")) continue;
            File canonical = entry.getCanonicalFile();
            if (!entry.isDirectory() || !root.equals(canonical.getParentFile()) || !entry.getName().equals(canonical.getName()))
                throw new IOException("自动备份目录异常，未替换存档");
            File[] contents = entry.listFiles();
            if (contents == null) throw new IOException("无法读取旧自动备份，未替换存档");
            boolean incomplete = false;
            for (File item : contents) {
                String name = item.getName(); File real = item.getCanonicalFile();
                if (!(name.equals("account.json") || name.equals("formal-import.json")
                        || name.equals("account.json.part") || name.equals("formal-import.json.part")
                        || name.equals("metadata.json") || name.equals("metadata.json.part")) || !item.isFile()
                        || !canonical.equals(real.getParentFile()) || !name.equals(real.getName()))
                    throw new IOException("旧自动备份包含未知文件，未替换存档");
                if (name.endsWith(".part")) incomplete = true;
            }
            // Incomplete older attempts are never listed, deduplicated or rotated away.
            File account = new File(entry, "account.json");
            if (incomplete || !account.isFile()) continue;
            try {
                JSONObject value = validateAccount(read(account));
                File receipt = new File(entry, "formal-import.json");
                if (receipt.isFile() && new JSONObject(new String(read(receipt), "UTF-8")).getLong("uid") != value.getLong("uid")) continue;
                File metadata = new File(entry, "metadata.json");
                if (metadata.isFile()) new JSONObject(new String(read(metadata), "UTF-8"));
            } catch (Exception invalid) { continue; }
            backups.add(entry);
        }
        return backups;
    }
    /** Keep at most ten app-generated automatic backups. */
    private static void trimAutomaticBackups(File directory, File current) throws IOException {
        trimAutomaticBackups(directory, current, null);
    }
    private static void trimAutomaticBackups(File directory, File current, File protectedHistory) throws IOException {
        java.util.ArrayList<File> backups = automaticBackups(directory);
        backups.sort((left, right) -> {
            int date = Long.compare(left.lastModified(), right.lastModified());
            return date != 0 ? date : left.getName().compareTo(right.getName());
        });
        int remove = backups.size() - 10;
        for (File backup : backups) {
            if (remove <= 0) break;
            if (backup.getCanonicalFile().equals(current.getCanonicalFile())) continue;
            if (protectedHistory != null && backup.getCanonicalFile().equals(protectedHistory.getCanonicalFile())) continue;
            File[] contents = backup.listFiles();
            if (contents == null) throw new IOException("无法读取旧自动备份，未替换存档");
            for (File item : contents) {
                String name = item.getName(); File real = item.getCanonicalFile();
                if (!(name.equals("account.json") || name.equals("formal-import.json")
                        || name.equals("account.json.part") || name.equals("formal-import.json.part")
                        || name.equals("metadata.json") || name.equals("metadata.json.part")) || !item.isFile()
                        || !backup.getCanonicalFile().equals(real.getParentFile()) || !name.equals(real.getName()))
                    throw new IOException("旧自动备份包含未知文件，未替换存档");
            }
            for (File item : contents) if (!item.delete()) throw new IOException("无法轮换旧自动备份，未替换存档");
            if (!backup.delete()) throw new IOException("无法轮换旧自动备份，未替换存档");
            remove--;
        }
        if (remove > 0) throw new IOException("无法保留最近的自动备份，未替换存档");
    }
    void commitPendingSave(boolean keepBackup, File backupRoot) throws Exception {
        commitPendingSave(keepBackup, backupRoot, null);
    }
    private void commitPendingSave(boolean keepBackup, File backupRoot, File protectedHistory) throws Exception {
        synchronized (LOCK) { commitPendingSaveLocked(keepBackup, backupRoot, protectedHistory); }
    }
    private void commitPendingSaveLocked(boolean keepBackup, File backupRoot, File protectedHistory) throws Exception {
        recoverLocked();
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
            File automatic = new File(backupRoot, "auto");
            if (!automatic.isDirectory() && !automatic.mkdirs()) throw new IOException("无法创建自动备份目录，未替换存档");
            if (!backupRoot.getCanonicalFile().equals(automatic.getCanonicalFile().getParentFile())
                    || !"auto".equals(automatic.getCanonicalFile().getName()))
                throw new IOException("自动备份目录无效，未替换存档");
            automaticBackups(automatic);
            File kept = new File(automatic, stamp);
            byte[] previousAccount = read(new File(backup, "account.json"));
            byte[] previousReceipt = hadReceipt ? read(new File(backup, "formal-import.json")) : null;
            writeVerifiedBackup(backupRoot, kept, previousAccount, previousReceipt, editorJournal().isFile());
            trimAutomaticBackups(automatic, kept, protectedHistory);
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
