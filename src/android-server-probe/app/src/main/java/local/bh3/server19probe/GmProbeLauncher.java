package local.bh3.server19probe;

import android.content.Context;
import android.os.Bundle;
import android.util.Log;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.LinearLayout;
import android.widget.Switch;
import android.widget.TextView;

public final class GmProbeLauncher extends IntegratedActivity {
    private static boolean registered;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        if (!registered) {
            getApplication().registerActivityLifecycleCallbacks(new GmProbeProvider());
            registered = true;
        }
    }

    @Override public void setContentView(View content) {
        super.setContentView(content);
        // LauncherScreen adds its child views synchronously after attaching the root.
        content.post(() -> replaceServerTile(content));
    }

    private boolean replaceServerTile(View view) {
        if (view instanceof TextView && "服务端调整".contentEquals(((TextView) view).getText())
                && view.getParent() instanceof LinearLayout) {
            LinearLayout tile = (LinearLayout) view.getParent();
            ((TextView) view).setText("GM 浮窗");
            if (tile.getChildCount() == 3 && tile.getChildAt(2) instanceof TextView)
                ((TextView) tile.getChildAt(2)).setText("进游戏后显示贴边把手");
            Switch toggle = new Switch(this);
            toggle.setContentDescription("游戏内 GM 浮窗");
            toggle.setChecked(GmProbeProvider.enabled(this));
            toggle.setOnCheckedChangeListener((button, checked) -> {
                getSharedPreferences(GmProbeProvider.PREFS, Context.MODE_PRIVATE)
                        .edit().putBoolean(GmProbeProvider.ENABLED, checked).apply();
                Log.i("BH3GmViewProbe", "SETTING " + checked);
            });
            LinearLayout cards = (LinearLayout) tile.getParent();
            LinearLayout editor = (LinearLayout) cards.getChildAt(0);
            alignTitle(editor, editor.getChildAt(1), null);
            alignTitle(tile, view, toggle);
            editor.getLayoutParams().height = ViewGroup.LayoutParams.MATCH_PARENT;
            tile.getLayoutParams().height = ViewGroup.LayoutParams.MATCH_PARENT;
            tile.setOnClickListener(v -> toggle.toggle());
            return true;
        }
        if (view instanceof ViewGroup) {
            ViewGroup group = (ViewGroup) view;
            for (int i = 0; i < group.getChildCount(); i++)
                if (replaceServerTile(group.getChildAt(i))) return true;
        }
        return false;
    }

    private void alignTitle(LinearLayout tile, View title, Switch toggle) {
        int index = tile.indexOfChild(title);
        ViewGroup.LayoutParams original = title.getLayoutParams();
        tile.removeViewAt(index);
        LinearLayout row = new LinearLayout(this);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setMinimumHeight(GmProbeProvider.dp(this, 24));
        row.addView(title, new LinearLayout.LayoutParams(0, -2, 1));
        if (toggle != null) row.addView(toggle, new LinearLayout.LayoutParams(-2, -2));
        tile.addView(row, index, original);
    }
}
