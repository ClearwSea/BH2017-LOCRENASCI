package local.bh3.server19probe;

import android.app.*;
import android.content.*;
import android.database.Cursor;
import android.net.Uri;
import android.os.*;
import android.provider.OpenableColumns;
import android.widget.*;
import java.io.*;
import org.json.JSONObject;
import org.json.JSONArray;

/** User-controlled preparation and startup / 手动选择、准备与启动。 */
public class IntegratedActivity extends Activity {
    private static final Object PYTHON_INIT_LOCK = new Object();
    private boolean bound, leaving, busy, ready, starting, blocked;
    private LauncherScreen screen;
    private SaveEditorScreen editor;
    private ServerSettingsScreen serverSettings;
    private CountDownTimer noticeTimer;
    private LauncherStore store;
    private final Handler main = new Handler(Looper.getMainLooper());
    private int dp(int value) { return (int)(value * getResources().getDisplayMetrics().density); }

    private static final String PREF_NOTICE_ACK_VERSION = "notice_ack_version";
    private static final String NOTICE =
        "禁止非法倒卖\n" +
        "该项目完全免费，仅供技术交流学习，如果你是从拼多多/淘宝/闲鱼等电商平台获取，说明你被骗了，请立即退款并举报。\n\n" +
        "遇到问题之前请确保当前是最新构建版！\n" +
        "遇到问题之前请确保当前是最新构建版！\n" +
        "遇到问题之前请确保当前是最新构建版！\n\n" +
        "仅在特定开发平台验证，不做可玩性技术承诺。\n" +
        "以下情况出现问题（例如卡死，崩溃）是可预见的：\n" +
        "1.过高的Android版本\n" +
        "2.纯64位处理器，且系统内无可靠转译层\n" +
        "3.部分联发科天玑，新款海思麒麟处理器机型，如\n" +
        "\u3000\u3000部分采用Mali GPU的新款机型\n" +
        "\u3000\u3000采用Maleoon GPU的机型";
    private void preparationPanel() {
        screen = new LauncherScreen(this, new LauncherScreen.Actions() {
            @Override public void selectResource() { choose(20); }
            @Override public void selectSave() { requestSaveChoice(); }
            @Override public void exportSave() { requestExport(); }
            @Override public void editSave() { openEditor(); }
            @Override public void adjustServer() { openServerSettings(); }
            @Override public void start() { requestStart(); }
            @Override public void changeDamage(boolean checked) {
                if (!ready || busy || blocked || store == null) return;
                try {
                    JSONObject patch = new JSONObject(); patch.put("damage_boost", checked); store.updateChoices(patch);
                } catch (Exception error) {
                    try { refreshChoices(); } catch (Exception ignored) { }
                    showFailure("保存伤害设置失败", error);
                }
            }
        }, NOTICE);
        screen.render(); controls();
    }
    private void setStatus(String value) { if (screen != null) screen.status(value); }
    private void controls() {
        boolean enabled = ready && !busy && !blocked;
        if (screen != null) screen.controls(enabled, starting, enabled && store != null && store.account().isFile());
    }
    private void refreshChoices() throws Exception {
        JSONObject chosen = store.choices();
        boolean resourcesPresent = new File(getFilesDir(), "embedded-resources.ready").isFile();
        boolean resourceChosen = !chosen.optString("resource_uri").isEmpty();
        boolean resourcePending = chosen.optBoolean("resource_pending");
        String resourceTitle,resourceState,resourceDetails;
        if (resourceChosen) {
            resourceTitle=chosen.optString("resource_name", "所选资源包");
            resourceState=resourcePending ? "待校验" : resourcesPresent ? "已导入" : "已选择";
            resourceDetails=chosen.optString("resource_path", "路径不可用");
        } else if (resourcesPresent) {
            resourceTitle="已导入的离线视频资源";resourceState="已导入";
            resourceDetails="…/files/assets/Video";
        } else {
            resourceTitle="尚未选择";resourceState="未选择";resourceDetails="尚未选择";
        }
        boolean pending=store.pendingSave(), accountPresent=store.account().isFile();
        String saveTitle,saveState,saveDetails;
        if (!chosen.optString("save_name").isEmpty()) {
            saveTitle=chosen.optString("save_name");saveState=pending ? "待导入" : accountPresent ? "已导入" : "未导入";
            saveDetails=pending ? chosen.optString("save_path", "路径不可用") : accountPresent ? store.account().getAbsolutePath() : "尚未选择";
        } else if (accountPresent) {
            saveTitle="account.json（当前存档）";saveState="已导入";
            saveDetails=store.account().getAbsolutePath();
        } else {
            saveTitle="尚未选择";saveState="未选择";saveDetails="尚未选择";
        }
        screen.choices(chosen.optBoolean("damage_boost", true),resourceTitle,resourceState,resourceDetails,saveTitle,saveState,saveDetails);
        controls();
    }
    private void selectionStatus(String otherwise) throws Exception {
        JSONObject chosen=store.choices();
        boolean resource=!chosen.optString("resource_uri").isEmpty() || new File(getFilesDir(),"embedded-resources.ready").isFile();
        boolean save=store.pendingSave() || store.account().isFile();
        setStatus(resource && save ? "点击开始游戏将校验内容，若为首次启动则需要较长时间，请耐心等待" : otherwise);
    }
    private void choose(int request) {
        if (!ready || busy || blocked) return;
        Intent picker = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        picker.addCategory(Intent.CATEGORY_OPENABLE); picker.setType("*/*");
        picker.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);
        startActivityForResult(picker, request);
    }
    private void requestSaveChoice() {
        if (!ready || busy || blocked || store == null) return;
        if (!store.account().isFile()) { choose(19); return; }
        new AlertDialog.Builder(this).setTitle("更换存档")
            .setMessage("选择新存档后，点击开始游戏将覆盖当前已导入的存档。建议先导出当前存档，保存到指定位置。")
            .setNeutralButton("导出当前存档", (dialog, which) -> requestExport())
            .setNegativeButton("取消", null)
            .setPositiveButton("继续选择", (dialog, which) -> choose(19)).show();
    }
    private String displayName(Uri uri) {
        try (Cursor cursor = getContentResolver().query(uri, new String[]{OpenableColumns.DISPLAY_NAME}, null, null, null)) {
            if (cursor != null && cursor.moveToFirst() && !cursor.isNull(0)) return cursor.getString(0);
        } catch (Exception ignored) { }
        String name = uri.getLastPathSegment(); return name == null ? "所选文件" : name;
    }
    private String displayPath(Uri uri) {
        String path = uri.getPath(); if (path == null) return uri.getAuthority();
        path = path.replace(':', '/'); String[] parts = path.split("/");
        int start = Math.max(0, parts.length - 3); StringBuilder tail = new StringBuilder("…");
        for (int i = start; i < parts.length; i++) if (!parts[i].isEmpty()) tail.append('/').append(parts[i]);
        return tail.toString();
    }
    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request == 21) {
            if (result == RESULT_OK && data != null && data.getData() != null) exportTo(data.getData());
            return;
        }
        if ((request != 19 && request != 20) || result != RESULT_OK || data == null || data.getData() == null) return;
        final Uri uri = data.getData(); final String name = displayName(uri), path = displayPath(uri);
        if (request == 20) {
            try {
                boolean persisted = false;
                try { getContentResolver().takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION); persisted = true; }
                catch (SecurityException ignored) { }
                JSONObject selected = new JSONObject();
                selected.put("resource_uri", uri.toString()).put("resource_name", name).put("resource_path", path);
                selected.put("resource_pending", true).put("resource_persisted", persisted); store.updateChoices(selected);
                refreshChoices(); selectionStatus("资源包已选择，请选择存档。" + (persisted ? "" : "本文件授权可能只在本次有效。"));
            } catch (Exception error) { showFailure("资源包选择失败", error); }
            return;
        }
        busy = true; controls(); setStatus("正在校验所选存档，现有进度保持不变……");
        new Thread(() -> {
            try {
                byte[] raw;
                try (InputStream in = getContentResolver().openInputStream(uri); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
                    if (in == null) throw new IOException("无法读取所选文件");
                    byte[] buffer = new byte[65536]; int count;
                    while ((count = in.read(buffer)) != -1) {
                        if (out.size() + count > 16 * 1024 * 1024) throw new IOException("存档超过16MiB");
                        out.write(buffer, 0, count);
                    }
                    raw = out.toByteArray();
                }
                if (isFinishing() || isDestroyed()) return;
                store.stageSave(raw, name, path);
                main.post(() -> {
                    busy = false;
                    try { refreshChoices(); selectionStatus("存档已选择，请选择资源包。"); }
                    catch (Exception error) { showFailure("读取选择记录失败", error); }
                });
            } catch (Exception error) { main.post(() -> { busy = false; showFailure("存档选择失败", error); }); }
        }, "launcher-select-save").start();
    }
    private void requestExport() {
        if (!ready || busy || blocked) return;
        if (serverRunning()) { setStatus("请先退出游戏并从最近任务划掉，再导出当前完整进度。"); return; }
        Intent create = new Intent(Intent.ACTION_CREATE_DOCUMENT);
        create.addCategory(Intent.CATEGORY_OPENABLE); create.setType("application/json");
        String stamp = new java.text.SimpleDateFormat("yyyyMMdd-HHmmss", java.util.Locale.ROOT).format(new java.util.Date());
        create.putExtra(Intent.EXTRA_TITLE, "bh3-save-" + stamp + ".json");
        create.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
        startActivityForResult(create, 21);
    }
    private void exportTo(Uri target) {
        if (serverRunning()) { setStatus("服务端正在运行，未导出；请退出游戏后重试。"); return; }
        busy = true; controls(); setStatus("正在导出当前存档……");
        final String name = displayName(target), path = displayPath(target);
        new Thread(() -> {
            try {
                byte[] raw = store.currentSave();
                try (OutputStream out = getContentResolver().openOutputStream(target, "wt")) {
                    if (out == null) throw new IOException("无法写入所选位置");
                    out.write(raw); out.flush();
                    if (out instanceof FileOutputStream) {
                        try { ((FileOutputStream)out).getFD().sync(); }
                        catch (SyncFailedException unsupported) { /* Document providers may use pipes. */ }
                    }
                }
                boolean verified = false;
                try (InputStream in = getContentResolver().openInputStream(target)) {
                    if (in != null) {
                        java.security.MessageDigest digest = java.security.MessageDigest.getInstance("SHA-256");
                        byte[] buffer = new byte[65536]; int count; long length = 0;
                        while ((count = in.read(buffer)) != -1) {
                            length += count;
                            if (length > raw.length) throw new IOException("导出文件长度校验不一致");
                            digest.update(buffer, 0, count);
                        }
                        verified = length == raw.length && EmbeddedResources.hex(digest.digest()).equals(LauncherStore.hash(raw));
                        if (!verified) throw new IOException("导出文件校验不一致，请重新导出");
                    }
                } catch (SecurityException | FileNotFoundException unavailable) { }
                if (isFinishing() || isDestroyed()) return;
                JSONObject selected = new JSONObject();
                selected.put("last_export_name", name).put("last_export_path", path); store.updateChoices(selected);
                final boolean checked = verified;
                main.post(() -> {
                    busy = false;
                    try { refreshChoices(); setStatus("已导出当前存档" + (checked ? "并校验一致" : "（此位置不支持回读校验）") + "：" + name + "\n位置：" + path); }
                    catch (Exception error) { showFailure("读取导出记录失败", error); }
                });
            } catch (Exception error) {
                main.post(() -> { busy = false; showFailure("导出失败，目标位置可能有不完整文件，请重试", error); });
            }
        }, "launcher-export-save").start();
    }
    private boolean serverRunning() {
        ActivityManager manager = (ActivityManager)getSystemService(ACTIVITY_SERVICE);
        java.util.List<ActivityManager.RunningAppProcessInfo> processes = manager.getRunningAppProcesses();
        if (processes != null) for (ActivityManager.RunningAppProcessInfo process : processes)
            if ((getPackageName() + ":server").equals(process.processName)) return true;
        return false;
    }
    private void openEditor() {
        if (!ready || busy || blocked || editor != null) return;
        if (serverRunning()) { setStatus("请先退出游戏并从最近任务划掉，再编辑存档。"); return; }
        editor = new SaveEditorScreen(this, new EditorBackend(), () -> {
            editor = null; screen.render();
            try { refreshChoices(); } catch (Exception error) { showFailure("读取存档选择失败", error); }
        });
        editor.show();
    }
    private void openServerSettings() {
        if (!ready || busy || blocked || editor != null || serverSettings != null) return;
        if (serverRunning()) { setStatus("请先退出游戏并从最近任务划掉，再调整服务端。"); return; }
        serverSettings = new ServerSettingsScreen(this, new ServerSettingsScreen.Backend() {
            private boolean guardOwned;
            private void requireStopped() throws IOException {
                if (serverRunning()) throw new IOException("服务端仍在运行，请彻底退出游戏后重试");
            }
            @Override public JSONObject load() throws Exception {
                com.chaquo.python.Python host = python();
                host.getModule("process_guard").callAttr("acquire", IntegratedActivity.this); guardOwned = true;
                requireStopped();
                return new JSONObject(host.getModule("gm_entry").callAttr("load", IntegratedActivity.this).toString());
            }
            @Override public void save(JSONObject value) throws Exception {
                requireStopped();
                JSONObject config = new JSONObject();
                config.put("abyss_temperature", value.isNull("abyss_temperature") ? JSONObject.NULL : value.getInt("abyss_temperature"));
                config.put("next_bosses", value.isNull("next_bosses") ? JSONObject.NULL : value.getJSONArray("next_bosses"));
                python().getModule("gm_entry").callAttr("save", IntegratedActivity.this, config.toString(), value.getLong("effective_begin"));
            }
            @Override public void close() throws Exception {
                if (guardOwned) { python().getModule("process_guard").callAttr("release"); guardOwned = false; }
            }
        }, () -> { serverSettings = null; screen.render();
            try { refreshChoices(); } catch (Exception error) { showFailure("读取启动设置失败", error); }
        });
        serverSettings.show();
    }
    private final class EditorBackend implements SaveEditorScreen.Backend {
        private String sourceId, sourceHash, targetHash, targetToken;
        private boolean guardOwned, backupDone;
        private com.chaquo.python.PyObject module() throws Exception {
            return python().getModule("editor_entry");
        }
        private void requireStopped() throws IOException {
            if (serverRunning()) throw new IOException("服务端仍在运行，请彻底退出游戏后重试");
        }
        private void remember(LauncherStore.EditorSnapshot snapshot) {
            sourceHash = snapshot.sourceHash; targetHash = snapshot.targetHash; targetToken = snapshot.targetToken;
        }
        @Override public JSONArray sources() throws Exception {
            module();
            if (!guardOwned) {
                com.chaquo.python.Python.getInstance().getModule("process_guard").callAttr("acquire", IntegratedActivity.this);
                guardOwned = true;
            }
            requireStopped(); return store.editorSources(backupRoot());
        }
        @Override public JSONObject load(String id) throws Exception {
            requireStopped(); LauncherStore.EditorSnapshot snapshot = store.editorSnapshot(id, backupRoot());
            sourceId = id; remember(snapshot);
            return new JSONObject(module().callAttr("load", IntegratedActivity.this, new String(snapshot.source, "UTF-8")).toString());
        }
        @Override public JSONObject create(long uid, String kind) throws Exception {
            requireStopped(); sourceId = "new"; remember(store.editorSnapshot(null, backupRoot()));
            return new JSONObject(module().callAttr("create", IntegratedActivity.this, uid, kind).toString());
        }
        @Override public JSONObject apply(JSONObject account, JSONObject operation) throws Exception {
            requireStopped();
            return new JSONObject(module().callAttr("apply", account.toString(), operation.toString()).toString());
        }
        @Override public void save(JSONObject account) throws Exception {
            requireStopped(); byte[] raw = account.toString().getBytes("UTF-8");
            LauncherStore.validateAccount(raw);
            store.withEditorLock(() -> {
                store.requireEditorTarget(targetToken, targetHash);
                String committedHash = LauncherStore.hash(raw);
                boolean needBackup = !backupDone;
                if ("selected".equals(sourceId) && targetToken.startsWith("pending:")) {
                    store.saveEditedPending(sourceHash, raw, backupRoot(), needBackup);
                } else if ("selected".equals(sourceId)) {
                    File target = needBackup ? store.editorBackupForTarget(backupRoot()) : null;
                    committedHash = module().callAttr("save", IntegratedActivity.this, account.toString(), target == null ? "" : target.getAbsolutePath(), sourceHash).toString();
                    if (target != null) try { store.editorBackupComplete(backupRoot(), target); }
                    catch (Exception warning) { editorWarning("存档已保存，但备份轮换未完成：" + warning.getMessage()); }
                } else {
                    final Exception[] failure = new Exception[1];
                    Runnable action = () -> {
                        try {
                            if ("new".equals(sourceId)) store.saveNewEdited(targetHash, raw, backupRoot(), needBackup);
                            else store.saveEditedHistory(sourceId, sourceHash, targetHash, raw, backupRoot(), needBackup);
                        } catch (Exception error) { failure[0] = error; }
                    };
                    module().callAttr("with_account_lock", IntegratedActivity.this, action);
                    if (failure[0] != null) throw failure[0];
                }
                backupDone = true;
                sourceId = "selected"; sourceHash = committedHash; targetHash = committedHash; targetToken = "";
                try { remember(store.editorSnapshot("selected", backupRoot())); }
                catch (Exception warning) { editorWarning("存档已保存，请重新读取后继续编辑：" + warning.getMessage()); }
            });
        }
        private void editorWarning(String text) { main.post(() -> Toast.makeText(IntegratedActivity.this, text, Toast.LENGTH_LONG).show()); }
        @Override public void close() throws Exception {
            if (guardOwned) {
                com.chaquo.python.Python.getInstance().getModule("process_guard").callAttr("release");
                guardOwned = false;
            }
        }
    }
    private com.chaquo.python.Python python() throws Exception {
        synchronized (PYTHON_INIT_LOCK) {
            if (!com.chaquo.python.Python.isStarted())
                com.chaquo.python.Python.start(PythonPlatform.create(getApplicationContext()));
            return com.chaquo.python.Python.getInstance();
        }
    }
    private void requestStart() {
        if (!ready || busy || blocked) return;
        try {
            if (!store.account().isFile() && !store.pendingSave()) { setStatus("请先选择自己的服务端 JSON 存档。"); return; }
            JSONObject selected = store.choices();
            DamageMode.requireCanApply(this, selected.optBoolean("damage_boost", true) ? 20 : 1);
            if ((store.pendingSave() || selected.optBoolean("resource_pending")) && serverRunning()) {
                setStatus("服务端仍在运行。请退出游戏并从最近任务划掉后，再应用重选的文件。"); return;
            }
            beginStart();
        } catch (Exception error) { showFailure("无法开始", error); }
    }
    private File backupRoot() {
        File external = getExternalFilesDir(null);
        return external == null ? null : new File(external, "save-backups");
    }
    private void beginStart() {
        if (busy || blocked || isFinishing() || isDestroyed()) return;
        busy = true; starting = true; screen.begin(); controls(); screen.stage(1, "启动条件已检查，正在准备离线资源。");
        android.util.Log.i("Server19Launcher", "Start button accepted");
        new Thread(() -> {
            com.chaquo.python.PyObject guard = null;
            boolean guardOwned = false;
            Exception failure = null;
            boolean videoMissing = false, prepared = false;
            try {
                guard = python().getModule("process_guard");
                guard.callAttr("acquire", IntegratedActivity.this);
                guardOwned = true;
                JSONObject selected = store.choices();
                Uri remembered = selected.optString("resource_uri").isEmpty() ? null : Uri.parse(selected.getString("resource_uri"));
                Uri source = selected.optBoolean("resource_pending") ? remembered : null;
                EmbeddedResources.Progress progress = new EmbeddedResources.Progress() {
                    @Override public void update(String text) { main.post(() -> setStatus(text)); }
                    @Override public void stage(String phase,long done,long total) {
                        int previous=phase.equals("verify")?1:2;
                        String label=phase.equals("verify")?"正在校验资源":"正在解压资源";
                        int percent=(int)Math.min(100,done*100/total);
                        main.post(() -> screen.progress(previous,label+" "+percent+"%",done,total));
                    }
                    @Override public void skipped(String phase) {
                        int completed=phase.equals("verify")?2:3;
                        String message=phase.equals("verify")?"资源校验无需执行。":"资源无需解压。";
                        main.post(() -> screen.stage(completed,message));
                    }
                };
                try { EmbeddedResources.prepare(this, source, progress); }
                catch (EmbeddedResources.VideoRequired missing) {
                    if (remembered == null || source != null) throw missing;
                    EmbeddedResources.prepare(this, remembered, progress);
                }
                if (isFinishing() || isDestroyed()) return;
                store.resourcePrepared(remembered == null ? "" : remembered.toString());
                main.post(() -> screen.stage(3, "离线资源已准备。"));
                if (store.pendingSave() && serverRunning()) throw new IOException("服务端仍在运行，未替换存档");
                DamageMode.apply(this, selected.optBoolean("damage_boost", true) ? 20 : 1);
                boolean importing = store.pendingSave();
                store.commitPendingSave(false, backupRoot());
                main.post(() -> screen.stage(4, importing ? "已导入所选存档。" : "沿用当前存档。"));
                prepared = true;
            } catch (EmbeddedResources.VideoRequired missing) {
                videoMissing = true;
            } catch (Exception error) { failure = error; }
            finally {
                if (guardOwned) {
                    try { guard.callAttr("release"); }
                    catch (Exception error) { failure = error; prepared = false; }
                }
            }
            if (videoMissing) {
                main.post(() -> { busy = false; starting = false; controls(); screen.failure("需要配套离线视频 ZIP，请先选择资源包，再点击“开始游戏”。"); });
            } else if (failure != null) {
                final Exception error = failure;
                main.post(() -> { busy = false; starting = false; showFailure("准备失败", error); });
            } else if (prepared) {
                main.post(() -> {
                    try { refreshChoices(); startServer(); }
                    catch (Exception error) { busy = false; starting = false; showFailure("启动失败", error); }
                });
            }
        }, "launcher-prepare").start();
    }
    private void showFailure(String action, Exception error) {
        android.util.Log.e("Server19Launcher", action, error); controls(); screen.failure(action + "：" + error.getMessage());
    }
    private void startServer() {
        if (isFinishing() || isDestroyed() || !starting) return;
        if (getIntent().getBooleanExtra("prepare_only", false)) {
            busy = false; starting = false; controls();
            setStatus("离线资源准备及校验完成。尚未启动游戏或服务端。");
            android.util.Log.i("Server19Resources", "Private resources ready; uid=" + android.os.Process.myUid()); return;
        }
        setStatus("离线资源已就绪，正在启动服务端……");
        Intent service = new Intent(this, IntegratedService.class);
        if (Build.VERSION.SDK_INT >= 26) startForegroundService(service); else startService(service);
        bound = bindService(service, connection, BIND_AUTO_CREATE);
        if (!bound) { busy = false; starting = false; blocked = true; controls(); screen.failure("无法连接服务端，请退出应用后重试。"); return; }
        main.postDelayed(() -> { if (starting && !leaving) setStatus("服务端尚未就绪，请保留现场并反馈。"); }, 30000);
    }
    private final Messenger reply = new Messenger(new Handler(Looper.getMainLooper(), msg -> {
        if (msg.what == 2 && starting && !leaving && !isFinishing()) {
            busy = false; starting = false; blocked = true; controls();
            screen.failure("服务端启动失败：" + msg.getData().getString("error", "未知错误") + "\n请退出应用后重试，或保留现场反馈。");
        }
        if (msg.what == 1 && starting && !leaving && !isFinishing()) {
            screen.stage(5, "本地服务端已就绪。");
            if (getIntent().getBooleanExtra("server_only", false)) {
                busy = false; starting = false; controls(); setStatus("服务端已就绪（技术检查，未启动游戏）。");
                return true;
            }
            Intent game = new Intent();
            game.setClassName(getPackageName(), "com.miHoYo.overridenativeactivity.OverrideNativeActivity");
            try { startActivity(game); screen.stage(6, "已交由系统启动游戏。"); leaving = true; finish(); }
            catch (ActivityNotFoundException error) { busy = false; starting = false; showFailure("无法打开游戏", error); }
        }
        return true;
    }));
    private final ServiceConnection connection = new ServiceConnection() {
        @Override public void onServiceConnected(ComponentName name, IBinder binder) {
            Message request = Message.obtain(null, 1); request.replyTo = reply;
            try { new Messenger(binder).send(request); }
            catch (RemoteException error) { busy = false; starting = false; blocked = true; showFailure("服务端连接失败", error); }
        }
        @Override public void onServiceDisconnected(ComponentName name) {
            busy = false; starting = false; controls(); setStatus("服务端已停止，请保留现场并反馈。");
        }
    };
    @Override public void onCreate(Bundle state) {
        setTheme(android.R.style.Theme_Material_NoActionBar);
        super.onCreate(state); store = new LauncherStore(getFilesDir()); preparationPanel();
        try { store.recover(); refreshChoices(); }
        catch (Exception error) { blocked = true; showFailure("读取或恢复启动记录失败", error); return; }
        String ackVersion = getPreferences(Activity.MODE_PRIVATE).getString(PREF_NOTICE_ACK_VERSION, "");
        if (!LauncherScreen.VERSION.equals(ackVersion)) {
            screen.hint("首次进入或版本更新，请阅读重要公告并勾选“我已阅读”……");
            android.util.Log.i("Server19Notice", "Mandatory notice shown for " + LauncherScreen.VERSION + " (previous=" + ackVersion + ")");
            screen.showMandatoryNotice(() -> {
                if (isFinishing() || isDestroyed()) return;
                getPreferences(Activity.MODE_PRIVATE).edit().putString(PREF_NOTICE_ACK_VERSION, LauncherScreen.VERSION).apply();
                ready = true; controls();
                try { selectionStatus("请确认资源包和存档后，点击“开始游戏”。"); }
                catch (Exception error) { showFailure("读取选择记录失败", error); }
                android.util.Log.i("Server19Notice", "Mandatory notice confirmed at " + SystemClock.elapsedRealtime());
            });
            return;
        }
        screen.hint("请阅读公告，3 秒后可开始游戏……");
        noticeTimer = new CountDownTimer(3000, 250) {
            @Override public void onTick(long remaining) {
                int secs = Math.max(1, (int) ((remaining + 999) / 1000));
                screen.hint("请阅读公告，" + secs + " 秒后可开始游戏……");
            }
            @Override public void onFinish() {
                if (isFinishing() || isDestroyed()) return;
                ready = true; controls();
                try { selectionStatus("请确认资源包和存档后，点击“开始游戏”。"); }
                catch (Exception error) { showFailure("读取选择记录失败", error); }
                android.util.Log.i("Server19Notice", "Countdown finished at " + SystemClock.elapsedRealtime());
            }
        };
        android.util.Log.i("Server19Notice", "Countdown started at " + SystemClock.elapsedRealtime()); noticeTimer.start();
    }
    @Override public void onConfigurationChanged(android.content.res.Configuration config) {
        super.onConfigurationChanged(config); if (editor != null) editor.render(); else if (serverSettings != null) serverSettings.render(); else if (screen != null) screen.render();
    }
    @Override public void onBackPressed() { if (editor != null) editor.close(); else if (serverSettings != null) serverSettings.close(); else super.onBackPressed(); }
    @Override public void onDestroy() {
        if (editor != null) editor.destroy();
        if (serverSettings != null) serverSettings.destroy();
        if (noticeTimer != null) noticeTimer.cancel();
        if (screen != null) screen.destroy();
        if (bound) unbindService(connection);
        main.removeCallbacksAndMessages(null); super.onDestroy();
    }
}
