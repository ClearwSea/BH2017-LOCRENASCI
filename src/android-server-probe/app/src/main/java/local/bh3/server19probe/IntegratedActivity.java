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

/** User-controlled preparation and startup / 手动选择、准备与启动。 */
public class IntegratedActivity extends Activity {
    private boolean bound, leaving, busy, ready, starting, blocked;
    private TextView status, countdown, resourceFile, saveFile, backupInfo, exportInfo;
    private Button resourceButton, saveButton, exportButton, startButton;
    private CountDownTimer noticeTimer;
    private Switch damageSwitch;
    private boolean syncingDamage;
    private LauncherStore store;
    private final Handler main = new Handler(Looper.getMainLooper());
    private int dp(int value) { return (int)(value * getResources().getDisplayMetrics().density); }

    private TextView selectionRow(LinearLayout panel, Button button) {
        LinearLayout row = new LinearLayout(this); row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(android.view.Gravity.CENTER_VERTICAL);
        row.addView(button, new LinearLayout.LayoutParams(dp(136), LinearLayout.LayoutParams.WRAP_CONTENT));
        TextView file = new TextView(this); file.setTextSize(14); file.setTextColor(0xffeeeeee);
        file.setTextIsSelectable(true); file.setPadding(dp(12), dp(10), dp(12), dp(10));
        file.setMinHeight(dp(64));
        android.graphics.drawable.GradientDrawable frame = new android.graphics.drawable.GradientDrawable();
        frame.setColor(0xff424242); frame.setCornerRadius(dp(6)); frame.setStroke(dp(1), 0xff888888);
        file.setBackground(frame);
        LinearLayout.LayoutParams label = new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1);
        label.setMargins(dp(8), 0, 0, 0); row.addView(file, label);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2); params.bottomMargin = dp(10);
        panel.addView(row, params); return file;
    }
    private void preparationPanel() {
        ScrollView scroll = new ScrollView(this); scroll.setFillViewport(true);
        LinearLayout panel = new LinearLayout(this); panel.setOrientation(LinearLayout.VERTICAL);
        int pad = dp(24); panel.setPadding(pad, pad, pad, pad);
        TextView notice = new TextView(this);
        LauncherNotice.setText(notice, "禁止非法倒卖\n如果你是从拼多多/淘宝/闲鱼等电商平台获取，说明你被骗了，请立即退款并举报。\n\n遇到问题之前请确保当前是最新构建版【当前版本：V0.1.4】【最新版本：检查】\n\n已验证适配机型：\nSONY Xperia XZ1（Android 9）\nRAZER Phone 1/2（Android 9）\nOPPO PDRM00（Android 12）\nOnePlus PJZ110 （Android 16）\n\n其他平台不做可玩性技术承诺。\n\n项目仓库：GitHub/ClearwSea，如有疑问或反馈，请提交issue。");
        notice.setTextSize(17); notice.setTextColor(0xff702400); notice.setBackgroundColor(0xffffefcf);
        notice.setPadding(pad, pad, pad, pad); notice.setLineSpacing(dp(4), 1); panel.addView(notice);
        status = new TextView(this); status.setTextSize(17); status.setPadding(0, dp(18), 0, dp(18)); panel.addView(status);
        resourceButton = new Button(this); resourceButton.setAllCaps(false);
        resourceFile = selectionRow(panel, resourceButton);
        resourceButton.setOnClickListener(view -> choose(20));
        saveButton = new Button(this); saveButton.setAllCaps(false);
        saveFile = selectionRow(panel, saveButton);
        saveButton.setOnClickListener(view -> choose(19));
        TextView generateSave = new TextView(this); generateSave.setTextSize(14);
        android.text.SpannableString generateLink = new android.text.SpannableString("生成存档");
        generateLink.setSpan(new android.text.style.URLSpan("https://github.com/ClearwSea/BH-LOCRENASCI-ACT-EDIT/releases/latest"),
            0, 4, android.text.Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
        generateSave.setText(generateLink); generateSave.setLinkTextColor(0xff66bbff);
        generateSave.setMovementMethod(android.text.method.LinkMovementMethod.getInstance());
        generateSave.setPadding(dp(12), 0, 0, dp(10)); panel.addView(generateSave);
        TextView hint = new TextView(this); hint.setTextSize(14);
        hint.setText("资源包请选择配套视频 ZIP。已有资源和存档可直接使用；重选存档将在开始游戏时确认替换，由你决定是否保留旧档备份。");
        hint.setPadding(0, dp(4), 0, dp(12)); panel.addView(hint);
        damageSwitch = new Switch(this); damageSwitch.setText("辅助伤害 20×（关闭为正常 1×）");
        panel.addView(damageSwitch);
        TextView damageHint = new TextView(this); damageHint.setTextSize(14);
        damageHint.setText("默认开启，仅影响己方角色伤害，不修改存档。修改后请彻底退出并重新打开应用，在下次开始游戏时生效。");
        panel.addView(damageHint);
        damageSwitch.setOnCheckedChangeListener((button, checked) -> {
            if (syncingDamage || store == null) return;
            try {
                JSONObject patch = new JSONObject(); patch.put("damage_boost", checked); store.updateChoices(patch);
                status.setText("已选择" + (checked ? "辅助 20×" : "正常 1×") + "，请彻底退出并重新打开应用后开始游戏。");
            } catch (Exception error) { showFailure("保存伤害设置失败", error);
                syncingDamage = true; damageSwitch.setChecked(!checked); syncingDamage = false; }
        });
        backupInfo = new TextView(this); backupInfo.setTextSize(14); backupInfo.setTextIsSelectable(true); panel.addView(backupInfo);
        exportButton = new Button(this); exportButton.setText("导出当前存档"); panel.addView(exportButton);
        exportButton.setOnClickListener(view -> requestExport());
        exportInfo = new TextView(this); exportInfo.setTextSize(14); exportInfo.setTextIsSelectable(true); panel.addView(exportInfo);
        startButton = new Button(this); startButton.setText("开始游戏"); panel.addView(startButton);
        startButton.setOnClickListener(view -> requestStart());
        scroll.addView(panel);
        LinearLayout screen = new LinearLayout(this); screen.setOrientation(LinearLayout.VERTICAL);
        countdown = new TextView(this); countdown.setTextSize(17); countdown.setTextColor(0xffffd580);
        countdown.setPadding(dp(24), dp(12), dp(24), dp(12)); countdown.setVisibility(android.view.View.GONE);
        screen.addView(countdown);
        screen.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1)); setContentView(screen);
    }
    private void controls() {
        boolean enabled = ready && !busy && !blocked;
        damageSwitch.setEnabled(enabled);
        resourceButton.setEnabled(enabled); saveButton.setEnabled(enabled); startButton.setEnabled(enabled);
        exportButton.setEnabled(enabled && store != null && store.account().isFile());
    }
    private void refreshChoices() throws Exception {
        JSONObject chosen = store.choices();
        syncingDamage = true; damageSwitch.setChecked(chosen.optBoolean("damage_boost", true)); syncingDamage = false;
        boolean resourcesPresent = new File(getFilesDir(), "embedded-resources.ready").isFile();
        boolean resourceChosen = !chosen.optString("resource_uri").isEmpty();
        resourceButton.setText(resourceChosen || resourcesPresent ? "重选资源包" : "选择资源包");
        if (resourceChosen) resourceFile.setText(chosen.optString("resource_name") + "\n位置：" + chosen.optString("resource_path")
                + (chosen.optBoolean("resource_pending") ? "\n待校验" : ""));
        else if (resourcesPresent) resourceFile.setText("已导入的离线视频资源\n原选择文件名未记录\n位置：…/files/assets/Video");
        else resourceFile.setText("尚未选择\n请选择配套视频 ZIP");
        boolean pending = store.pendingSave(), accountPresent = store.account().isFile();
        saveButton.setText(pending || accountPresent ? "重选存档" : "选择存档");
        if (!chosen.optString("save_name").isEmpty()) saveFile.setText(chosen.optString("save_name") + "\n位置：" + chosen.optString("save_path")
                + (pending ? "\n待导入，现有进度未改变" : ""));
        else if (accountPresent) saveFile.setText("account.json（当前存档）\n原选择文件名未记录\n位置：…/files/formal-data/account.json");
        else saveFile.setText("尚未选择\n请选择服务端 JSON 存档");
        String backup = chosen.optString("last_backup_path");
        backupInfo.setText(backup.isEmpty() ? "" : "最近保留的旧档备份：\n" + backup + "\n卸载应用会删除，请自行复制到其他位置保存。");
        String exported = chosen.optString("last_export_name");
        exportInfo.setText(exported.isEmpty() ? "" : "最近导出：" + exported + "\n位置：" + chosen.optString("last_export_path"));
        controls();
    }
    private void choose(int request) {
        if (!ready || busy || blocked) return;
        Intent picker = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        picker.addCategory(Intent.CATEGORY_OPENABLE); picker.setType("*/*");
        picker.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);
        startActivityForResult(picker, request);
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
                refreshChoices(); status.setText("资源包已选择，点击“开始游戏”后校验。" + (persisted ? "" : "本文件授权可能只在本次有效。"));
            } catch (Exception error) { showFailure("资源包选择失败", error); }
            return;
        }
        busy = true; controls(); status.setText("正在校验所选存档，现有进度保持不变……");
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
                    try { refreshChoices(); status.setText("存档已选择，尚未替换当前进度。点击“开始游戏”时确认导入。"); }
                    catch (Exception error) { showFailure("读取选择记录失败", error); }
                });
            } catch (Exception error) { main.post(() -> { busy = false; showFailure("存档选择失败", error); }); }
        }, "launcher-select-save").start();
    }
    private void requestExport() {
        if (!ready || busy || blocked) return;
        if (serverRunning()) { status.setText("请先退出游戏并从最近任务划掉，再导出当前完整进度。"); return; }
        Intent create = new Intent(Intent.ACTION_CREATE_DOCUMENT);
        create.addCategory(Intent.CATEGORY_OPENABLE); create.setType("application/json");
        String stamp = new java.text.SimpleDateFormat("yyyyMMdd-HHmmss", java.util.Locale.ROOT).format(new java.util.Date());
        create.putExtra(Intent.EXTRA_TITLE, "bh3-save-" + stamp + ".json");
        create.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
        startActivityForResult(create, 21);
    }
    private void exportTo(Uri target) {
        if (serverRunning()) { status.setText("服务端正在运行，未导出；请退出游戏后重试。"); return; }
        busy = true; controls(); status.setText("正在导出当前存档……");
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
                    try { refreshChoices(); status.setText("已导出当前存档" + (checked ? "并校验一致" : "（此位置不支持回读校验）") + "：" + name + "\n位置：" + path); }
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
    private void requestStart() {
        if (!ready || busy || blocked) return;
        try {
            if (!store.account().isFile() && !store.pendingSave()) { status.setText("请先选择自己的服务端 JSON 存档。"); return; }
            JSONObject selected = store.choices();
            DamageMode.requireCanApply(this, selected.optBoolean("damage_boost", true) ? 20 : 1);
            if ((store.pendingSave() || selected.optBoolean("resource_pending")) && serverRunning()) {
                status.setText("服务端仍在运行。请退出游戏并从最近任务划掉后，再应用重选的文件。"); return;
            }
            if (store.pendingSave() && store.account().isFile()) {
                new AlertDialog.Builder(this).setTitle("确认替换当前存档")
                    .setMessage("将导入“" + selected.optString("save_name") + "”并替换当前进度。\n\n请选择是否保留旧档备份。\n备份位置：\n"
                        + (backupRoot() == null ? "当前不可用" : backupRoot().getAbsolutePath() + "/<时间>/account.json")
                        + "\n\n该目录随卸载应用删除；建议用文件管理器另行复制保存。选择不备份，导入成功后不保留本次旧档。")
                    .setNegativeButton("取消", null)
                    .setNeutralButton("不备份导入", (dialog, which) -> beginStart(false))
                    .setPositiveButton("备份并导入", (dialog, which) -> beginStart(true)).show();
            } else beginStart(false);
        } catch (Exception error) { showFailure("无法开始", error); }
    }
    private File backupRoot() {
        File external = getExternalFilesDir(null);
        return external == null ? null : new File(external, "save-backups");
    }
    private void beginStart(final boolean keepBackup) {
        if (busy || blocked || isFinishing() || isDestroyed()) return;
        busy = true; starting = true; controls(); status.setText("正在准备离线资源，请稍候……");
        android.util.Log.i("Server19Launcher", "Start button accepted");
        new Thread(() -> {
            try {
                JSONObject selected = store.choices();
                Uri remembered = selected.optString("resource_uri").isEmpty() ? null : Uri.parse(selected.getString("resource_uri"));
                Uri source = selected.optBoolean("resource_pending") ? remembered : null;
                EmbeddedResources.Progress progress = text -> main.post(() -> status.setText(text));
                try { EmbeddedResources.prepare(this, source, progress); }
                catch (EmbeddedResources.VideoRequired missing) {
                    if (remembered == null || source != null) throw missing;
                    EmbeddedResources.prepare(this, remembered, progress);
                }
                if (isFinishing() || isDestroyed()) return;
                store.resourcePrepared(remembered == null ? "" : remembered.toString());
                if (store.pendingSave() && serverRunning()) throw new IOException("服务端仍在运行，未替换存档");
                DamageMode.apply(this, selected.optBoolean("damage_boost", true) ? 20 : 1);
                store.commitPendingSave(keepBackup, backupRoot());
                main.post(() -> {
                    try { refreshChoices(); startServer(); }
                    catch (Exception error) { busy = false; starting = false; showFailure("启动失败", error); }
                });
            } catch (EmbeddedResources.VideoRequired missing) {
                main.post(() -> { busy = false; starting = false; controls(); status.setText("需要配套离线视频 ZIP，请先选择资源包，再点击“开始游戏”。"); });
            } catch (Exception error) { main.post(() -> { busy = false; starting = false; showFailure("准备失败", error); }); }
        }, "launcher-prepare").start();
    }
    private void showFailure(String action, Exception error) {
        android.util.Log.e("Server19Launcher", action, error); controls(); status.setText(action + "：" + error.getMessage());
    }
    private void startServer() {
        if (isFinishing() || isDestroyed() || !starting) return;
        if (getIntent().getBooleanExtra("prepare_only", false)) {
            busy = false; starting = false; controls();
            status.setText("离线资源准备及校验完成。尚未启动游戏或服务端。");
            android.util.Log.i("Server19Resources", "Private resources ready; uid=" + android.os.Process.myUid()); return;
        }
        status.setText("离线资源已就绪，正在启动服务端……");
        Intent service = new Intent(this, IntegratedService.class);
        if (Build.VERSION.SDK_INT >= 26) startForegroundService(service); else startService(service);
        bound = bindService(service, connection, BIND_AUTO_CREATE);
        main.postDelayed(() -> { if (starting && !leaving) status.setText("服务端尚未就绪，请保留现场并反馈。"); }, 30000);
    }
    private final Messenger reply = new Messenger(new Handler(Looper.getMainLooper(), msg -> {
        if (msg.what == 2 && starting && !leaving && !isFinishing()) {
            busy = false; starting = false; blocked = true; controls();
            status.setText("服务端启动失败：" + msg.getData().getString("error", "未知错误") + "\n请退出应用后重试，或保留现场反馈。");
        }
        if (msg.what == 1 && starting && !leaving && !isFinishing()) {
            if (getIntent().getBooleanExtra("server_only", false)) {
                busy = false; starting = false; controls(); status.setText("服务端已就绪（技术检查，未启动游戏）。");
                return true;
            }
            leaving = true; Intent game = new Intent();
            game.setClassName(getPackageName(), "com.miHoYo.overridenativeactivity.OverrideNativeActivity");
            startActivity(game); finish();
        }
        return true;
    }));
    private final ServiceConnection connection = new ServiceConnection() {
        @Override public void onServiceConnected(ComponentName name, IBinder binder) {
            Message request = Message.obtain(null, 1); request.replyTo = reply;
            try { new Messenger(binder).send(request); }
            catch (RemoteException error) { status.setText("服务端连接失败，请保留现场并反馈。"); }
        }
        @Override public void onServiceDisconnected(ComponentName name) {
            busy = false; starting = false; controls(); status.setText("服务端已停止，请保留现场并反馈。");
        }
    };
    @Override public void onCreate(Bundle state) {
        super.onCreate(state); store = new LauncherStore(getFilesDir()); preparationPanel();
        try { store.recover(); refreshChoices(); }
        catch (Exception error) { blocked = true; showFailure("读取或恢复启动记录失败", error); return; }
        countdown.setVisibility(android.view.View.VISIBLE);
        countdown.setText("请阅读以上说明，5 秒后可开始游戏……");
        noticeTimer = new CountDownTimer(5000, 1000) {
            @Override public void onTick(long remaining) { countdown.setText("请阅读以上说明，" + ((remaining + 999) / 1000) + " 秒后可开始游戏……"); }
            @Override public void onFinish() {
                if (isFinishing() || isDestroyed()) return;
                countdown.setVisibility(android.view.View.GONE);
                ready = true; controls(); status.setText("请确认资源包和存档后，点击“开始游戏”。");
                android.util.Log.i("Server19Notice", "Countdown finished at " + SystemClock.elapsedRealtime());
            }
        };
        android.util.Log.i("Server19Notice", "Countdown started at " + SystemClock.elapsedRealtime()); noticeTimer.start();
    }
    @Override public void onDestroy() {
        if (noticeTimer != null) noticeTimer.cancel();
        if (bound) unbindService(connection);
        main.removeCallbacksAndMessages(null); super.onDestroy();
    }
}
