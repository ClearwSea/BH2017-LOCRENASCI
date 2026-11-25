package local.bh3.server19probe;

import android.app.Activity;
import android.app.Application;
import android.content.Context;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.graphics.PixelFormat;
import android.os.Bundle;
import android.util.Log;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewConfiguration;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.view.inputmethod.InputMethodManager;
import android.webkit.RenderProcessGoneDetail;
import android.webkit.WebChromeClient;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;

public final class GmProbeProvider implements Application.ActivityLifecycleCallbacks {
    static final String PREFS = "gm_overlay";
    static final String ENABLED = "enabled";
    private static final String TAG = "BH3GmViewProbe";
    private static final String GAME = "com.miHoYo.overridenativeactivity.OverrideNativeActivity";
    private static final String PAGE = "file:///android_asset/gm2017.html";
    private static final String DOCK_RIGHT = "dock_right";
    private static final String DOCK_HEIGHT = "dock_height";
    private Activity game;
    private TextView handle;
    private WindowManager.LayoutParams handlePosition;
    private WindowManager.LayoutParams panelPosition;
    private View.OnLayoutChangeListener rootSizeListener;
    private LinearLayout panel;
    private WebView browser;
    private static final long HANDLE_IDLE_MS = 3000;
    private final Runnable fadeHandle = () -> {
        if (handle != null && handle.isAttachedToWindow())
            handle.animate().alpha(0.28f).setDuration(240).start();
    };

    private void wakeHandle(boolean scheduleFade) {
        if (handle == null) return;
        handle.removeCallbacks(fadeHandle);
        handle.animate().cancel();
        handle.setAlpha(1f);
        if (scheduleFade) handle.postDelayed(fadeHandle, HANDLE_IDLE_MS);
    }

    static boolean enabled(Context context) {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getBoolean(ENABLED, false);
    }

    static int dp(Context context, int size) {
        return Math.round(size * context.getResources().getDisplayMetrics().density);
    }

    private static GradientDrawable background(int color, int radius) {
        GradientDrawable shape = new GradientDrawable();
        shape.setColor(color);
        shape.setCornerRadius(radius);
        return shape;
    }

    private FrameLayout content(Activity activity) {
        return activity.findViewById(android.R.id.content);
    }

    private static float clamp(float value, float min, float max) {
        return Math.max(min, Math.min(max, value));
    }

    private boolean dockRight(Activity activity) {
        return activity.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getBoolean(DOCK_RIGHT, true);
    }

    private void placeHandle(Activity activity, TextView button, boolean right, float height) {
        FrameLayout root = content(activity);
        int travel = Math.max(0, root.getHeight() - dp(activity, 48));
        handlePosition.x = right ? Math.max(0, root.getWidth() - handlePosition.width) : 0;
        handlePosition.y = height < 0 ? Math.min(dp(activity, 72), travel)
                : Math.round(clamp(height, 0, 1) * travel);
        int radius = dp(activity, 10);
        int left = right ? radius : 0;
        int edge = right ? 0 : radius;
        GradientDrawable shape = background(0xe526434d, radius);
        shape.setCornerRadii(new float[]{left, left, edge, edge, edge, edge, left, left});
        button.setBackground(shape);
        if (button.isAttachedToWindow()) activity.getWindowManager().updateViewLayout(button, handlePosition);
    }

    private WindowManager.LayoutParams subwindow(Activity activity, int width, int height, boolean focusable) {
        // The app window owns its touch stream. Touches outside go through normal Android window dispatch.
        int flags = WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL;
        if (!focusable) flags |= WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE;
        WindowManager.LayoutParams position = new WindowManager.LayoutParams(width, height,
                WindowManager.LayoutParams.TYPE_APPLICATION_PANEL, flags, PixelFormat.TRANSLUCENT);
        position.gravity = Gravity.TOP | Gravity.LEFT;
        position.token = activity.getWindow().getDecorView().getWindowToken();
        position.softInputMode = WindowManager.LayoutParams.SOFT_INPUT_ADJUST_NOTHING;
        position.setTitle(focusable ? "BH2017 GM 控制台" : "BH2017 GM 把手");
        return position;
    }

    private void attach(Activity activity) {
        if (activity.isFinishing() || activity != game || handle != null) return;
        TextView button = new TextView(activity);
        button.setText("GM");
        button.setTextColor(Color.WHITE);
        button.setTextSize(12);
        button.setContentDescription("展开 GM");
        button.setGravity(Gravity.CENTER);
        button.setOnClickListener(v -> expand(activity));
        handlePosition = subwindow(activity, dp(activity, 29), dp(activity, 48), false);
        FrameLayout root = content(activity);
        button.setOnTouchListener(new Drag(root, button, handlePosition, true));
        rootSizeListener = (view, left, top, right, bottom, oldLeft, oldTop, oldRight, oldBottom) -> {
            if (right - left != oldRight - oldLeft || bottom - top != oldBottom - oldTop)
                placeHandle(activity, button, dockRight(activity), activity.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                        .getFloat(DOCK_HEIGHT, -1));
        };
        root.addOnLayoutChangeListener(rootSizeListener);
        handle = button;
        placeHandle(activity, button, dockRight(activity), activity.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                .getFloat(DOCK_HEIGHT, -1));
        activity.getWindowManager().addView(button, handlePosition);
        wakeHandle(true);
        Log.i(TAG, "ATTACHED " + activity.getClass().getName());
    }

    private void expand(Activity activity) {
        if (panel != null) return;
        wakeHandle(false);
        activity.getWindowManager().removeViewImmediate(handle);
        panel = new LinearLayout(activity);
        panel.setOrientation(LinearLayout.VERTICAL);
        panel.setClickable(true);
        panel.setSystemUiVisibility(activity.getWindow().getDecorView().getWindowSystemUiVisibility());
        panel.setBackground(background(0xff151d2b, dp(activity, 10)));
        panel.setClipToOutline(true);

        LinearLayout header = new LinearLayout(activity);
        header.setGravity(Gravity.CENTER_VERTICAL);
        header.setPadding(dp(activity, 12), 0, dp(activity, 6), 0);
        TextView title = new TextView(activity);
        title.setText("GM 控制台");
        title.setContentDescription("GM 控制台，拖动标题栏移动面板");
        title.setTextColor(0xffeef4fa);
        title.setGravity(Gravity.CENTER_VERTICAL);
        header.addView(title, new LinearLayout.LayoutParams(0, -1, 1));
        Button close = new Button(activity);
        close.setText("收起");
        close.setOnClickListener(v -> collapse(true, "button"));
        header.addView(close);
        panel.addView(header, new LinearLayout.LayoutParams(-1, dp(activity, 44)));

        FrameLayout root = content(activity);
        int width = Math.min(dp(activity, 370), root.getWidth() - dp(activity, 16));
        int edge = dp(activity, 8);
        panelPosition = subwindow(activity, width, root.getHeight() - edge * 2, true);
        panelPosition.x = dockRight(activity) ? root.getWidth() - width - edge : edge;
        panelPosition.y = edge;
        title.setOnTouchListener(new Drag(root, panel, panelPosition, false));
        activity.getWindowManager().addView(panel, panelPosition);
        Log.i(TAG, "OPEN");
        openPage(activity);
    }

    private final class Drag implements View.OnTouchListener {
        private final FrameLayout root;
        private final View target;
        private final WindowManager.LayoutParams position;
        private final boolean docks;
        private final int slop;
        private float downX, downY, startX, startY;
        private boolean moved;

        Drag(FrameLayout root, View target, WindowManager.LayoutParams position, boolean docks) {
            this.root = root;
            this.target = target;
            this.position = position;
            this.docks = docks;
            slop = ViewConfiguration.get(root.getContext()).getScaledTouchSlop();
        }

        @Override public boolean onTouch(View touched, MotionEvent event) {
            switch (event.getActionMasked()) {
                case MotionEvent.ACTION_DOWN:
                    if (docks) wakeHandle(false);
                    downX = event.getRawX();
                    downY = event.getRawY();
                    startX = position.x;
                    startY = position.y;
                    moved = false;
                    return true;
                case MotionEvent.ACTION_MOVE:
                    float dx = event.getRawX() - downX;
                    float dy = event.getRawY() - downY;
                    if (Math.abs(dx) > slop || (docks && Math.abs(dy) > slop)) moved = true;
                    if (moved) {
                        int margin = docks ? 0 : dp(root.getContext(), 8);
                        position.x = Math.round(clamp(startX + dx, margin, root.getWidth() - position.width - margin));
                        if (docks)
                            position.y = Math.round(clamp(startY + dy, 0, root.getHeight() - position.height));
                        game.getWindowManager().updateViewLayout(target, position);
                    }
                    return true;
                case MotionEvent.ACTION_UP:
                    if (docks) wakeHandle(true);
                    if (!moved) {
                        if (docks) touched.performClick();
                    } else if (docks) {
                        boolean right = position.x + position.width / 2f >= root.getWidth() / 2f;
                        float y = (float) position.y / Math.max(1, root.getHeight() - position.height);
                        game.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                                .putBoolean(DOCK_RIGHT, right).putFloat(DOCK_HEIGHT, y).apply();
                        placeHandle(game, handle, right, y);
                        Log.i(TAG, "DOCK " + (right ? "right" : "left") + " " + Math.round(y * 100));
                    } else {
                        Log.i(TAG, "MOVE_PANEL " + position.x);
                    }
                    return true;
                case MotionEvent.ACTION_CANCEL:
                    if (docks) wakeHandle(true);
                    if (game != null && target.isAttachedToWindow()) {
                        position.x = (int) startX;
                        position.y = (int) startY;
                        game.getWindowManager().updateViewLayout(target, position);
                    }
                    return true;
                default:
                    return true;
            }
        }
    }

    private void openPage(Activity activity) {
        try {
            browser = new WebView(activity);
            browser.setBackgroundColor(0xff0b101b);
            browser.getSettings().setJavaScriptEnabled(true);
            browser.getSettings().setAllowContentAccess(false);
            browser.getSettings().setAllowFileAccess(false);
            browser.getSettings().setBlockNetworkLoads(true);
            browser.addJavascriptInterface(new GmMailbox(activity), "GmNative");
            browser.setWebViewClient(new WebViewClient() {
                @Override public boolean shouldOverrideUrlLoading(WebView view, String url) {
                    return !PAGE.equals(url);
                }

                @Override public boolean onRenderProcessGone(WebView view, RenderProcessGoneDetail details) {
                    if (browser == view) pageUnavailable(activity);
                    return true;
                }
            });
            browser.setWebChromeClient(new WebChromeClient() {
                @Override public void onReceivedTitle(WebView view, String title) {
                    if (title != null && title.matches("GM:(READY|TAB|SEARCH|SELECT|PAGE):[0-9]+"))
                        Log.i(TAG, "WEB " + title);
                }
            });
            panel.addView(browser, new LinearLayout.LayoutParams(-1, 0, 1));
            browser.loadUrl(PAGE);
        } catch (RuntimeException error) {
            Log.e(TAG, "WEB_UNAVAILABLE", error);
            pageUnavailable(activity);
        }
    }

    private void pageUnavailable(Activity activity) {
        destroyPage();
        Log.w(TAG, "WEB_FALLBACK");
        TextView message = new TextView(activity);
        message.setPadding(dp(activity, 12), 0, dp(activity, 12), 0);
        message.setTextColor(0xffeef4fa);
        message.setText("WebView 无法打开。可收起面板并继续游戏。");
        panel.addView(message);
    }

    private static void remove(View view) {
        if (view != null && view.getParent() instanceof ViewGroup)
            ((ViewGroup) view.getParent()).removeView(view);
    }

    private void destroyPage() {
        if (browser == null) return;
        WebView old = browser;
        browser = null;
        remove(old);
        old.destroy();
    }

    private void collapse(boolean showHandle, String reason) {
        if (panel == null) return;
        InputMethodManager ime = (InputMethodManager) game.getSystemService(Activity.INPUT_METHOD_SERVICE);
        if (ime != null) ime.hideSoftInputFromWindow(panel.getWindowToken(), 0);
        destroyPage();
        game.getWindowManager().removeViewImmediate(panel);
        panel = null;
        panelPosition = null;
        if (showHandle && handle != null) {
            game.getWindowManager().addView(handle, handlePosition);
            wakeHandle(true);
        }
        Log.i(TAG, "CLOSE " + reason);
    }

    @Override public void onActivityResumed(Activity activity) {
        if (!GAME.equals(activity.getClass().getName())) return;
        if (!enabled(activity)) {
            Log.i(TAG, "DISABLED");
            return;
        }
        game = activity;
        activity.getWindow().getDecorView().post(() -> attach(activity));
    }

    @Override public void onActivityPaused(Activity activity) {
        if (activity != game) return;
        collapse(false, "pause");
        if (rootSizeListener != null) content(activity).removeOnLayoutChangeListener(rootSizeListener);
        rootSizeListener = null;
        wakeHandle(false);
        if (handle != null && handle.isAttachedToWindow()) activity.getWindowManager().removeViewImmediate(handle);
        handle = null;
        handlePosition = null;
        game = null;
        Log.i(TAG, "DETACHED");
    }

    @Override public void onActivityDestroyed(Activity activity) { onActivityPaused(activity); }
    @Override public void onActivityCreated(Activity activity, Bundle state) {}
    @Override public void onActivityStarted(Activity activity) {}
    @Override public void onActivityStopped(Activity activity) {}
    @Override public void onActivitySaveInstanceState(Activity activity, Bundle state) {}
}
