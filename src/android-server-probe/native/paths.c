/* ARM EABI bridge, no libc/NDK dependency. JNI string slots follow jni.h. */
typedef const char *(*get_utf)(void *, void *, unsigned char *);
typedef void (*release_utf)(void *, void *, const char *);
__attribute__((visibility("default")))
int Java_local_bh3_server19probe_NativePaths_changeDirectory(void *env, void *cls, void *path) {
    void **table = *(void ***)env;
    const char *text = ((get_utf)table[169])(env, path, 0);
    if (!text) return -12;
    register long arg __asm__("r0") = (long)text;
    register long call __asm__("r7") = 12; /* Linux ARM __NR_chdir */
    __asm__ volatile("svc 0" : "+r"(arg) : "r"(call) : "memory", "cc");
    long result = arg;
    ((release_utf)table[170])(env, path, text);
    return (int)result;
}
