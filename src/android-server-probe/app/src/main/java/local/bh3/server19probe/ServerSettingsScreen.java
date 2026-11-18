package local.bh3.server19probe;

import android.app.Activity;
import android.app.AlertDialog;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import org.json.JSONArray;
import org.json.JSONObject;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Native settings for the supported offline server controls. */
final class ServerSettingsScreen {
    interface Backend {
        JSONObject load() throws Exception;
        void save(JSONObject value) throws Exception;
        void close() throws Exception;
    }
    private final Activity activity;
    private final Backend backend;
    private final Runnable exit;
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private final Handler main = new Handler(Looper.getMainLooper());
    private JSONObject value, original;
    private boolean busy, closed;
    ServerSettingsScreen(Activity activity, Backend backend, Runnable exit) {
        this.activity = activity; this.backend = backend; this.exit = exit;
    }
    private int dp(int n) { return (int)(n * activity.getResources().getDisplayMetrics().density + .5f); }
    private LinearLayout column() { LinearLayout v = new LinearLayout(activity); v.setOrientation(LinearLayout.VERTICAL); return v; }
    private TextView label(String s, int size, int color, boolean bold) {
        TextView v = new TextView(activity); v.setText(s); v.setTextSize(size); v.setTextColor(color);
        if (bold) v.setTypeface(Typeface.DEFAULT, Typeface.BOLD); return v;
    }
    private TextView button(String s, Runnable action) {
        TextView v = label(s, 15, 0xffe2e9ef, true); v.setPadding(dp(15), dp(13), dp(15), dp(13));
        GradientDrawable b = new GradientDrawable(); b.setColor(0xff202327); b.setCornerRadius(dp(10)); b.setStroke(dp(1), 0xff393e44);
        v.setBackground(b); v.setOnClickListener(w -> action.run()); return v;
    }
    private void add(LinearLayout parent, View view, int margin) {
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(-1, -2); p.topMargin = dp(margin); parent.addView(view, p);
    }
    private boolean dirty() {
        return value != null && original != null &&
            (!value.optString("abyss_temperature", "null").equals(original.optString("abyss_temperature", "null")) ||
             !value.optString("next_bosses", "null").equals(original.optString("next_bosses", "null")));
    }
    void show() {
        busy = true; render();
        worker.execute(() -> {
            try {
                JSONObject loaded = backend.load();
                if (loaded.getLong("effective_begin") <= 0 || loaded.getInt("temperature_min") < 0 ||
                        loaded.getInt("temperature_max") < loaded.getInt("temperature_min") ||
                        loaded.getJSONArray("bosses").length() < 3 ||
                        !loaded.has("abyss_temperature") || !loaded.has("next_bosses"))
                    throw new IllegalArgumentException("服务端设置数据不完整");
                main.post(() -> { if (!closed) try {
                    value = loaded; original = new JSONObject(loaded.toString()); busy = false; render();
                } catch (Exception e) { fail(e); } });
            } catch (Exception e) { main.post(() -> fail(e)); }
        });
    }
    void close() {
        if (busy) return;
        if (dirty()) new AlertDialog.Builder(activity).setTitle("放弃未保存的设置？")
            .setNegativeButton("继续调整", null).setPositiveButton("放弃", (d,w) -> finish()).show();
        else finish();
    }
    private void finish() { destroy(); exit.run(); }
    void destroy() {
        if (closed) return;
        closed = true;
        worker.execute(() -> { try { backend.close(); } catch (Exception e) { android.util.Log.e("ServerSettings", "close", e); } });
        worker.shutdown();
    }
    private void fail(Exception error) {
        if (closed) return;
        busy = false; render();
        new AlertDialog.Builder(activity).setTitle("操作未完成")
            .setMessage(error.getMessage() == null ? error.toString() : error.getMessage()).setPositiveButton("知道了", null).show();
    }
    private String date(long seconds) {
        SimpleDateFormat f = new SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.CHINA);
        f.setTimeZone(TimeZone.getTimeZone("Asia/Shanghai")); return f.format(new Date(seconds * 1000));
    }
    private String selectedBosses() {
        JSONArray selected = value.optJSONArray("next_bosses"), all = value.optJSONArray("bosses");
        if (selected == null) return "自动轮换";
        StringBuilder result = new StringBuilder();
        for (int i = 0; i < selected.length(); i++) {
            int id = selected.optInt(i); String name = Integer.toString(id);
            if (all != null) for (int j = 0; j < all.length(); j++) {
                JSONObject boss = all.optJSONObject(j);
                if (boss != null && boss.optInt("id") == id) { name = boss.optString("name", name); break; }
            }
            if (result.length() > 0) result.append("、"); result.append(name);
        }
        return result.toString();
    }
    void render() {
        if (closed) return;
        LinearLayout root = column(); root.setPadding(dp(16), dp(12), dp(16), dp(12)); root.setBackgroundColor(0xff101113);
        activity.setContentView(root);
        LinearLayout header = new LinearLayout(activity); header.setGravity(Gravity.CENTER_VERTICAL);
        header.addView(button("‹ 返回", this::close)); TextView title = label("服务端调整", 20, 0xffe9edf0, true); title.setPadding(dp(14), 0, 0, 0);
        header.addView(title, new LinearLayout.LayoutParams(0, -2, 1)); add(root, header, 0);
        ScrollView scroll = new ScrollView(activity); LinearLayout body = column(); scroll.addView(body);
        root.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));
        if (busy) { add(body, label("正在读取，请稍候…", 15, 0xff9ba4af, false), 24); return; }
        if (value == null) { add(body, label("无法读取服务端设置。", 14, 0xffd8b1ad, false), 20); return; }
        add(body, label("记忆战场", 18, 0xffe9edf0, true), 20);
        add(body, button("下期 Boss：" + selectedBosses() + "  ›", this::bossDialog), 10);
        add(body, label("下期开始：" + date(value.optLong("effective_begin")) + "（北京时间）；当前期的进度与奖励保持原样。", 13, 0xff9ba4af, false), 8);
        add(body, label("深渊", 18, 0xffe9edf0, true), 24);
        String temp = value.isNull("abyss_temperature") ? "自动" : Integer.toString(value.optInt("abyss_temperature"));
        add(body, button("温度：" + temp + "  ›", this::temperatureDialog), 10);
        add(body, label("固定温度影响玩家界面和战斗难度；本期模拟对手仍沿用原模型。", 13, 0xff9ba4af, false), 8);
        add(body, label("设置在下次启动游戏时生效。", 13, 0xff9ba4af, false), 20);
        if (dirty()) add(root, button("保存设置", this::save), 12);
    }
    private void bossDialog() {
        JSONArray all = value.optJSONArray("bosses"), selected = value.optJSONArray("next_bosses");
        if (all == null || all.length() == 0) return;
        String[] names = new String[all.length()]; boolean[] checked = new boolean[all.length()];
        for (int i = 0; i < all.length(); i++) {
            JSONObject boss = all.optJSONObject(i);
            if (boss == null || boss.optInt("id") <= 0) { fail(new IllegalArgumentException("Boss 列表数据不完整")); return; }
            names[i] = boss.optString("name", Integer.toString(boss.optInt("id")));
            for (int j = 0; selected != null && j < selected.length(); j++) if (selected.optInt(j) == boss.optInt("id")) checked[i] = true;
        }
        new AlertDialog.Builder(activity).setTitle("选择下期三名 Boss")
            .setMultiChoiceItems(names, checked, (d, index, isChecked) -> checked[index] = isChecked)
            .setNeutralButton("自动轮换", (d,w) -> { try { value.put("next_bosses", JSONObject.NULL); render(); } catch (Exception e) { fail(e); } })
            .setNegativeButton("取消", null).setPositiveButton("确定", (d,w) -> {
                try {
                    JSONArray ids = new JSONArray();
                    for (int i = 0; i < checked.length; i++) if (checked[i]) ids.put(all.getJSONObject(i).getInt("id"));
                    if (ids.length() != 3) throw new IllegalArgumentException("请选择三名不同的 Boss");
                    value.put("next_bosses", ids); render();
                } catch (Exception e) { fail(e); }
            }).show();
    }
    private void temperatureDialog() {
        EditText field = new EditText(activity); field.setInputType(InputType.TYPE_CLASS_NUMBER);
        if (!value.isNull("abyss_temperature")) field.setText(value.optString("abyss_temperature"));
        new AlertDialog.Builder(activity).setTitle("固定深渊温度")
            .setMessage("允许范围：" + value.optInt("temperature_min") + "–" + value.optInt("temperature_max"))
            .setView(field).setNeutralButton("自动", (d,w) -> { try { value.put("abyss_temperature", JSONObject.NULL); render(); } catch (Exception e) { fail(e); } })
            .setNegativeButton("取消", null).setPositiveButton("确定", (d,w) -> {
                try {
                    int n;
                    try { n = Integer.parseInt(field.getText().toString().trim()); }
                    catch (NumberFormatException e) { throw new IllegalArgumentException("请输入允许范围内的整数"); }
                    if (n < value.getInt("temperature_min") || n > value.getInt("temperature_max")) throw new IllegalArgumentException("温度不在允许范围内");
                    value.put("abyss_temperature", n); render();
                } catch (Exception e) { fail(e); }
            }).show();
    }
    private void save() {
        try {
            JSONObject copy = new JSONObject(value.toString()); busy = true; render();
            worker.execute(() -> {
                try { backend.save(copy); main.post(() -> { if (!closed) try {
                    original = new JSONObject(copy.toString()); busy = false; render();
                    new AlertDialog.Builder(activity).setMessage("设置已保存，下次启动游戏时生效。") .setPositiveButton("确定", null).show();
                } catch (Exception e) { fail(e); } }); }
                catch (Exception e) { main.post(() -> fail(e)); }
            });
        } catch (Exception e) { fail(e); }
    }
}
