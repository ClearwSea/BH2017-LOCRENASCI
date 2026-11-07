package local.bh3.server19probe;

import android.text.SpannableString;
import android.text.Spanned;
import android.text.method.LinkMovementMethod;
import android.text.style.URLSpan;
import android.widget.TextView;

/** Launcher release link / 启动页最新版本链接。 */
public final class LauncherNotice {
    private LauncherNotice() {}
    public static void setText(TextView view, CharSequence text) {
        SpannableString content = new SpannableString(text);
        String label = "【最新版本：检查】";
        int start = text.toString().indexOf(label);
        if (start >= 0) {
            start += label.indexOf("检查");
            content.setSpan(new URLSpan("https://github.com/ClearwSea/BH2017-LOCRENASCI/releases/latest"),
                start, start + 2, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
        }
        view.setText(content);
        view.setLinkTextColor(0xff0066cc);
        view.setMovementMethod(LinkMovementMethod.getInstance());
    }
}
