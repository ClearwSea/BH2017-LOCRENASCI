package local.bh3.server19probe;

import android.system.Os;
import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.zip.*;
import org.json.JSONObject;

/** Exercises the production storage/pack logic on isolated host fixtures. */
public final class LauncherStoreCheck {
    static byte[] account(int uid) throws Exception {
        return ("{\"schema\":1,\"uid\":" + uid + ",\"main\":{},\"avatar_list\":[],\"weapon_list\":[],"
                + "\"stigmata_list\":[],\"material_list\":[],\"stage_list\":[]}").getBytes("UTF-8");
    }
    static void check(boolean condition, String message) { if (!condition) throw new AssertionError(message); }
    static void installOld(File root) throws Exception {
        File account = new File(root, "formal-data/account.json"); account.getParentFile().mkdirs();
        Files.write(account.toPath(), account(1)); Files.write(new File(root, "formal-import.json").toPath(), "{\"uid\":1}".getBytes("UTF-8"));
    }
    static int uid(File file) throws Exception { return new JSONObject(new String(LauncherStore.read(file), "UTF-8")).getInt("uid"); }
    static void pair(File root, boolean oldAllowed) throws Exception {
        File account = new File(root, "formal-data/account.json"), receipt = new File(root, "formal-import.json");
        if (!account.exists()) { check(oldAllowed && !receipt.exists(), "partial first import"); return; }
        check(receipt.exists(), "missing receipt"); int accountUid = uid(account), receiptUid = uid(receipt);
        check(accountUid == receiptUid, "mixed account and receipt");
        check(accountUid == 2 || oldAllowed && accountUid == 1, "unexpected account");
    }
    static int commit(File root, boolean existing, boolean keep) throws Exception {
        if (existing) installOld(root);
        LauncherStore store = new LauncherStore(root); store.stageSave(account(2), "new-save.json", "…/Download/new-save.json");
        store.updateChoices(new JSONObject().put("last_export_name", "export.json"));
        check(store.pendingSave() && store.choices().optString("save_name").equals("new-save.json"), "export record lost pending selection");
        store.updateChoices(new JSONObject().put("resource_uri", "content://new").put("resource_pending", true));
        store.resourcePrepared("content://old");
        check(store.choices().optBoolean("resource_pending"), "old preparation cleared a new selection");
        if (existing) check(uid(store.account()) == 1, "selection mutated live account");
        else check(!store.account().exists(), "selection imported automatically");
        if (existing) check(Arrays.equals(store.currentSave(), account(1)), "export selected staged account instead of current account");
        Os.calls = 0; store.commitPendingSave(keep, new File(root, "retained")); int count = Os.calls;
        pair(root, false); check(!store.pendingSave(), "pending marker retained");
        check(new File(root, "launcher-staging").listFiles().length == 0, "consumed staged copy retained");
        File[] temporary = new File(root, "launcher-save-recovery").listFiles();
        check(temporary == null || temporary.length == 0, "temporary backup retained after successful import");
        if (existing && keep) {
            File[] backups = new File(root, "retained").listFiles();
            check(backups != null && backups.length == 1, "missing backup");
            check(Arrays.equals(LauncherStore.read(new File(backups[0], "account.json")), account(1)), "backup changed");
            check(!store.choices().optString("last_backup_path").isEmpty(), "backup location not recorded");
        } else {
            check(!new File(root, "retained").exists(), "unrequested retained backup");
        }
        check(Arrays.equals(store.currentSave(), account(2)), "export does not reflect current committed save");
        return count;
    }
    static byte[] zip(String... entries) throws Exception {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ZipOutputStream out = new ZipOutputStream(bytes)) {
            for (String name : entries) { out.putNextEntry(new ZipEntry(name)); out.write(new byte[]{1,2,3}); out.closeEntry(); }
        }
        return bytes.toByteArray();
    }
    public static void main(String[] args) throws Exception {
        File base = new File(args[0]); if (!base.mkdir()) throw new IOException("fresh output required");
        int recovered = 0;
        for (int mode = 0; mode < 3; mode++) {
            boolean existing = mode != 0, keep = mode == 2;
            File successful = new File(base, "success-" + mode); successful.mkdir();
            int steps = commit(successful, existing, keep);
            for (int stop = 1; stop <= steps; stop++) {
                File root = new File(base, "crash-" + mode + "-" + stop); root.mkdir();
                if (existing) installOld(root);
                LauncherStore store = new LauncherStore(root); store.stageSave(account(2), "new.json", "…/new.json");
                Os.calls = 0; Os.crashAfter = stop;
                try { store.commitPendingSave(keep, new File(root, "retained")); throw new AssertionError("interruption did not fire"); }
                catch (Os.Interrupted expected) { }
                finally { Os.crashAfter = 0; }
                store.recover(); pair(root, true);
                check(!new File(root, "launcher-save-import.json").exists(), "journal not resolved");
                store.recover(); pair(root, true);
                if (!store.pendingSave()) check(new File(root, "launcher-staging").listFiles().length == 0, "consumed stage retained after recovery");
                File[] leftovers = new File(root, "launcher-save-recovery").listFiles();
                check(leftovers == null || leftovers.length == 0, "temporary recovery files retained");
                if (!keep) check(!new File(root, "retained").exists(), "unrequested permanent backup on recovery");
                recovered++;
            }
        }
        File unavailable = new File(base, "unavailable-backup"); unavailable.mkdir(); installOld(unavailable);
        LauncherStore unavailableStore = new LauncherStore(unavailable); unavailableStore.stageSave(account(2), "new.json", "…/new.json");
        boolean backupRejected = false;
        try { unavailableStore.commitPendingSave(true, null); } catch (IOException expected) { backupRejected = true; }
        check(backupRejected && uid(unavailableStore.account()) == 1, "unavailable backup changed source");
        unavailableStore.recover();
        check(new File(unavailable, "launcher-save-recovery").listFiles().length == 0, "failed backup left recovery files");
        File failed = new File(base, "failed"); failed.mkdir(); installOld(failed);
        LauncherStore store = new LauncherStore(failed); store.stageSave(account(2), "new.json", "…/new.json");
        Os.failReceipt = true; Os.failReceiptTarget = new File(failed, "formal-import.json").getPath();
        try { store.commitPendingSave(false, null); throw new AssertionError("failure not returned"); }
        catch (IOException expected) { }
        check(uid(store.account()) == 1 && uid(new File(failed, "formal-import.json")) == 1, "failed replacement changed progress");
        check(store.pendingSave(), "failed replacement lost staged choice");
        String prior = store.choices().toString();
        for (byte[] invalid : new byte[][]{"bad".getBytes("UTF-8"), "{\"schema\":1,\"uid\":\"2\"}".getBytes("UTF-8"), "{\"schema\":1,\"uid\":2}".getBytes("UTF-8")}) {
            boolean rejected = false; try { store.stageSave(invalid, "bad.json", "…/bad.json"); } catch (Exception expected) { rejected = true; }
            check(rejected && prior.equals(store.choices().toString()), "bad selection replaced prior choice");
        }
        JSONObject choices = store.choices();
        Files.write(new File(failed, choices.getString("save_stage")).toPath(), account(3));
        boolean rejected = false; try { store.commitPendingSave(false, null); } catch (IOException expected) { rejected = true; }
        check(rejected && uid(store.account()) == 1, "tampered staged save accepted");
        Map<String, JSONObject> manifest = new HashMap<>();
        manifest.put("video", new JSONObject().put("size",3).put("sha256", LauncherStore.hash(new byte[]{1,2,3})));
        EmbeddedResources.verifyPack(new ByteArrayInputStream(zip("video")), manifest);
        int invalidPacks = 0;
        for (byte[] invalid : new byte[][]{zip(), zip("other"), zip("video", "extra"), "not a zip".getBytes("UTF-8")}) {
            rejected = false; try { EmbeddedResources.verifyPack(new ByteArrayInputStream(invalid), manifest); } catch (Exception expected) { rejected = true; }
            check(rejected, "invalid pack accepted"); invalidPacks++;
        }
        manifest.get("video").put("size", 2);
        rejected = false; try { EmbeddedResources.verifyPack(new ByteArrayInputStream(zip("video")), manifest); } catch (Exception expected) { rejected = true; }
        check(rejected, "oversized resource accepted"); invalidPacks++;
        manifest.get("video").put("size", 3).put("sha256", "bad");
        rejected = false; try { EmbeddedResources.verifyPack(new ByteArrayInputStream(zip("video")), manifest); } catch (Exception expected) { rejected = true; }
        check(rejected, "bad resource hash accepted"); invalidPacks++;
        System.out.println("PASS: optional retained backups, current-save snapshots, first/replacement imports, " + recovered + " interrupted rename recoveries, failed receipt rollback, invalid/tampered saves, " + invalidPacks + " invalid resource packs");
    }
}
