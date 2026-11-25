package local.bh3.server19probe;

import android.content.Context;
import android.os.SystemClock;
import android.webkit.JavascriptInterface;
import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.util.UUID;

final class GmMailbox {
    private static final Object LOCK = new Object();
    private final File directory;

    GmMailbox(Context context) {
        directory = new File(context.getFilesDir(), "gm-mailbox");
    }

    @JavascriptInterface public String request(String body) {
        synchronized (LOCK) {
            try {
                if (body.length() > 2048) throw new IllegalArgumentException();
                JSONObject command = new JSONObject(body);
                String nonce = UUID.randomUUID().toString();
                command.put("nonce", nonce);
                command.put("expires", System.currentTimeMillis() + 5000);
                directory.mkdirs();
                File pending = new File(directory, "request.json");
                File temporary = new File(directory, "request.tmp");
                File reply = new File(directory, "reply.json");
                try (FileOutputStream out = new FileOutputStream(temporary)) {
                    out.write(command.toString().getBytes("UTF-8"));
                }
                if (!temporary.renameTo(pending)) throw new IllegalStateException();
                long deadline = SystemClock.elapsedRealtime() + 6000;
                while (SystemClock.elapsedRealtime() < deadline) {
                    if (reply.isFile()) {
                        byte[] chunk = new byte[1024];
                        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
                        try (FileInputStream in = new FileInputStream(reply)) {
                            int read;
                            while ((read = in.read(chunk)) != -1) bytes.write(chunk, 0, read);
                        }
                        JSONObject result = new JSONObject(bytes.toString("UTF-8"));
                        if (nonce.equals(result.optString("nonce"))) {
                            reply.delete();
                            return result.toString();
                        }
                    }
                    SystemClock.sleep(70);
                }
                return error("游戏未返回结果。请重新打开 GM 核对操作是否生效。");
            } catch (Exception error) {
                return error("GM 暂时无法与本地游戏通信");
            }
        }
    }

    private String error(String message) {
        return "{\"ok\":false,\"message\":" + JSONObject.quote(message) + "}";
    }
}
