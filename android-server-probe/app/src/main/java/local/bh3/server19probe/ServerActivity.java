package local.bh3.server19probe;

import android.app.Activity;
import android.os.Bundle;
import android.content.Intent;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

/** 手机启动入口 / Manual standalone server launcher. */
public class ServerActivity extends Activity {
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        int pad = (int)(24 * getResources().getDisplayMetrics().density);
        layout.setPadding(pad, pad, pad, pad);
        TextView text = new TextView(this);
        text.setTextSize(18);
        text.setText("崩坏3离线服务端\n\n点击启动，等待通知显示“已就绪”，再打开游戏。无需连接电脑或网络。\n\n退出此页面不会关闭服务。手机重启或服务被关闭后，请再次启动。游戏与服务端目前是两个应用。\n\n存档保存在此应用内，请勿清除应用数据或卸载。");
        layout.addView(text);
        Button start = new Button(this);
        start.setText("启动手机服务端");
        start.setOnClickListener(v -> {
            startForegroundService(new Intent(this, ProbeService.class));
            text.setText("已发送启动请求，请查看通知。\n\n通知显示“已就绪”后即可打开游戏；重复点击不会重复启动服务。\n\n若显示失败，请保留现场并反馈。请勿清除应用数据或卸载。");
        });
        layout.addView(start);
        setContentView(layout);
    }
}
