"""Cache immutable, verified stage configuration; never cache player state."""
from functools import lru_cache
import json


def install(stage):
    # Call after portable.configure: all story/Extra wrappers and table overrides
    # must already be installed and their source bundle SHA verified.
    original = stage.stage_config

    @lru_cache(maxsize=1024)
    def canonical(identity):
        # Source configurations are JSON trees. Keep an encoded canonical copy
        # so each caller gets fresh containers via the native JSON decoder,
        # avoiding Python deepcopy's per-scalar bookkeeping on ARM32.
        return json.dumps(original(identity), ensure_ascii=False,
                          separators=(',', ':'), allow_nan=False)

    def config(identity=stage.STAGE_ID):
        # Callers retain the original ownership semantics: mutating their result
        # cannot change future configurations or another request's result.
        return json.loads(canonical(identity))

    stage.stage_config = config
    return canonical.cache_info
