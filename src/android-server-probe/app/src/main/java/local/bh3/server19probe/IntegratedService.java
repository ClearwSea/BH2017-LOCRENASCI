package local.bh3.server19probe;

import android.content.Intent;
import android.os.*;
import java.util.ArrayList;

/** Same Python host; readiness IPC never starts gameplay from the service. */
public class IntegratedService extends ProbeService {
    private boolean ready;
    private String failure;
    private final ArrayList<Messenger> waiting = new ArrayList<>();
    private final Handler main = new Handler(Looper.getMainLooper());
    private void reply(Messenger client) {
        try { Message response = Message.obtain(null, failure == null ? 1 : 2);
            if (failure != null) { Bundle data = new Bundle(); data.putString("error", failure); response.setData(data); }
            client.send(response); }
        catch (RemoteException ignored) { }
    }
    private final Messenger endpoint = new Messenger(new Handler(Looper.getMainLooper(), msg -> {
        if (msg.what == 1 && msg.replyTo != null) {
            if (ready || failure != null) reply(msg.replyTo); else waiting.add(msg.replyTo);
        }
        return true;
    }));
    @Override protected void onServerReady() {
        main.post(() -> { if (stopping) return; ready = true; for (Messenger client : waiting) reply(client); waiting.clear(); });
    }
    @Override protected void onServerFailed(String error) {
        main.post(() -> { if (stopping) return; failure = error; ready = false;
            for (Messenger client : waiting) reply(client); waiting.clear(); });
    }
    @Override public void onTaskRemoved(Intent rootIntent) {
        if (stopping) return;
        stopping = true;
        ready = false;
        waiting.clear();
        android.util.Log.i("Server19Lifecycle", "Game task removed; draining server");
        new Thread(() -> {
            synchronized (runtimeLock) {
                try {
                    if (com.chaquo.python.Python.isStarted())
                        com.chaquo.python.Python.getInstance().getModule("server_entry").callAttr("stop");
                } catch (Throwable error) {
                    android.util.Log.e("Server19Lifecycle", "Server shutdown failed", error);
                }
            }
            main.post(() -> { stopForeground(true); stopSelf(); });
        }, "server19-stop").start();
    }
    @Override public IBinder onBind(Intent intent) { return endpoint.getBinder(); }
}
