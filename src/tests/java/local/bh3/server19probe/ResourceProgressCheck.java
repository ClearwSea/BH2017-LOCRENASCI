package local.bh3.server19probe;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.Map;
import java.util.Random;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;
import org.json.JSONObject;

/** Host-only check of byte-based resource verification and failure reporting. */
public final class ResourceProgressCheck {
    private static final class Capture implements EmbeddedResources.Progress {
        final ArrayList<Long> values = new ArrayList<>();
        long total;
        @Override public void update(String text) { }
        @Override public void stage(String phase, long completed, long total) {
            if (!"verify".equals(phase) || total <= 0 || completed < 0 || completed > total)
                throw new AssertionError("invalid progress event");
            if (this.total != 0 && this.total != total) throw new AssertionError("total changed");
            if (!values.isEmpty() && completed < values.get(values.size() - 1)) throw new AssertionError("progress regressed");
            this.total = total; values.add(completed);
        }
    }
    public static void main(String[] args) throws Exception {
        byte[] data = new byte[1024 * 1024]; new Random(19).nextBytes(data);
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ZipOutputStream out = new ZipOutputStream(bytes)) {
            out.putNextEntry(new ZipEntry("video")); out.write(data); out.closeEntry();
        }
        Map<String, JSONObject> manifest = new HashMap<>();
        manifest.put("video", new JSONObject().put("size", data.length).put("sha256", EmbeddedResources.hash(data)));
        Capture valid = new Capture();
        EmbeddedResources.verifyPack(new ByteArrayInputStream(bytes.toByteArray()), manifest, valid);
        if (valid.values.size() < 3 || valid.values.size() > 101 || valid.values.get(0) != 0
                || valid.values.get(valid.values.size() - 1) != valid.total)
            throw new AssertionError("valid verification progress incomplete or excessive");
        manifest.get("video").put("sha256", "wrong"); Capture invalid = new Capture();
        try {
            EmbeddedResources.verifyPack(new ByteArrayInputStream(bytes.toByteArray()), manifest, invalid);
            throw new AssertionError("invalid pack accepted");
        } catch (java.io.IOException expected) { }
        if (invalid.values.isEmpty() || invalid.values.get(invalid.values.size() - 1) >= invalid.total)
            throw new AssertionError("failed verification reported completion");
        System.out.println("PASS: real byte progress is monotonic, limited, and reports completion only after validation");
    }
}
