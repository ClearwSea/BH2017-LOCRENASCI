using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

internal static class DesktopLauncher {
    private static string Quote(string value) { return "\"" + value + "\""; }

    [STAThread]
    private static void Main() {
        string baseDir = AppDomain.CurrentDomain.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar);
        string python = Path.Combine(baseDir, "tools", "python", "pythonw.exe");
        string script = Path.Combine(baseDir, "app", "launch_gui.py");
        if (!File.Exists(python) || !File.Exists(script)) {
            MessageBox.Show("请将构建器程序和离线工具包解压到同一目录。\n需要 app 和 tools 两个文件夹。",
                "构建器文件不完整", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return;
        }
        try {
            var info = new ProcessStartInfo(python, "-B -s " + Quote(script) + " " + Quote(baseDir));
            info.UseShellExecute = false;
            info.CreateNoWindow = true;
            info.WorkingDirectory = baseDir;
            foreach (string key in new[] { "PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV", "TCL_LIBRARY", "TK_LIBRARY" })
                info.EnvironmentVariables.Remove(key);
            info.EnvironmentVariables["PYTHONNOUSERSITE"] = "1";
            info.EnvironmentVariables["PYTHONUTF8"] = "1";
            Process.Start(info);
        } catch (Exception error) {
            MessageBox.Show(error.Message, "无法启动构建器", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }
}
