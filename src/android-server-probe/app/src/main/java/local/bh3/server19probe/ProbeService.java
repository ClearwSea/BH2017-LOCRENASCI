package local.bh3.server19probe;

import android.app.Service;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.content.Intent;
import android.os.IBinder;
import android.util.Log;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

/** 独立服务；不启动游戏 / Standalone service; never starts the game. */
public class ProbeService extends Service {
    private boolean started = false;
    protected volatile boolean stopping;
    protected final Object runtimeLock = new Object();
    protected void onServerReady() { }
    protected void onServerFailed(String error) { }
    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        if (started) return START_NOT_STICKY;
        final boolean probe = intent != null && "probe".equals(intent.getStringExtra("mode"));
        final boolean benchmark = intent != null && "benchmark".equals(intent.getStringExtra("mode"));
        NotificationManager manager = getSystemService(NotificationManager.class);
        manager.createNotificationChannel(new NotificationChannel("probe", "ARM32 server test", NotificationManager.IMPORTANCE_LOW));
        startForeground(19, new Notification.Builder(this, "probe")
            .setSmallIcon(android.R.drawable.stat_notify_sync)
            .setContentTitle(probe ? "ARM32 隔离测试" : "崩坏3手机服务端")
            .setContentText("正在启动，请稍候").build());
        if (!started) {
            started = true;
            new Thread(() -> {
                synchronized (runtimeLock) {
                try {
                    if (stopping) return;
                    if (!Python.isStarted()) Python.start(PythonPlatform.create(this));
                    String report = Python.getInstance().getModule(benchmark ? "benchmark_entry" : probe ? "probe_entry" : "server_entry")
                        .callAttr("run", this).toString();
                    Log.i("Server19Probe", report);
                    if (benchmark) { stopSelf(); return; }
                    if (stopping) return;
                    onServerReady();
                    manager.notify(19, new Notification.Builder(this, "probe")
                        .setSmallIcon(android.R.drawable.stat_notify_sync)
                        .setContentTitle(probe ? "隔离测试已完成" : "手机服务端已就绪")
                        .setContentText(probe ? "测试账户" : "可打开游戏，无需电脑连接")
                        .setOngoing(true).build());
                } catch (Throwable error) {
                    Log.e("Server19Probe", "Probe failed", error);
                    try (java.io.PrintWriter writer = new java.io.PrintWriter(new java.io.File(getFilesDir(), "server-start-error.txt"), "UTF-8")) {
                        error.printStackTrace(writer);
                    } catch (java.io.IOException ignored) { }
                    onServerFailed(error.getClass().getSimpleName() + ": " + error.getMessage());
                    manager.notify(20, new Notification.Builder(this, "probe")
                        .setSmallIcon(android.R.drawable.stat_notify_error)
                        .setContentTitle("服务端启动失败")
                        .setContentText("请保留现场并反馈，诊断日志已保存").build());
                    stopSelf();
                }
                }
            }, "server19-probe").start();
        }
        return START_NOT_STICKY;
    }
    @Override public IBinder onBind(Intent intent) { return null; }
    @Override public void onDestroy() {
        // Stop only this separate server process; the game process is independent.
        super.onDestroy();
        android.os.Process.killProcess(android.os.Process.myPid());
    }
}
