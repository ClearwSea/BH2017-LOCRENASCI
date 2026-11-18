package local.bh3.server19probe;

import android.app.Activity;
import android.app.AlertDialog;
import android.graphics.Color;
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
import android.widget.Spinner;
import android.widget.ArrayAdapter;
import android.widget.AdapterView;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Iterator;
import java.util.LinkedHashSet;
import java.util.HashMap;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** A working-copy editor; the backend owns persistence, locking and validation. */
final class SaveEditorScreen {
    interface Backend {
        JSONArray sources() throws Exception;
        JSONObject load(String sourceId) throws Exception;
        JSONObject create(long uid, String templateKind) throws Exception;
        JSONObject apply(JSONObject account, JSONObject operation) throws Exception;
        void save(JSONObject account) throws Exception;
        void close() throws Exception;
    }

    private final Activity activity;
    private final Backend backend;
    private final Runnable exit;
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private final Handler main = new Handler(Looper.getMainLooper());
    private JSONObject original, account, catalog;
    private JSONArray capabilities;
    private JSONArray sources;
    private LinearLayout body;
    private String page = "sources";
    private String search = "";
    private int selectedId;
    private int selectedUid;
    private String stageKind = "story";
    private int stageDifficulty = -1, stageChapter = -1, stageId = -1;
    private int sakuraCycle = -1, sakuraId = -1;
    private final HashMap<String, String> texts = new HashMap<>();
    private boolean busy;
    private volatile boolean closed;
    private String sourceTitle = "";

    SaveEditorScreen(Activity activity, Backend backend, Runnable exit) {
        this.activity = activity;
        this.backend = backend;
        this.exit = exit;
    }

    void show() {
        if (closed) return;
        busy = true;
        render();
        worker.execute(() -> {
            try {
                JSONArray available = backend.sources();
                main.post(() -> { if (!closed) { sources = available; busy = false; render(); } });
            } catch (Exception e) { main.post(() -> fail(e)); }
        });
    }

    private void load(String sourceId) {
        if (sources != null) for (int i = 0; i < sources.length(); i++) {
            JSONObject entry = sources.optJSONObject(i);
            if (entry != null && sourceId.equals(entry.optString("id"))) sourceTitle = entry.optString("title", sourceId);
        }
        busy = true; render();
        worker.execute(() -> {
            try {
                JSONObject result = backend.load(sourceId);
                JSONObject loaded = copy(result.getJSONObject("account"));
                JSONObject tables = result.optJSONObject("catalog");
                JSONArray supported = result.optJSONArray("capabilities");
                main.post(() -> {
                    if (closed) return;
                    try {
                        original = copy(loaded);
                        account = loaded;
                        catalog = tables == null ? new JSONObject() : tables;
                        texts.clear();
                        JSONArray textmap = catalog.optJSONArray("textmap");
                        if (textmap != null) for (int i = 0; i < textmap.length(); i++) {
                            JSONObject row = textmap.optJSONObject(i);
                            if (row != null) texts.put(row.optString("ID"), row.optString("Text"));
                        }
                        capabilities = supported;
                        page = "home";
                        busy = false;
                        render();
                    } catch (JSONException e) { fail(e); }
                });
            } catch (Exception e) { main.post(() -> fail(e)); }
        });
    }

    void close() {
        if (closed || busy) return;
        if (dirty()) {
            new AlertDialog.Builder(activity).setTitle("放弃未保存的修改？")
                .setMessage("尚未保存的编辑将会丢失。")
                .setNegativeButton("继续编辑", null).setPositiveButton("放弃修改", (d, w) -> finish()).show();
        } else finish();
    }

    private void finish() { if (!closed) { destroy(); exit.run(); } }

    /** Stop callbacks immediately; release the backend only after any active transaction. */
    void destroy() {
        if (closed) return;
        closed = true;
        worker.execute(() -> {
            try { backend.close(); }
            catch (Exception error) { android.util.Log.e("SaveEditor", "Failed to close editor backend", error); }
        });
        worker.shutdown();
    }
    private static JSONObject copy(JSONObject value) throws JSONException { return new JSONObject(value.toString()); }
    private int dp(float n) { return (int) (n * activity.getResources().getDisplayMetrics().density + .5f); }
    private boolean dirty() { return original != null && account != null && !original.toString().equals(account.toString()); }
    private boolean has(String operation) {
        if (capabilities == null) return false;
        for (int i = 0; i < capabilities.length(); i++) if (operation.equals(capabilities.optString(i))) return true;
        return false;
    }
    private GradientDrawable shape(int color) {
        GradientDrawable b = new GradientDrawable(); b.setColor(color); b.setCornerRadius(dp(10)); b.setStroke(dp(1), 0xff393e44); return b;
    }
    private LinearLayout column() { LinearLayout l = new LinearLayout(activity); l.setOrientation(LinearLayout.VERTICAL); return l; }
    private TextView label(String text, int size, int color, boolean bold) {
        TextView t = new TextView(activity); t.setText(text); t.setTextSize(size); t.setTextColor(color);
        if (bold) t.setTypeface(Typeface.DEFAULT, Typeface.BOLD); return t;
    }
    private void add(LinearLayout parent, View child, int margin) {
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(-1, -2); p.topMargin = dp(margin); parent.addView(child, p);
    }
    private TextView button(String text, Runnable action) {
        TextView t = label(text, 15, 0xffd9e3eb, true); t.setPadding(dp(14), dp(13), dp(14), dp(13));
        t.setBackground(shape(0xff202327)); t.setOnClickListener(v -> action.run()); return t;
    }
    private LinearLayout card() {
        LinearLayout v = column(); v.setPadding(dp(16), dp(14), dp(16), dp(14)); v.setBackground(shape(0xff1b1d21)); return v;
    }

    void render() {
        if (closed) return;
        LinearLayout root = column(); root.setBackgroundColor(0xff101113); root.setPadding(dp(16), dp(12), dp(16), dp(12));
        activity.setContentView(root);
        LinearLayout header = new LinearLayout(activity); header.setGravity(Gravity.CENTER_VERTICAL);
        TextView back = button("‹ 返回", () -> {
            if ("avatar_detail".equals(page)) page = "avatars";
            else if ("equipment_detail".equals(page)) page = "equipment";
            else if ("sources".equals(page)) { close(); return; }
            else if (!"home".equals(page)) { page = "home"; search = ""; }
            else { close(); return; }
            render();
        });
        header.addView(back); TextView title = label("存档编辑", 20, 0xffe9edf0, true); title.setPadding(dp(14), 0, 0, 0);
        header.addView(title, new LinearLayout.LayoutParams(0, -2, 1));
        TextView status = label(dirty() ? "有未保存修改" : "", 12, 0xffe3c397, false); header.addView(status); add(root, header, 0);
        ScrollView scroll = new ScrollView(activity); body = column(); scroll.addView(body);
        root.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));
        if (busy) { add(body, label("正在处理，请稍候…", 15, 0xff9ba4af, false), 24); return; }
        if ("sources".equals(page)) { sourceList(); return; }
        if (account == null) { add(body, label("无法读取当前存档。", 15, 0xffd8b1ad, false), 24); return; }
        switch (page) {
            case "captain": captain(); break;
            case "avatars": avatars(); break;
            case "avatar_detail": avatarDetail(); break;
            case "materials": materials(); break;
            case "costumes": costumes(); break;
            case "equipment": equipment(); break;
            case "equipment_detail": equipmentDetail(); break;
            case "equipment_add": equipmentAdd(); break;
            case "story": story(); break;
            case "sakura": sakura(); break;
            case "abyss": abyss(); break;
            case "cabins": cabins(); break;
            case "templates": templates(); break;
            default: home(); break;
        }
        if (dirty()) add(root, button("查看修改并保存", this::preview), 12);
    }

    private void home() {
        add(body, label("当前存档 · " + sourceTitle, 13, 0xff9ba4af, true), 20);
        LinearLayout intro = card();
        add(intro, label("编辑后先预览变更，再保存到当前存档。", 14, 0xffd0d4d9, false), 0);
        add(body, intro, 10);
        add(body, button("选择其他存档  ›", () -> {
            if (!dirty()) { page = "sources"; render(); return; }
            new AlertDialog.Builder(activity).setTitle("放弃未保存的修改？").setMessage("切换存档将丢弃当前工作副本。")
                .setNegativeButton("继续编辑", null).setPositiveButton("切换存档", (d, w) -> { account = original = null; page = "sources"; render(); }).show();
        }), 10);
        if (has("captain")) add(body, button("舰长资料与资源  ›", () -> { page = "captain"; render(); }), 12);
        if (has("avatar")) add(body, button("女武神与技能  ›", () -> { page = "avatars"; render(); }), 12);
        if (has("material")) add(body, button("材料与道具  ›", () -> { page = "materials"; render(); }), 12);
        if (has("costume")) add(body, button("服装  ›", () -> { page = "costumes"; render(); }), 12);
        if (has("equipment_edit")) add(body, button("武器与圣痕  ›", () -> { page = "equipment"; render(); }), 12);
        if (has("story_unlock")) add(body, button("剧情与外传  ›", () -> { page = "story"; render(); }), 12);
        if (has("sakura_set_part")) add(body, button("樱色轮回  ›", () -> { page = "sakura"; render(); }), 12);
        if (has("abyss_set")) add(body, button("深渊  ›", () -> { page = "abyss"; render(); }), 12);
        if (has("cabin")) add(body, button("家园与宿舍  ›", () -> { page = "cabins"; render(); }), 12);
        if (has("template")) add(body, button("存档模板  ›", () -> { page = "templates"; render(); }), 12);
    }
    private void templates() {
        add(body, label("存档模板", 18, 0xffe9edf0, true), 20);
        add(body, label("模板会替换当前工作副本；可先预览变更，再决定是否保存。", 14, 0xff9ba4af, false), 12);
        String[][] options = {{"starter", "新号 · 无首登"}, {"starter_first_login", "新号 · 首登"}, {"full_level", "满级号 · 全角色、全皮肤、全部关卡满星"}};
        for (String[] option : options) add(body, button(option[1] + "  ›", () -> {
            new AlertDialog.Builder(activity).setTitle("应用" + option[1] + "？")
                .setMessage("这会替换当前未保存的工作副本。")
                .setNegativeButton("取消", null).setPositiveButton("应用", (d, w) -> {
                    try { apply(new JSONObject().put("op", "template").put("kind", option[0])); }
                    catch (Exception e) { fail(e); }
                }).show();
        }), 10);
    }
    private void sourceList() {
        add(body, label("选择要编辑的存档", 18, 0xffe9edf0, true), 20);
        add(body, button("新建存档  ›", this::createDialog), 10);
        if (sources == null || sources.length() == 0) {
            add(body, label("没有可读取的存档。", 14, 0xff9ba4af, false), 12); return;
        }
        for (int i = 0; i < sources.length(); i++) {
            JSONObject source = sources.optJSONObject(i); if (source == null) continue;
            String id = source.optString("id"); if (id.isEmpty()) continue;
            LinearLayout row = new LinearLayout(activity); row.setGravity(Gravity.CENTER_VERTICAL);
            row.addView(button(source.optString("title", id) + "\n" + source.optString("detail") + "  ›", () -> load(id)),
                        new LinearLayout.LayoutParams(0, -2, 1));
            String path = source.optString("path");
            if (!path.isEmpty()) {
                TextView details = button("⋯", () -> new AlertDialog.Builder(activity)
                    .setTitle("备份详情").setMessage(source.optString("title") + "\n" + source.optString("detail") + "\n\n" + path)
                    .setPositiveButton("关闭", null).show());
                LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(-2, -2); p.leftMargin = dp(8);
                row.addView(details, p);
            }
            add(body, row, 10);
        }
    }
    private void createDialog() {
        EditText uid = new EditText(activity); uid.setInputType(InputType.TYPE_CLASS_NUMBER); uid.setText("1024"); uid.selectAll();
        new AlertDialog.Builder(activity).setTitle("新建存档").setMessage("输入 UID（1–4294967295），然后选择模板。")
            .setView(uid).setNegativeButton("取消", null).setPositiveButton("选择模板", (dialog, ignored) -> {
                final long value;
                try {
                    value = Long.parseLong(uid.getText().toString().trim());
                    if (value < 1 || value > 4294967295L) throw new IllegalArgumentException("UID 允许范围为 1–4294967295");
                } catch (Exception e) { fail(e); return; }
                String[] labels = {"新号 · 无首登", "新号 · 首登", "满级号 · 全角色、全皮肤、全部关卡满星"};
                String[] kinds = {"starter", "starter_first_login", "full_level"};
                new AlertDialog.Builder(activity).setTitle("选择模板").setItems(labels, (d, which) -> create(value, kinds[which], labels[which])).setNegativeButton("取消", null).show();
            }).show();
    }
    private void create(long uid, String kind, String title) {
        busy = true; render();
        worker.execute(() -> {
            try {
                JSONObject result = backend.create(uid, kind), loaded = copy(result.getJSONObject("account"));
                JSONObject tables = result.optJSONObject("catalog"); JSONArray supported = result.optJSONArray("capabilities");
                main.post(() -> {
                    if (closed) return;
                    original = new JSONObject(); account = loaded; catalog = tables == null ? new JSONObject() : tables; capabilities = supported;
                    texts.clear(); JSONArray textmap = catalog.optJSONArray("textmap");
                    if (textmap != null) for (int i = 0; i < textmap.length(); i++) { JSONObject row = textmap.optJSONObject(i); if (row != null) texts.put(row.optString("ID"), row.optString("Text")); }
                    sourceTitle = "新建 · " + title + " · UID " + uid; page = "home"; busy = false; render();
                });
            } catch (Exception e) { main.post(() -> fail(e)); }
        });
    }

    private void captain() {
        add(body, label("舰长资料与资源", 18, 0xffe9edf0, true), 20);
        JSONObject limits = catalog.optJSONObject("captain_limits");
        JSONObject mainData = account.optJSONObject("main");
        if (mainData == null) { add(body, label("存档缺少舰长资料。", 14, 0xffd8b1ad, false), 10); return; }
        String[][] fields = {{"level","等级"},{"scoin","金币"},{"hcoin","水晶"},{"stamina","体力"},
            {"friends_point","友情点"},{"skill_point","技能点"},{"skill_point_limit","技能点上限"},{"equipment_size_limit","装备容量"}};
        for (String[] f : fields) {
            if (!mainData.has(f[0]) && !"friends_point".equals(f[0])) continue;
            JSONObject range = limits == null ? null : limits.optJSONObject(f[0]);
            String detail = "当前：" + mainData.optLong(f[0]);
            if (range != null && range.has("min") && range.has("max")) {
                long min = range.optLong("min"), max = range.optLong("max");
                if ("skill_point".equals(f[0])) max = mainData.optLong("skill_point_limit");
                if ("skill_point_limit".equals(f[0])) min = 50L + currentCabinBonus();
                if ("equipment_size_limit".equals(f[0])) min = 500L + (mainData.optLong("level") - 1L) * 20L;
                detail += "   范围：" + min + "–" + max;
            }
            final String key = f[0], name = f[1], shown = detail;
            add(body, button(name + "\n" + detail + "  ›", () -> editNumber(name, shown, key, mainData.optLong(key))), 10);
        }
        for (String[] f : new String[][]{{"nickname","名称"},{"self_desc","签名"}}) {
            if (mainData.has(f[0])) add(body, label(f[1] + "：" + mainData.optString(f[0]), 14, 0xff9ba4af, false), 12);
        }
    }

    private long currentCabinBonus() {
        JSONObject cabin = find(rows(account, "cabin_list"), "type", 4);
        if (cabin == null) return 0;
        JSONArray owned = rows(cabin, "tech_list"), nodes = rows(catalog, "cabintechtreedata"); long bonus = 0;
        for (int i = 0; i < owned.length(); i++) {
            JSONObject tech = owned.optJSONObject(i); if (tech == null) continue;
            for (int j = 0; j < nodes.length(); j++) {
                JSONObject node = nodes.optJSONObject(j);
                if (node != null && node.optInt("Cabin") == 4 && node.optInt("X") == tech.optInt("pos_x") && node.optInt("Y") == tech.optInt("pos_y") && node.optInt("AbilityType") == 11 && cabin.optInt("level") >= node.optInt("UnlockLevel")) bonus += node.optLong("Argument1");
            }
        }
        return bonus;
    }

    private void editNumber(String name, String hint, String key, long current) {
        EditText input = new EditText(activity); input.setInputType(InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_FLAG_SIGNED); input.setText(Long.toString(current)); input.selectAll();
        new AlertDialog.Builder(activity).setTitle(name).setMessage(hint).setView(input).setNegativeButton("取消", null)
            .setPositiveButton("应用", (d, w) -> {
                try { JSONObject op = new JSONObject().put("op", "captain").put(key, Long.parseLong(input.getText().toString().trim())); apply(op); }
                catch (Exception e) { fail(e); }
            }).show();
    }

    private JSONArray rows(JSONObject object, String name) {
        JSONArray result = object.optJSONArray(name); return result == null ? new JSONArray() : result;
    }
    private JSONObject find(JSONArray array, String field, int id) {
        for (int i = 0; i < array.length(); i++) { JSONObject x = array.optJSONObject(i); if (x != null && x.optInt(field) == id) return x; }
        return null;
    }
    private String name(JSONObject row, String key, int id) {
        String value = row.optString(key), result = texts.get(value);
        return result == null || result.isEmpty() ? "ID " + id : result.replaceAll("<[^>]+>", "");
    }
    private void searchBar() {
        add(body, button("搜索：" + (search.isEmpty() ? "名称或 ID" : search), () -> {
            EditText input = new EditText(activity); input.setSingleLine(true); input.setText(search);
            new AlertDialog.Builder(activity).setTitle("搜索名称或 ID").setView(input).setNegativeButton("取消", null)
                .setNeutralButton("清除", (d, w) -> { search = ""; render(); })
                .setPositiveButton("搜索", (d, w) -> { search = input.getText().toString().trim(); render(); }).show();
        }), 10);
    }
    private boolean matches(String s) { return search.isEmpty() || s.toLowerCase(Locale.ROOT).contains(search.toLowerCase(Locale.ROOT)); }
    private void avatars() {
        add(body, label("女武神", 18, 0xffe9edf0, true), 20); searchBar();
        JSONArray all = rows(catalog, "avatardata"), owned = rows(account, "avatar_list"); int shown = 0;
        for (int i = 0; i < all.length(); i++) {
            JSONObject row = all.optJSONObject(i); if (row == null) continue;
            int id = row.optInt("avatarID"); if (id <= 0) continue;
            JSONObject avatar = find(owned, "avatar_id", id);
            String title = name(row, "fullName", id) + "  #" + id;
            if (!matches(title)) continue;
            if (++shown > 150) { add(body, label("结果较多，请使用搜索缩小范围。", 13, 0xff9ba4af, false), 12); break; }
            String state = avatar == null || avatar.optInt("star") == 0 ? "未解锁" : "评阶 " + avatar.optInt("star") + "   等级 " + avatar.optInt("level");
            add(body, button(title + "\n" + state + "  ›", () -> { selectedId = id; page = "avatar_detail"; render(); }), 8);
        }
    }
    private void numericOperation(String title, String hint, long value, JSONObject op, String field) {
        EditText input = new EditText(activity); input.setInputType(InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_FLAG_SIGNED);
        input.setText(Long.toString(value)); input.selectAll();
        new AlertDialog.Builder(activity).setTitle(title).setMessage(hint).setView(input).setNegativeButton("取消", null)
            .setPositiveButton("应用", (d, w) -> {
                try { op.put(field, Long.parseLong(input.getText().toString().trim())); apply(op); }
                catch (Exception e) { fail(e); }
            }).show();
    }
    private JSONObject operation(String kind, String idKey, int id) {
        JSONObject op = new JSONObject(); try { op.put("op", kind); op.put(idKey, id); } catch (JSONException impossible) { throw new IllegalStateException(impossible); } return op;
    }
    private void avatarDetail() {
        JSONObject meta = find(rows(catalog, "avatardata"), "avatarID", selectedId);
        JSONObject a = find(rows(account, "avatar_list"), "avatar_id", selectedId);
        if (meta == null) { add(body, label("角色数据不可用。", 14, 0xffd8b1ad, false), 20); return; }
        add(body, label(name(meta, "fullName", selectedId) + "  #" + selectedId, 18, 0xffe9edf0, true), 20);
        int star = a == null ? 0 : a.optInt("star"), level = a == null ? 1 : a.optInt("level", 1);
        add(body, button("解锁与评阶：" + (star == 0 ? "未解锁" : star) + "  ›", () ->
            numericOperation("解锁与评阶", "0 为锁定；解锁时最低评阶 " + meta.optInt("unlockStar") + "，最高 5。", star, operation("avatar", "avatar_id", selectedId), "star")), 12);
        if (star > 0) {
            JSONObject mainData = account.optJSONObject("main");
            JSONObject player = mainData == null ? null : find(rows(catalog, "playerleveldata"), "level", mainData.optInt("level"));
            int cap = player == null ? 0 : player.optInt("avatarLevelLimit");
            add(body, button("等级：" + level + "  ›", () -> numericOperation("角色等级", "允许范围：1–" + cap, level, operation("avatar", "avatar_id", selectedId), "level")), 8);
            for (String[] field : new String[][]{{"touch_goodfeel", "互动好感"}, {"stage_goodfeel", "出战好感"}}) {
                final int current = a.optInt(field[0]);
                add(body, button(field[1] + "：" + current + "  ›", () -> numericOperation(field[1], "当前：" + current, current, operation("avatar", "avatar_id", selectedId), field[0])), 8);
            }
            if (has("equipment_equip")) {
                String[] slots = {"武器", "圣痕上", "圣痕中", "圣痕下"};
                String[] fields = {"weapon_unique_id", "stigmata_unique_id_1", "stigmata_unique_id_2", "stigmata_unique_id_3"};
                for (int i = 0; i < 4; i++) {
                    final int slot = i + 1, uid = a.optInt(fields[i]);
                    JSONObject e = equipmentItem(uid);
                    String current = e == null ? "未穿戴" : "实例 " + uid;
                    add(body, button(slots[i] + "：" + current + "  ›", () -> selectEquipment(slot)), 8);
                }
                if (has("equipment_exchange")) add(body, button("与其他角色交换武器  ›", this::exchangeWeapon), 8);
            }
        }
        int fragments = a == null ? 0 : a.optInt("fragment");
        JSONObject frag = find(rows(catalog, "avatarfragmentdata"), "ID", meta.optInt("avatarFragmentID"));
        if (frag != null) add(body, button("角色碎片：" + fragments + "  ›", () -> numericOperation("角色碎片", "允许范围：0–" + frag.optInt("quantityLimit"), fragments, operation("avatar", "avatar_id", selectedId), "fragment")), 8);
        if (star > 0 && has("skill")) {
            add(body, label("技能", 16, 0xffe9edf0, true), 18);
            JSONArray skills = rows(a, "skill_list"), available = rows(catalog, "avatarsubskilldata");
            for (int i = 0; i < available.length(); i++) {
                JSONObject sm = available.optJSONObject(i); if (sm == null) continue;
                int skillId = sm.optInt("skillId"), subId = sm.optInt("avatarSubSkillId");
                if (!arrayContains(rows(meta, "skillList"), skillId) || subId <= 0) continue;
                JSONObject skill = find(skills, "skill_id", skillId);
                JSONObject sub = skill == null ? null : find(rows(skill, "sub_skill_list"), "sub_skill_id", subId);
                int current = sub == null ? 0 : sub.optInt("level");
                String title = name(sm, "name", subId), hint = "允许范围：0–" + sm.optInt("maxLv");
                add(body, button(title + "：" + current + "  ›", () -> {
                    JSONObject op = operation("skill", "avatar_id", selectedId);
                    try { op.put("skill_id", skillId); op.put("sub_skill_id", subId); } catch (JSONException impossible) { throw new IllegalStateException(impossible); }
                    numericOperation(title, hint, current, op, "level");
                }), 8);
            }
        }
    }
    private void selectEquipment(int slot) {
        String kind = slot == 1 ? "weapon" : "stigmata";
        ArrayList<String> labels = new ArrayList<>(); ArrayList<Integer> ids = new ArrayList<>();
        if (slot > 1) { labels.add("卸下"); ids.add(0); }
        JSONArray items = rows(account, kind + "_list");
        for (int i = 0; i < items.length(); i++) {
            JSONObject item = items.optJSONObject(i); if (item == null) continue;
            int uid = item.optInt("unique_id"), id = item.optInt("id");
            JSONObject meta = find(rows(catalog, slot == 1 ? "weapondata" : "stigmatadata"), "ID", id);
            if (meta == null || (slot > 1 && meta.optInt("baseType") != slot - 1)) continue;
            labels.add(name(meta, "displayTitle", id) + " · 实例 " + uid + " · " + owner(uid)); ids.add(uid);
        }
        if (ids.isEmpty()) { new AlertDialog.Builder(activity).setMessage("没有可选装备。") .setPositiveButton("确定", null).show(); return; }
        new AlertDialog.Builder(activity).setTitle("选择装备").setItems(labels.toArray(new String[0]), (d, which) -> {
            try { apply(new JSONObject().put("op", "equipment_equip").put("avatar_id", selectedId).put("slot", slot).put("unique_id", ids.get(which))); }
            catch (Exception e) { fail(e); }
        }).show();
    }
    private void exchangeWeapon() {
        ArrayList<String> labels = new ArrayList<>(); ArrayList<Integer> ids = new ArrayList<>();
        JSONArray characters = rows(account, "avatar_list");
        for (int i = 0; i < characters.length(); i++) {
            JSONObject a = characters.optJSONObject(i); if (a == null || a.optInt("star") <= 0 || a.optInt("avatar_id") == selectedId) continue;
            int id = a.optInt("avatar_id"); JSONObject meta = find(rows(catalog, "avatardata"), "avatarID", id);
            labels.add(meta == null ? "角色 #" + id : name(meta, "fullName", id)); ids.add(id);
        }
        if (ids.isEmpty()) { new AlertDialog.Builder(activity).setMessage("没有其他已解锁角色。").setPositiveButton("确定", null).show(); return; }
        new AlertDialog.Builder(activity).setTitle("选择交换武器的角色").setItems(labels.toArray(new String[0]), (d, which) -> {
            try { apply(new JSONObject().put("op", "equipment_exchange").put("avatar_id_1", selectedId).put("avatar_id_2", ids.get(which))); }
            catch (Exception e) { fail(e); }
        }).show();
    }
    private void materials() {
        add(body, label("材料与道具", 18, 0xffe9edf0, true), 20); searchBar();
        if (has("materials_batch")) {
            JSONArray presets = rows(catalog, "material_presets");
            for (int i = 0; i < presets.length(); i++) {
                JSONObject preset = presets.optJSONObject(i); if (preset == null) continue;
                JSONArray items = preset.optJSONArray("items"); if (items == null || items.length() == 0) continue;
                String title = preset.optString("name", preset.optString("id"));
                add(body, button("批量补充 · " + title + "  ›", () -> {
                    StringBuilder details = new StringBuilder("数量不足时补至以下目标，已有更多时保留：\n");
                    for (int j = 0; j < items.length(); j++) {
                        JSONObject item = items.optJSONObject(j); if (item == null) continue;
                        int id = item.optInt("id"); JSONObject meta = find(rows(catalog, "materialdata"), "ID", id);
                        details.append(meta == null ? "ID " + id : name(meta, "displayTitle", id)).append("：").append(item.optInt("num")).append('\n');
                    }
                    new AlertDialog.Builder(activity).setTitle("批量补充 · " + title).setMessage(details.toString()).setNegativeButton("取消", null)
                        .setPositiveButton("应用", (d, w) -> { try { apply(new JSONObject().put("op", "materials_batch").put("items", items)); } catch (Exception e) { fail(e); } }).show();
                }), 8);
            }
        }
        JSONArray all = rows(catalog, "materialdata"), owned = rows(account, "material_list"); int shown = 0;
        for (int i = 0; i < all.length(); i++) {
            JSONObject row = all.optJSONObject(i); if (row == null) continue;
            int id = row.optInt("ID"); if (id <= 0) continue;
            boolean fragment = false;
            JSONArray avatars = rows(catalog, "avatardata");
            for (int j = 0; j < avatars.length(); j++) { JSONObject a = avatars.optJSONObject(j); if (a != null && a.optInt("avatarFragmentID") == id) { fragment = true; break; } }
            if (fragment) continue;
            String title = name(row, "displayTitle", id) + "  #" + id + "  " + row.optString("ItemType");
            if (!matches(title)) continue;
            if (++shown > 150) { add(body, label("结果较多，请使用搜索缩小范围。", 13, 0xff9ba4af, false), 12); break; }
            JSONObject item = find(owned, "id", id); int count = item == null ? 0 : item.optInt("num");
            add(body, button(title + "\n数量 " + count + "  ›", () -> numericOperation(title, "允许范围：0–" + row.optInt("quantityLimit"), count, operation("material", "id", id), "num")), 8);
        }
    }

    private boolean arrayContains(JSONArray values, int id) {
        for (int i = 0; i < values.length(); i++) if (values.optInt(i) == id) return true;
        return false;
    }
    private void costumes() {
        add(body, label("服装", 18, 0xffe9edf0, true), 20); searchBar();
        if (has("costume_all")) add(body, button("解锁全部服装", () -> {
            new AlertDialog.Builder(activity).setTitle("解锁全部服装？").setNegativeButton("取消", null)
                .setPositiveButton("解锁", (d, w) -> { try { apply(new JSONObject().put("op", "costume_all").put("owned", true)); } catch (Exception e) { fail(e); } }).show();
        }), 10);
        JSONArray all = rows(catalog, "dressdata"), owned = rows(account, "has_got_item_id_list"); int shown = 0;
        for (int i = 0; i < all.length(); i++) {
            JSONObject row = all.optJSONObject(i); if (row == null || row.optInt("dressType") != 1) continue;
            int id = row.optInt("dressID"); if (id <= 0 || rows(row, "avatarIDList").length() == 0) continue;
            String title = name(row, "name", id) + "  #" + id; if (!matches(title)) continue;
            if (++shown > 150) { add(body, label("结果较多，请使用搜索缩小范围。", 13, 0xff9ba4af, false), 12); break; }
            boolean isOwned = arrayContains(owned, id);
            add(body, button(title + "\n" + (isOwned ? "已解锁" : "未解锁") + "  ›", () -> costumeMenu(row, id, isOwned)), 8);
        }
    }
    private void costumeMenu(JSONObject meta, int id, boolean owned) {
        ArrayList<String> options = new ArrayList<>(); ArrayList<Integer> ids = new ArrayList<>();
        options.add(owned ? "锁定服装" : "解锁服装"); ids.add(-1);
        if (owned) {
            JSONArray valid = rows(meta, "avatarIDList");
            for (int i = 0; i < valid.length(); i++) {
                int aid = valid.optInt(i); JSONObject avatar = find(rows(account, "avatar_list"), "avatar_id", aid);
                JSONObject ameta = find(rows(catalog, "avatardata"), "avatarID", aid);
                if (avatar != null && avatar.optInt("star") > 0 && ameta != null) {
                    options.add((avatar.optInt("dress_id") == id ? "当前穿着：" : "切换至：") + name(ameta, "fullName", aid)); ids.add(aid);
                }
            }
        }
        new AlertDialog.Builder(activity).setTitle(name(meta, "name", id)).setItems(options.toArray(new String[0]), (d, which) -> {
            try {
                JSONObject op = new JSONObject().put("op", "costume");
                if (ids.get(which) == -1) op.put("dress_id", id).put("owned", !owned);
                else op.put("avatar_id", ids.get(which)).put("equip", id);
                apply(op);
            } catch (Exception e) { fail(e); }
        }).show();
    }
    private String equipmentKind(int uid) {
        return find(rows(account, "weapon_list"), "unique_id", uid) != null ? "weapon" : "stigmata";
    }
    private JSONObject equipmentItem(int uid) {
        JSONObject result = find(rows(account, "weapon_list"), "unique_id", uid);
        return result != null ? result : find(rows(account, "stigmata_list"), "unique_id", uid);
    }
    private String owner(int uid) {
        JSONArray avatars = rows(account, "avatar_list");
        for (int i = 0; i < avatars.length(); i++) {
            JSONObject a = avatars.optJSONObject(i); if (a == null) continue;
            String[] fields = {"weapon_unique_id", "stigmata_unique_id_1", "stigmata_unique_id_2", "stigmata_unique_id_3"};
            for (String field : fields) if (a.optInt(field) == uid) {
                int id = a.optInt("avatar_id"); JSONObject meta = find(rows(catalog, "avatardata"), "avatarID", id);
                return meta == null ? "角色 #" + id : name(meta, "fullName", id);
            }
        }
        return "未穿戴";
    }
    private String stigmaSlot(JSONObject meta) {
        int slot = meta.optInt("baseType");
        return slot == 1 ? "上" : slot == 2 ? "中" : slot == 3 ? "下" : Integer.toString(slot);
    }
    private void equipment() {
        add(body, label("武器与圣痕", 18, 0xffe9edf0, true), 20); searchBar();
        if (has("equipment_add")) add(body, button("添加武器或圣痕  ›", () -> { page = "equipment_add"; search = ""; render(); }), 10);
        int shown = 0;
        for (String kind : new String[]{"weapon", "stigmata"}) {
            JSONArray all = rows(account, kind + "_list");
            for (int i = 0; i < all.length(); i++) {
                JSONObject item = all.optJSONObject(i); if (item == null) continue;
                int id = item.optInt("id"), uid = item.optInt("unique_id");
                JSONObject meta = find(rows(catalog, kind.equals("weapon") ? "weapondata" : "stigmatadata"), "ID", id);
                String title = (kind.equals("weapon") ? "武器 · " : "圣痕 · ") + (meta == null ? "ID " + id : name(meta, "displayTitle", id)) + " #" + id + " / 实例 " + uid;
                if (meta != null && kind.equals("stigmata")) title += " · " + stigmaSlot(meta) + " · 套装 " + meta.optInt("setID");
                if (!matches(title)) continue;
                if (++shown > 150) { add(body, label("结果较多，请使用搜索缩小范围。", 13, 0xff9ba4af, false), 12); return; }
                add(body, button(title + "\n等级 " + item.optInt("level") + " · " + owner(uid) + "  ›", () -> { selectedUid = uid; page = "equipment_detail"; render(); }), 8);
            }
        }
    }
    private void equipmentAdd() {
        add(body, label("添加装备", 18, 0xffe9edf0, true), 20); searchBar();
        int shown = 0;
        for (String kind : new String[]{"weapon", "stigmata"}) {
            JSONArray all = rows(catalog, kind.equals("weapon") ? "weapondata" : "stigmatadata");
            for (int i = 0; i < all.length(); i++) {
                JSONObject row = all.optJSONObject(i); if (row == null) continue;
                int id = row.optInt("ID"); if (id <= 0) continue;
                String title = (kind.equals("weapon") ? "武器 · " : "圣痕 · ") + name(row, "displayTitle", id) + "  #" + id;
                if (kind.equals("stigmata")) title += " · " + stigmaSlot(row) + " · 套装 " + row.optInt("setID");
                if (!matches(title)) continue;
                if (++shown > 150) { add(body, label("结果较多，请使用搜索缩小范围。", 13, 0xff9ba4af, false), 12); return; }
                final String displayTitle = title;
                add(body, button(displayTitle + "  ›", () -> new AlertDialog.Builder(activity).setTitle("添加 " + displayTitle + "？")
                    .setMessage("将添加等级 1、经验 0 的装备实例。")
                    .setNegativeButton("取消", null).setPositiveButton("添加", (d, w) -> {
                        try { apply(new JSONObject().put("op", "equipment_add").put("kind", kind).put("id", id)); }
                        catch (Exception e) { fail(e); }
                    }).show()), 8);
            }
        }
    }
    private void equipmentDetail() {
        JSONObject item = equipmentItem(selectedUid); if (item == null) { page = "equipment"; equipment(); return; }
        String kind = equipmentKind(selectedUid); int id = item.optInt("id");
        JSONObject meta = find(rows(catalog, kind.equals("weapon") ? "weapondata" : "stigmatadata"), "ID", id);
        String title = meta == null ? "ID " + id : name(meta, "displayTitle", id);
        add(body, label(title + "  #" + id + " / 实例 " + selectedUid, 18, 0xffe9edf0, true), 20);
        add(body, label("穿戴：" + owner(selectedUid), 14, 0xff9ba4af, false), 12);
        if (meta != null) add(body, label("等级上限：" + meta.optInt("maxLv") + "   进化 ID：" + meta.optInt("evoID") + "   进化材料：" + meta.optString("evoMaterial"), 14, 0xff9ba4af, false), 8);
        for (String[] f : new String[][]{{"level", "等级"}, {"exp", "经验"}}) {
            int value = item.optInt(f[0]);
            String bounds = "修改将按当前装备表校验。";
            if (meta != null && "level".equals(f[0])) bounds = "允许范围：1–" + meta.optInt("maxLv");
            if (meta != null && "exp".equals(f[0])) {
                JSONObject level = find(rows(catalog, "equipmentleveldata"), "level", item.optInt("level"));
                JSONArray values = level == null ? null : level.optJSONArray("Type1"); int expType = meta.optInt("expType");
                if (values != null && expType >= 0 && expType < values.length()) {
                    int max = values.optInt(expType) - (item.optInt("level") == meta.optInt("maxLv") ? 0 : 1);
                    bounds = "允许范围：0–" + max;
                }
            }
            final String hint = bounds;
            add(body, button(f[1] + "：" + value + "  ›", () -> numericOperation(f[1], hint, value, operation("equipment_edit", "unique_id", selectedUid), f[0])), 8);
        }
        boolean locked = item.optBoolean("is_protected");
        add(body, button("保护：" + (locked ? "开启" : "关闭") + "  ›", () -> {
            try { apply(operation("equipment_edit", "unique_id", selectedUid).put("is_protected", !locked)); } catch (Exception e) { fail(e); }
        }), 8);
        if (has("equipment_delete")) add(body, button("删除此装备  ›", () -> {
            if (!"未穿戴".equals(owner(selectedUid))) { new AlertDialog.Builder(activity).setMessage("请先为角色更换装备，再删除此实例。") .setPositiveButton("确定", null).show(); return; }
            new AlertDialog.Builder(activity).setTitle("删除此装备？").setNegativeButton("取消", null).setPositiveButton("删除", (d, w) -> {
                page = "equipment"; apply(operation("equipment_delete", "unique_id", selectedUid));
            }).show();
        }), 8);
    }

    private Spinner selector(ArrayList<String> labels, int selected, java.util.function.IntConsumer onChange) {
        Spinner spinner = new Spinner(activity);
        ArrayAdapter<String> adapter = new ArrayAdapter<>(activity, android.R.layout.simple_spinner_item, labels);
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item); spinner.setAdapter(adapter);
        spinner.setSelection(Math.max(0, selected));
        spinner.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            boolean first = true;
            @Override public void onNothingSelected(AdapterView<?> parent) { }
            @Override public void onItemSelected(AdapterView<?> parent, View view, int pos, long id) {
                if (view instanceof TextView) ((TextView) view).setTextColor(0xffe9edf0);
                if (first) { first = false; return; }
                onChange.accept(pos);
            }
        });
        return spinner;
    }
    private void story() {
        add(body, label("剧情与外传", 18, 0xffe9edf0, true), 20);
        add(body, button(stageKind.equals("story") ? "剧情  ·  切换为外传" : "外传  ·  切换为剧情", () -> {
            stageKind = stageKind.equals("story") ? "extra" : "story"; stageDifficulty = stageChapter = stageId = -1; render();
        }), 10);
        JSONArray all = rows(catalog, "stages");
        ArrayList<Integer> diffs = new ArrayList<>(), chapters = new ArrayList<>(), ids = new ArrayList<>();
        for (int i = 0; i < all.length(); i++) {
            JSONObject s = all.optJSONObject(i); if (s == null || !stageKind.equals(s.optString("kind"))) continue;
            int value = s.optInt("difficulty"); if (!diffs.contains(value)) diffs.add(value);
        }
        java.util.Collections.sort(diffs);
        if (diffs.isEmpty()) { add(body, label("当前没有可编辑关卡。", 14, 0xff9ba4af, false), 10); return; }
        if (!diffs.contains(stageDifficulty)) stageDifficulty = diffs.get(0);
        for (int i = 0; i < all.length(); i++) {
            JSONObject s = all.optJSONObject(i); if (s == null || !stageKind.equals(s.optString("kind")) || s.optInt("difficulty") != stageDifficulty) continue;
            int value = s.optInt("editor_chapter_id", s.optInt("chapterId")); if (!chapters.contains(value)) chapters.add(value);
        }
        java.util.Collections.sort(chapters); if (!chapters.contains(stageChapter)) stageChapter = chapters.get(0);
        ArrayList<String> names = new ArrayList<>();
        for (int i = 0; i < all.length(); i++) {
            JSONObject s = all.optJSONObject(i); if (s == null || !stageKind.equals(s.optString("kind")) || s.optInt("difficulty") != stageDifficulty || s.optInt("editor_chapter_id", s.optInt("chapterId")) != stageChapter) continue;
            ids.add(s.optInt("id")); names.add(s.optString("display_name") + " #" + s.optInt("id"));
        }
        if (!ids.contains(stageId)) stageId = ids.get(0);
        ArrayList<String> dn = new ArrayList<>(), cn = new ArrayList<>();
        for (int value : diffs) dn.add("难度 " + value);
        for (int value : chapters) cn.add("章节 " + value);
        LinearLayout choices = new LinearLayout(activity);
        choices.addView(selector(dn, diffs.indexOf(stageDifficulty), index -> { stageDifficulty = diffs.get(index); stageChapter = stageId = -1; render(); }), new LinearLayout.LayoutParams(0, -2, 1));
        choices.addView(selector(cn, chapters.indexOf(stageChapter), index -> { stageChapter = chapters.get(index); stageId = -1; render(); }), new LinearLayout.LayoutParams(0, -2, 1));
        choices.addView(selector(names, ids.indexOf(stageId), index -> { stageId = ids.get(index); render(); }), new LinearLayout.LayoutParams(0, -2, 2));
        add(body, choices, 18);
        JSONObject saved = find(rows(account, "stage_list"), "id", stageId);
        add(body, label(saved == null ? "当前：尚无关卡记录" : "当前进度：" + saved.optInt("progress") + "   星级：" + rows(saved, "challenge_index_list").length(), 14, 0xff9ba4af, false), 14);
        add(body, button("解锁到所选关卡", () -> apply(operation("story_unlock", "stage_id", stageId))), 12);
        if (has("story_max_stars")) add(body, button("本章节全部满星", () -> {
            try { apply(new JSONObject().put("op", "story_max_stars").put("kind", stageKind).put("difficulty", stageDifficulty).put("chapter_id", stageChapter)); }
            catch (Exception e) { fail(e); }
        }), 10);
        if (has("story_max_stars")) add(body, button("全部剧情与外传满星", () -> {
            new AlertDialog.Builder(activity).setTitle("设置所有剧情与外传满星？")
                .setMessage("将逐章校验全部难度；如有章节不满足条件，本次不会应用任何修改。")
                .setNegativeButton("取消", null).setPositiveButton("应用", (d, w) -> allStars()).show();
        }), 10);
    }
    private void allStars() {
        if (busy || account == null) return;
        try {
            JSONObject snapshot = copy(account); JSONArray stages = rows(catalog, "stages");
            LinkedHashSet<String> groups = new LinkedHashSet<>(); ArrayList<JSONObject> operations = new ArrayList<>();
            for (int i = 0; i < stages.length(); i++) {
                JSONObject s = stages.optJSONObject(i); if (s == null) continue;
                String kind = s.optString("kind"); int difficulty = s.optInt("difficulty"), chapter = s.optInt("editor_chapter_id", s.optInt("chapterId"));
                if (groups.add(kind + ":" + difficulty + ":" + chapter)) operations.add(new JSONObject().put("op", "story_max_stars").put("kind", kind).put("difficulty", difficulty).put("chapter_id", chapter));
            }
            busy = true; render();
            worker.execute(() -> {
                try {
                    JSONObject result = snapshot;
                    for (JSONObject op : operations) result = backend.apply(result, op);
                    final JSONObject done = copy(result);
                    main.post(() -> { if (!closed) { account = done; busy = false; render(); } });
                } catch (Exception e) { main.post(() -> fail(e)); }
            });
        } catch (Exception e) { fail(e); }
    }
    private void sakura() {
        add(body, label("樱色轮回", 18, 0xffe9edf0, true), 20);
        JSONObject world = account.optJSONObject("openworld_data");
        String current = "当前：尚无轮回记录";
        if (world != null) {
            StringBuilder parts = new StringBuilder(); JSONArray active = rows(world, "cur_story_list");
            for (int i = 0; i < active.length(); i++) { JSONObject story = active.optJSONObject(i); if (story == null) continue; if (parts.length() > 0) parts.append("、"); parts.append(story.optInt("story_id")); }
            current = "当前轮回：" + world.optInt("cycle") + "   进行中的任务：" + (parts.length() == 0 ? "无" : parts.toString());
        }
        add(body, label(current, 14, 0xff9ba4af, false), 12);
        JSONObject data = catalog.optJSONObject("sakura"); if (data == null) return;
        JSONArray stories = rows(data, "stories"); ArrayList<Integer> cycles = new ArrayList<>(), ids = new ArrayList<>();
        for (int i = 0; i < stories.length(); i++) {
            JSONObject item = stories.optJSONObject(i); if (item == null) continue;
            int cycle = item.optInt("Cycle"), id = item.optInt("StoryID");
            if (cycle < 1 || cycle > 4 || id <= 0) continue;
            if (!cycles.contains(cycle)) cycles.add(cycle);
        }
        if (cycles.isEmpty()) { add(body, label("当前没有可编辑的轮回任务。", 14, 0xff9ba4af, false), 10); return; }
        if (!cycles.contains(sakuraCycle)) sakuraCycle = cycles.get(0);
        ArrayList<String> cycleNames = new ArrayList<>(), partNames = new ArrayList<>();
        for (int cycle : cycles) cycleNames.add("第 " + cycle + " 轮回");
        for (int i = 0; i < stories.length(); i++) {
            JSONObject item = stories.optJSONObject(i); if (item == null || item.optInt("Cycle") != sakuraCycle) continue;
            int id = item.optInt("StoryID"); ids.add(id); partNames.add("PART " + (id % 100) + "  #" + id);
        }
        if (!ids.contains(sakuraId)) sakuraId = ids.get(0);
        LinearLayout choices = new LinearLayout(activity);
        choices.addView(selector(cycleNames, cycles.indexOf(sakuraCycle), index -> { sakuraCycle = cycles.get(index); sakuraId = -1; render(); }), new LinearLayout.LayoutParams(0, -2, 1));
        choices.addView(selector(partNames, ids.indexOf(sakuraId), index -> { sakuraId = ids.get(index); render(); }), new LinearLayout.LayoutParams(0, -2, 1));
        add(body, choices, 12);
        add(body, button("切换至所选任务", () -> {
            try { apply(new JSONObject().put("op", "sakura_set_part").put("cycle", sakuraCycle).put("story_id", sakuraId)); }
            catch (Exception e) { fail(e); }
        }), 10);
    }
    private void abyss() {
        add(body, label("深渊", 18, 0xffe9edf0, true), 20);
        JSONObject state = account.optJSONObject("endless_runtime");
        if (state == null) { add(body, label("请先进入深渊并刷新本期数据。", 14, 0xff9ba4af, false), 12); return; }
        int currentGroup = state.optInt("group"), currentFloor = state.optInt("progress") + 1, maxFloor = catalog.optInt("abyss_floors");
        add(body, label("当前段位：" + currentGroup + "   当前关卡：" + currentFloor, 14, 0xff9ba4af, false), 12);
        LinearLayout form = column();
        EditText group = new EditText(activity), floor = new EditText(activity);
        group.setInputType(InputType.TYPE_CLASS_NUMBER); group.setHint("段位（1–7）"); group.setText(Integer.toString(currentGroup));
        floor.setInputType(InputType.TYPE_CLASS_NUMBER); floor.setHint("关卡（1–" + maxFloor + "）"); floor.setText(Integer.toString(currentFloor));
        add(form, group, 0); add(form, floor, 6); add(body, form, 10);
        add(body, button("应用深渊设置", () -> {
            try { apply(new JSONObject().put("op", "abyss_set").put("group", Integer.parseInt(group.getText().toString())).put("floor", Integer.parseInt(floor.getText().toString()))); }
            catch (Exception e) { fail(e); }
        }), 10);
    }
    private void cabins() {
        add(body, label("家园与宿舍", 18, 0xffe9edf0, true), 20);
        for (int type : new int[]{3, 4, 5}) {
            JSONObject cabin = find(rows(account, "cabin_list"), "type", type);
            int level = cabin == null ? 1 : cabin.optInt("level", 1), grade = cabin == null ? 1 : cabin.optInt("extend_grade", 1);
            add(body, label("舱室 " + type + (cabin == null ? " · 尚无记录" : ""), 16, 0xffe9edf0, true), 18);
            add(body, button("等级：" + level + "  ›", () -> numericOperation("舱室等级", "仅支持提高等级，受舰长等级及扩建限制。", level, operation("cabin", "cabin_type", type), "level")), 8);
            add(body, button("扩建：" + grade + "  ›", () -> numericOperation("扩建等级", "仅支持提高扩建等级。", grade, operation("cabin", "cabin_type", type), "extend_grade")), 8);
            if (cabin != null) {
                JSONArray techs = rows(cabin, "tech_list"), table = rows(catalog, "cabintechtreedata");
                if (techs.length() == 0) add(body, label("科技：无", 13, 0xff9ba4af, false), 8);
                for (int i = 0; i < techs.length(); i++) {
                    JSONObject tech = techs.optJSONObject(i); if (tech == null) continue;
                    JSONObject meta = null;
                    for (int j = 0; j < table.length(); j++) {
                        JSONObject row = table.optJSONObject(j);
                        if (row != null && row.optInt("Cabin") == type && row.optInt("X") == tech.optInt("pos_x") && row.optInt("Y") == tech.optInt("pos_y")) { meta = row; break; }
                    }
                    String title = meta == null ? "节点 (" + tech.optInt("pos_x") + ", " + tech.optInt("pos_y") + ")" : name(meta, "Title", 0);
                    add(body, label("科技：" + title, 13, 0xff9ba4af, false), 6);
                }
            }
        }
    }

    private void apply(JSONObject operation) {
        if (busy || account == null) return;
        try {
            JSONObject snapshot = copy(account); busy = true; render();
            worker.execute(() -> {
                try {
                    JSONObject result = copy(backend.apply(snapshot, operation));
                    main.post(() -> { if (!closed) { account = result; busy = false; render(); } });
                } catch (Exception e) { main.post(() -> fail(e)); }
            });
        } catch (Exception e) { fail(e); }
    }
    private void fail(Exception error) {
        if (closed) return;
        busy = false; render();
        String message = error.getMessage();
        new AlertDialog.Builder(activity).setTitle("操作未完成").setMessage(message == null ? error.toString() : message).setPositiveButton("知道了", null).show();
    }

    private void preview() {
        ArrayList<String> changes = new ArrayList<>(); collectDiff("", original, account, changes, 100);
        if (changes.isEmpty()) return;
        StringBuilder message = new StringBuilder();
        for (String change : changes) message.append(change).append('\n');
        if (changes.size() == 100) message.append("仅显示前 100 项，请确认以上变更后保存。\n");
        new AlertDialog.Builder(activity).setTitle("确认保存修改").setMessage(message.toString())
            .setNegativeButton("继续编辑", null).setPositiveButton("保存", (d, w) -> save()).show();
    }
    private void save() {
        try {
            JSONObject snapshot = copy(account); busy = true; render();
            worker.execute(() -> {
                try {
                    backend.save(snapshot);
                    JSONArray refreshed = null;
                    try { refreshed = backend.sources(); } catch (Exception ignored) { /* The save already succeeded. */ }
                    final JSONArray updatedSources = refreshed;
                    main.post(() -> {
                        if (closed) return;
                        try { original = copy(snapshot); if (updatedSources != null) sources = updatedSources;
                            sourceTitle = "当前选择的存档"; busy = false; render();
                            new AlertDialog.Builder(activity).setMessage("存档已保存。").setPositiveButton("确定", null).show();
                        } catch (Exception e) { fail(e); }
                    });
                } catch (Exception e) { main.post(() -> fail(e)); }
            });
        } catch (Exception e) { fail(e); }
    }
    private static void collectDiff(String path, Object before, Object after, ArrayList<String> out, int limit) {
        if (out.size() >= limit) return;
        if (before == null && after instanceof JSONObject) before = new JSONObject();
        if (after == null && before instanceof JSONObject) after = new JSONObject();
        if (before == null && after instanceof JSONArray) before = new JSONArray();
        if (after == null && before instanceof JSONArray) after = new JSONArray();
        if (before instanceof JSONObject && after instanceof JSONObject) {
            JSONObject a = (JSONObject) before, b = (JSONObject) after;
            LinkedHashSet<String> keys = new LinkedHashSet<>();
            for (Iterator<String> i = a.keys(); i.hasNext();) keys.add(i.next());
            for (Iterator<String> i = b.keys(); i.hasNext();) keys.add(i.next());
            for (String key : keys) collectDiff(path.isEmpty() ? key : path + "." + key, a.opt(key), b.opt(key), out, limit);
        } else if (before instanceof JSONArray && after instanceof JSONArray) {
            JSONArray a = (JSONArray) before, b = (JSONArray) after;
            for (int i = 0; i < Math.max(a.length(), b.length()); i++) collectDiff(path + "[" + i + "]", a.opt(i), b.opt(i), out, limit);
        } else if (!(before == null ? after == null : before.equals(after))) {
            out.add(path + "：" + String.valueOf(before) + " → " + String.valueOf(after));
        }
    }
}
