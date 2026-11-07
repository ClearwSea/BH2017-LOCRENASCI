package local.bh3.server19probe;

final class NativePaths {
    static { System.loadLibrary("server19paths"); }
    private static native int changeDirectory(String path);
    static void enter(String path) throws java.io.IOException {
        int result = changeDirectory(path);
        if (result != 0) throw new java.io.IOException("Private resource directory unavailable: " + result);
    }
}
