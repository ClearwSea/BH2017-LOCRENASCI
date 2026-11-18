package local.bh3.server19probe;

import android.system.Os;
import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.zip.*;
import org.json.JSONObject;
import org.json.JSONArray;

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
            File[] backups = new File(root, "retained/auto").listFiles();
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
    static File oldAutoBackup(File folder, int index, boolean extra) throws Exception {
        File auto = new File(folder, "auto"); auto.mkdirs();
        File entry = new File(auto, String.format(java.util.Locale.ROOT,
            "20200101-%06d-00000000-0000-0000-0000-%012d", index, index));
        if (!entry.mkdir()) throw new IOException("cannot create automatic backup fixture");
        Files.write(new File(entry, "account.json").toPath(), account(index + 10));
        if (extra) Files.write(new File(entry, "unknown.txt").toPath(), new byte[]{1});
        if (!entry.setLastModified(1000000L + index * 1000L)) throw new IOException("cannot order fixtures");
        return entry;
    }
    static void checkAutomaticRotation(File base) throws Exception {
        File root=new File(base, "rotation");root.mkdir();installOld(root);
        File saved=new File(root, "retained");File manual=new File(saved,"manual-backup.json");saved.mkdirs();
        Files.write(manual.toPath(), account(99));
        File oldest=null;for(int i=0;i<10;i++){File entry=oldAutoBackup(saved,i,false);if(i==0)oldest=entry;}
        Files.write(new File(oldest,"formal-import.json.part").toPath(),new byte[]{1});
        if (!oldest.setLastModified(1000000L)) throw new IOException("cannot order partial fixture");
        LauncherStore store=new LauncherStore(root);store.stageSave(account(2),"new.json","…/new.json");
        store.commitPendingSave(true,saved);
        File[] left=new File(saved,"auto").listFiles();
        check(left!=null && left.length==11,"incomplete prior backup was removed or rotation miscounted");
        check(oldest.exists(),"incomplete prior backup must be preserved");
        check(manual.isFile() && uid(manual)==99,"manual backup changed");
        String retained=store.choices().getString("last_backup_path");
        check(uid(new File(retained))==1,"new automatic backup did not preserve old account");
        check(uid(store.account())==2,"new account not imported after backup");

        File failure=new File(base,"rotation-failure");failure.mkdir();installOld(failure);
        File failedRoot=new File(failure,"retained");
        for(int i=0;i<10;i++)oldAutoBackup(failedRoot,i,i==0);
        LauncherStore failed=new LauncherStore(failure);failed.stageSave(account(2),"new.json","…/new.json");
        boolean rejected=false;
        try{failed.commitPendingSave(true,failedRoot);}catch(IOException expected){rejected=true;}
        check(rejected && uid(failed.account())==1 && failed.pendingSave(),"unsafe rotation replaced current save");
        check(new File(failedRoot,"auto").listFiles().length==10,"unknown backup was deleted or a new backup was added");
    }

    static void checkEditorSourcesAndHistory(File base) throws Exception {
        File root = new File(base, "editor-sources"); root.mkdir(); installOld(root);
        File saved = new File(root, "retained");
        File oldest = null;
        for (int i = 0; i < 10; i++) { File folder = oldAutoBackup(saved, i, false); if (i == 0) oldest = folder; }
        LauncherStore store = new LauncherStore(root);
        JSONArray sources = store.editorSources(saved);
        check(sources.length() == 11 && sources.getJSONObject(0).getString("id").equals("selected"), "incorrect source list");
        String history = "history:" + oldest.getName();
        byte[] historyRaw = store.editorSource(history, saved);
        String historyHash = LauncherStore.hash(historyRaw);
        String selectedHash = LauncherStore.hash(store.editorSource("selected", saved));
        JSONObject editedValue = new JSONObject(new String(historyRaw, "UTF-8"));
        editedValue.getJSONObject("main").put("scoin", 123);
        byte[] edited = editedValue.toString().getBytes("UTF-8");
        boolean rejected = false;
        try { store.saveEditedHistory(history, "bad", selectedHash, edited, saved); }
        catch (IOException expected) { rejected = true; }
        check(rejected && uid(store.account()) == 1, "changed history accepted");
        rejected = false;
        try { store.saveEditedHistory(history, historyHash, "bad", edited, saved); }
        catch (IOException expected) { rejected = true; }
        check(rejected && uid(store.account()) == 1, "changed destination accepted");
        store.saveEditedHistory(history, historyHash, selectedHash, edited, saved);
        check(Arrays.equals(LauncherStore.read(store.account()), edited), "history not applied to formal account");
        check(uid(new File(root, "formal-import.json")) == 10, "history identity/receipt mismatch");
        check(oldest.isDirectory() && Arrays.equals(historyRaw, store.editorSource(history, saved)), "source history changed or rotated");
        check(new File(saved, "auto").listFiles().length == 10, "history save broke backup rotation");
        String retained = store.choices().getString("last_backup_path");
        check(uid(new File(retained)) == 1, "formal previous account not retained");

        File stagedRoot = new File(base, "editor-pending"); stagedRoot.mkdir(); installOld(stagedRoot);
        LauncherStore staged = new LauncherStore(stagedRoot);
        File stagedSaved = new File(stagedRoot, "retained");
        staged.stageSave(account(2), "chosen.json", "Downloads/chosen.json");
        byte[] pending = staged.editorSource("selected", stagedSaved);
        JSONObject pendingEdit = new JSONObject(new String(pending, "UTF-8"));
        pendingEdit.getJSONObject("main").put("scoin", 77);
        String initialHash = LauncherStore.hash(pending);
        staged.saveEditedPending(initialHash, pendingEdit.toString().getBytes("UTF-8"), stagedSaved);
        check(staged.pendingSave() && uid(staged.account()) == 1, "pending edit touched formal account");
        check(new JSONObject(new String(staged.editorSource("selected", stagedSaved), "UTF-8")).getJSONObject("main").getInt("scoin") == 77, "edited pending not selected");
        check(uid(new File(stagedSaved, "auto").listFiles()[0].toPath().resolve("account.json").toFile()) == 2, "pending previous account not backed up");
        rejected = false;
        try { staged.saveEditedPending(initialHash, pending, stagedSaved); } catch (IOException expected) { rejected = true; }
        check(rejected && uid(staged.account()) == 1, "stale pending edit accepted");
        String historyId = "history:" + new File(stagedSaved, "auto").listFiles()[0].getName();
        byte[] restore = staged.editorSource(historyId, stagedSaved);
        String pendingHash = LauncherStore.hash(staged.editorSource("selected", stagedSaved));
        staged.saveEditedHistory(historyId, LauncherStore.hash(restore), pendingHash, restore, stagedSaved);
        check(staged.pendingSave() && Arrays.equals(staged.editorSource("selected", stagedSaved), restore), "history not selected as new pending save");
        check(uid(staged.account()) == 1, "pending history changed formal account");
        check(Arrays.equals(staged.editorSource(historyId, stagedSaved), restore), "pending history source changed");

        File emptyRoot = new File(base, "editor-new"); emptyRoot.mkdir();
        LauncherStore fresh = new LauncherStore(emptyRoot);
        fresh.saveNewEdited(account(5));
        check(!fresh.account().exists() && fresh.pendingSave() && uid(new File(emptyRoot, fresh.choices().getString("save_stage"))) == 5,
            "new template was not left pending");
        rejected = false;
        try { fresh.saveNewEdited(account(6)); } catch (IOException expected) { rejected = true; }
        check(rejected && uid(new File(emptyRoot, fresh.choices().getString("save_stage"))) == 5,
            "new template replaced an existing choice");

        File newFormalRoot = new File(base, "editor-new-over-formal"); newFormalRoot.mkdir(); installOld(newFormalRoot);
        LauncherStore newFormal = new LauncherStore(newFormalRoot);
        File newFormalSaved = new File(newFormalRoot, "retained");
        String newFormalHash = LauncherStore.hash(newFormal.editorSource("selected", newFormalSaved));
        rejected = false;
        try { newFormal.saveNewEdited("wrong", account(6), newFormalSaved); } catch (IOException expected) { rejected = true; }
        check(rejected && uid(newFormal.account()) == 1, "stale formal template target accepted");
        newFormal.saveNewEdited(newFormalHash, account(6), newFormalSaved);
        check(uid(newFormal.account()) == 6 && uid(new File(newFormalRoot, "formal-import.json")) == 6,
            "new template formal account/receipt mismatch");
        check(uid(new File(newFormal.choices().getString("last_backup_path"))) == 1,
            "new template did not back up formal target");

        File newPendingRoot = new File(base, "editor-new-over-pending"); newPendingRoot.mkdir(); installOld(newPendingRoot);
        LauncherStore newPending = new LauncherStore(newPendingRoot);
        File newPendingSaved = new File(newPendingRoot, "retained");
        newPending.stageSave(account(2), "chosen.json", "Downloads/chosen.json");
        String newPendingHash = LauncherStore.hash(newPending.editorSource("selected", newPendingSaved));
        newPending.saveNewEdited(newPendingHash, account(7), newPendingSaved);
        check(newPending.pendingSave() && uid(newPending.account()) == 1 &&
              uid(new File(newPendingRoot, newPending.choices().getString("save_stage"))) == 7,
              "new template did not preserve formal account while replacing pending");
        check(uid(new File(new File(newPendingSaved, "auto").listFiles()[0], "account.json")) == 2,
            "new template did not back up pending target");

        File fromHistoryRoot = new File(base, "editor-history-no-current"); fromHistoryRoot.mkdir();
        File fromHistorySaved = new File(fromHistoryRoot, "retained");
        File onlyHistory = oldAutoBackup(fromHistorySaved, 0, false);
        LauncherStore historyOnly = new LauncherStore(fromHistoryRoot);
        String onlyId = "history:" + onlyHistory.getName();
        byte[] only = historyOnly.editorSource(onlyId, fromHistorySaved);
        historyOnly.saveEditedHistory(onlyId, LauncherStore.hash(only), "", only, fromHistorySaved);
        check(historyOnly.pendingSave() && !historyOnly.account().exists() && Arrays.equals(only, historyOnly.editorSource("selected", fromHistorySaved)),
            "history without current save was not staged");
        check(Arrays.equals(only, historyOnly.editorSource(onlyId, fromHistorySaved)), "history without current save changed source");
    }

    static void checkSessionBackupPolicy(File base) throws Exception {
        File root = new File(base, "session-policy"); root.mkdir(); installOld(root);
        File saved = new File(root, "retained"); LauncherStore store = new LauncherStore(root);
        store.stageSave(account(2), "chosen.json", "chosen");
        byte[] original = store.editorSource("selected", saved);
        JSONObject next = new JSONObject(new String(original, "UTF-8"));
        next.getJSONObject("main").put("scoin", 10);
        store.saveEditedPending(LauncherStore.hash(original), next.toString().getBytes("UTF-8"), saved, true);
        File automatic = new File(saved, "auto");
        check(automatic.listFiles().length == 1, "first edit was not backed up");
        File first = automatic.listFiles()[0];
        check(new File(first, "metadata.json").isFile(), "new edit backup has no metadata");
        JSONArray list = store.editorSources(saved);
        JSONObject item = list.getJSONObject(1);
        check(item.getString("title").contains("编辑前") && !item.getString("detail").contains("/"), "history is not readable");
        byte[] once = store.editorSource("selected", saved);
        next.getJSONObject("main").put("scoin", 20);
        store.saveEditedPending(LauncherStore.hash(once), next.toString().getBytes("UTF-8"), saved, false);
        check(automatic.listFiles().length == 1, "same editor session created another backup");
        store.stageSave(new JSONObject(new String(original, "UTF-8")).toString(2).getBytes("UTF-8"), "same.json", "same");
        check(store.editorBackupForTarget(saved) == null, "identical JSON content was not deduplicated");
        JSONObject unique = new JSONObject(new String(original, "UTF-8"));
        unique.getJSONObject("main").put("scoin", 5);
        store.stageSave(unique.toString().getBytes("UTF-8"), "different.json", "different");
        check(store.editorBackupForTarget(saved) != null, "different data incorrectly deduplicated");
        store.commitPendingSave(false, saved);
        check(automatic.listFiles().length == 1, "plain replacement created an automatic backup");

        byte[] historic = LauncherStore.read(new File(first, "account.json"));
        String historyId = "history:" + first.getName();
        String currentHash = LauncherStore.hash(store.editorSource("selected", saved));
        JSONObject edited = new JSONObject(new String(historic, "UTF-8"));
        edited.getJSONObject("main").put("scoin", 99);
        store.saveEditedHistory(historyId, LauncherStore.hash(historic), currentHash,
                                edited.toString().getBytes("UTF-8"), saved, false);
        check(automatic.listFiles().length == 1, "history save after first session save backed up again");
        check(Arrays.equals(historic, LauncherStore.read(new File(first, "account.json"))), "history source changed");
        check(uid(store.account()) == 2 && uid(new File(root, "formal-import.json")) == 2, "history identity did not follow account");
        currentHash = LauncherStore.hash(store.editorSource("selected", saved));
        store.saveNewEdited(currentHash, account(3), saved, false);
        check(automatic.listFiles().length == 1, "new template after first session save backed up again");
        check(uid(store.account()) == 3 && uid(new File(root, "formal-import.json")) == 3, "new template identity did not follow account");

        File numeric = new File(base, "different-json-number-types"); numeric.mkdir(); installOld(numeric);
        LauncherStore numericStore = new LauncherStore(numeric); File numericSaved = new File(numeric, "retained");
        String integer = new String(account(2), "UTF-8").replace("\"main\":{}", "\"main\":{\"scoin\":1}");
        String floating = integer.replace("\"scoin\":1", "\"scoin\":1.0");
        numericStore.stageSave(integer.getBytes("UTF-8"), "int.json", "int");
        JSONObject changed = new JSONObject(integer); changed.getJSONObject("main").put("scoin", 2);
        numericStore.saveEditedPending(LauncherStore.hash(integer.getBytes("UTF-8")), changed.toString().getBytes("UTF-8"), numericSaved, true);
        numericStore.stageSave(floating.getBytes("UTF-8"), "float.json", "float");
        check(numericStore.editorBackupForTarget(numericSaved) != null, "float and integer were incorrectly treated as identical");

        File damaged = new File(base, "damaged-old-backup"); damaged.mkdir(); installOld(damaged);
        File damagedSaved = new File(damaged, "retained"); File partial = oldAutoBackup(damagedSaved, 0, false);
        Files.write(new File(partial, "account.json").toPath(), "{\"schema\":".getBytes("UTF-8"));
        LauncherStore damagedStore = new LauncherStore(damaged);
        check(damagedStore.editorSources(damagedSaved).length() == 1, "partial backup displayed as valid");
        check(damagedStore.editorBackupForTarget(damagedSaved) != null, "partial backup used for deduplication");
        check(partial.isDirectory(), "partial old backup was deleted");
    }

    static void checkPendingBackupInterrupted(File base) throws Exception {
        File sample = new File(base, "pending-backup-sample"); sample.mkdir(); installOld(sample);
        LauncherStore first = new LauncherStore(sample); File saved = new File(sample, "retained");
        first.stageSave(account(2), "source", "source");
        Os.calls = 0; first.saveEditedPending(LauncherStore.hash(account(2)), account(2), saved, true);
        int steps = Os.calls;
        for (int stop = 1; stop <= steps; stop++) {
            File root = new File(base, "pending-backup-interrupted-" + stop); root.mkdir(); installOld(root);
            LauncherStore store = new LauncherStore(root); File targetRoot = new File(root, "retained");
            store.stageSave(account(2), "source", "source");
            Os.calls = 0; Os.crashAfter = stop;
            try { store.saveEditedPending(LauncherStore.hash(account(2)), account(2), targetRoot, true);
                throw new AssertionError("backup interruption did not fire"); }
            catch (Os.Interrupted expected) { }
            finally { Os.crashAfter = 0; }
            store.editorSources(targetRoot);
            store.editorBackupForTarget(targetRoot);
            File auto = new File(targetRoot, "auto");
            if (auto.isDirectory()) for (File folder : auto.listFiles())
                check(Arrays.equals(LauncherStore.read(new File(folder, "account.json")), account(2)), "partial backup was published");
        }
    }

    static void checkEditorInterruptedReplacement(File base) throws Exception {
        File sampleRoot = new File(base, "editor-interrupted-sample"); sampleRoot.mkdir(); installOld(sampleRoot);
        LauncherStore sample = new LauncherStore(sampleRoot);
        sample.updateChoices(new JSONObject().put("save_name", "prior.json").put("save_path", "prior-path"));
        String before = LauncherStore.hash(sample.currentSave());
        Os.calls = 0; sample.saveNewEdited(before, account(6), new File(sampleRoot, "retained"));
        int steps = Os.calls;
        for (int stop = 1; stop <= steps; stop++) {
            File root = new File(base, "editor-interrupted-" + stop); root.mkdir(); installOld(root);
            LauncherStore store = new LauncherStore(root);
            store.updateChoices(new JSONObject().put("save_name", "prior.json").put("save_path", "prior-path"));
            Os.calls = 0; Os.crashAfter = stop;
            try { store.saveNewEdited(LauncherStore.hash(account(1)), account(6), new File(root, "retained"));
                throw new AssertionError("editor interruption did not fire"); }
            catch (Os.Interrupted expected) { }
            finally { Os.crashAfter = 0; }
            store.recover(); store.recover();
            int current = uid(store.account());
            check(current == 1 || current == 6, "interrupted editor installed unexpected account");
            check(uid(new File(root, "formal-import.json")) == current, "interrupted editor mixed account and receipt");
            check(!store.pendingSave(), "interrupted editor left an unintended pending selection");
            check(!new File(root, "launcher-editor-selection.json").exists(), "editor transaction not resolved");
            if (current == 1) check(store.choices().getString("save_name").equals("prior.json") &&
                                    store.choices().getString("save_path").equals("prior-path"), "prior selection not restored");
        }
        File root = new File(base, "editor-interrupted-failed-receipt"); root.mkdir(); installOld(root);
        LauncherStore failed = new LauncherStore(root);
        failed.updateChoices(new JSONObject().put("save_name", "prior.json"));
        Os.failReceipt = true; Os.failReceiptTarget = new File(root, "formal-import.json").getPath();
        boolean rejected = false;
        try { failed.saveNewEdited(LauncherStore.hash(account(1)), account(6), new File(root, "retained")); }
        catch (IOException expected) { rejected = true; }
        check(rejected && uid(failed.account()) == 1 && !failed.pendingSave() &&
              failed.choices().getString("save_name").equals("prior.json"), "failed editor import left a pending replacement");

        File historySampleRoot = new File(base, "editor-interrupted-history-sample"); historySampleRoot.mkdir(); installOld(historySampleRoot);
        File historySampleSaved = new File(historySampleRoot, "retained");
        File historySampleFile = oldAutoBackup(historySampleSaved, 0, false);
        LauncherStore historySample = new LauncherStore(historySampleRoot);
        String sampleHistoryId = "history:" + historySampleFile.getName();
        Os.calls = 0;
        historySample.saveEditedHistory(sampleHistoryId, LauncherStore.hash(account(10)), LauncherStore.hash(account(1)),
            account(10), historySampleSaved);
        int historySteps = Os.calls;
        for (int stop = 1; stop <= historySteps; stop++) {
            File historyRoot = new File(base, "editor-interrupted-history-" + stop); historyRoot.mkdir(); installOld(historyRoot);
            File historySaved = new File(historyRoot, "retained");
            File historyFile = oldAutoBackup(historySaved, 0, false);
            String historyId = "history:" + historyFile.getName();
            LauncherStore historyStore = new LauncherStore(historyRoot);
            historyStore.updateChoices(new JSONObject().put("save_name", "prior.json"));
            Os.calls = 0; Os.crashAfter = stop;
            try { historyStore.saveEditedHistory(historyId, LauncherStore.hash(account(10)), LauncherStore.hash(account(1)),
                      account(10), historySaved); throw new AssertionError("history interruption did not fire"); }
            catch (Os.Interrupted expected) { }
            finally { Os.crashAfter = 0; }
            historyStore.recover(); historyStore.recover();
            int current = uid(historyStore.account());
            check((current == 1 || current == 10) && uid(new File(historyRoot, "formal-import.json")) == current,
                  "interrupted history mixed account and receipt");
            check(!historyStore.pendingSave() && historyFile.isDirectory() &&
                  Arrays.equals(historyStore.editorSource(historyId, historySaved), account(10)),
                  "interrupted history left pending selection or changed history");
            if (current == 1) check(historyStore.choices().getString("save_name").equals("prior.json"), "history failed to restore prior selection");
        }

        File tokenRoot = new File(base, "editor-selection-token"); tokenRoot.mkdir(); installOld(tokenRoot);
        LauncherStore tokenStore = new LauncherStore(tokenRoot);
        LauncherStore.EditorSnapshot formal = tokenStore.editorSnapshot("selected", null);
        tokenStore.stageSave(account(1), "same-bytes.json", "chosen");
        rejected = false;
        try { tokenStore.requireEditorTarget(formal.targetToken, formal.targetHash); } catch (IOException expected) { rejected = true; }
        check(rejected, "same bytes in a new pending source were mistaken for the formal source");
        LauncherStore.EditorSnapshot pending = tokenStore.editorSnapshot("selected", null);
        tokenStore.stageSave(account(1), "another-identical.json", "chosen-again");
        rejected = false;
        try { tokenStore.requireEditorTarget(pending.targetToken, pending.targetHash); } catch (IOException expected) { rejected = true; }
        check(rejected, "identical replacement pending source was mistaken for the original");
    }
    public static void main(String[] args) throws Exception {
        File base = new File(args[0]); if (!base.mkdir()) throw new IOException("fresh output required");
        checkAutomaticRotation(base);
        checkEditorSourcesAndHistory(base);
        checkSessionBackupPolicy(base);
        checkPendingBackupInterrupted(base);
        checkEditorInterruptedReplacement(base);
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
        store.commitPendingSave(false, new File(failed, "retained"));
        check(uid(store.account()) == 2 && uid(new File(failed, "formal-import.json")) == 2 && !store.pendingSave(), "retry failed after rollback");
        check(!new File(failed, "retained").exists(), "retry created an unrequested history backup");
        store.stageSave(account(2), "new.json", "…/new.json");
        String prior = store.choices().toString();
        for (byte[] invalid : new byte[][]{"bad".getBytes("UTF-8"), "{\"schema\":1,\"uid\":\"2\"}".getBytes("UTF-8"), "{\"schema\":1,\"uid\":2}".getBytes("UTF-8")}) {
            boolean rejected = false; try { store.stageSave(invalid, "bad.json", "…/bad.json"); } catch (Exception expected) { rejected = true; }
            check(rejected && prior.equals(store.choices().toString()), "bad selection replaced prior choice");
        }
        JSONObject choices = store.choices();
        Files.write(new File(failed, choices.getString("save_stage")).toPath(), account(3));
        boolean rejected = false; try { store.commitPendingSave(false, null); } catch (IOException expected) { rejected = true; }
        check(rejected && uid(store.account()) == 2, "tampered staged save accepted");
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
