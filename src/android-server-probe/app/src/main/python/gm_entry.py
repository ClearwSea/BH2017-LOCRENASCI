"""Android bridge for offline GM settings; caller holds process_guard."""
import json
from pathlib import Path
import sys


def _module(context):
    if 'server19_gm' not in sys.modules:
        from probe_entry import extract_runtime
        extract_runtime(context)
    import server19_gm
    return server19_gm


def _data(context):
    return Path(str(context.getFilesDir().getAbsolutePath())) / 'formal-data'


def load(context):
    return json.dumps(_module(context).describe(_data(context)), ensure_ascii=False)


def save(context, config_json, expected_effective_begin):
    return json.dumps(_module(context).save(_data(context), json.loads(str(config_json)),
                                            int(expected_effective_begin)), ensure_ascii=False)
