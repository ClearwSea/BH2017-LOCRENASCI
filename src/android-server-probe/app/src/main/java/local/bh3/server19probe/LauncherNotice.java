package local.bh3.server19probe;

import android.content.ActivityNotFoundException;
import android.text.SpannableString;
import android.text.Spanned;
import android.text.method.LinkMovementMethod;
import android.text.style.URLSpan;
import android.view.View;
import android.widget.TextView;
import android.widget.Toast;

/** Launcher release link / 启动页公告超链接渲染。 */
public final class LauncherNotice {
    static final String LATEST_RELEASE_URL = "https://github.com/ClearwSea/BH2017-LOCRENASCI/releases/latest";
    static final String VERIFIED_PLATFORMS_URL =
        "https://github.com/ClearwSea/BH2017-LOCRENASCI#详细参考源码导航与实测列表";

    private LauncherNotice() {}

    private static final class SafeUrlSpan extends URLSpan {
        SafeUrlSpan(String url) { super(url); }

        @Override public void onClick(View widget) {
            try {
                super.onClick(widget);
            } catch (ActivityNotFoundException error) {
                Toast.makeText(widget.getContext(), "未找到可打开链接的应用：" + getURL(), Toast.LENGTH_LONG).show();
            }
        }
    }

    private static void linkAll(SpannableString content, String raw, String label, String url) {
        int index = 0;
        while ((index = raw.indexOf(label, index)) >= 0) {
            content.setSpan(new SafeUrlSpan(url), index, index + label.length(), Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
            index += label.length();
        }
    }

    public static void setText(TextView view, CharSequence text) {
        String raw = text.toString();
        SpannableString content = new SpannableString(raw);
        linkAll(content, raw, "最新构建版", LATEST_RELEASE_URL);
        linkAll(content, raw, "特定开发平台验证", VERIFIED_PLATFORMS_URL);
        String legacyLabel = "【最新版本：检查】";
        int legacyStart = raw.indexOf(legacyLabel);
        if (legacyStart >= 0) {
            legacyStart += legacyLabel.indexOf("检查");
            content.setSpan(new SafeUrlSpan(LATEST_RELEASE_URL),
                legacyStart, legacyStart + 2, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
        }
        view.setText(content);
        view.setLinkTextColor(0xff0066cc);
        view.setMovementMethod(LinkMovementMethod.getInstance());
    }
}
